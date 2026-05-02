"""archspec Go scanner: discover architectural artefacts in Go source.

Scans a service directory's `*.go` files (excluding `_test.go`, `vendor/`,
`gen/`, `.git/`) and emits a JSON report describing endpoints, downstream
synchronous calls, storage clients, and messaging topics that the user should
record in `SERVICE_MAP.yaml`.

Read-only. Deterministic — same input ⇒ same JSON bytes.

CLI:
  scan_go.py <service_dir>
      Forward scan: discover artefacts produced/owned by the given service.

  scan_go.py --reverse-scan <repo_root> --target <service-name>
      Reverse scan: discover *consumers* of the target service in a monorepo.
      Looks for Go files importing `<...>/<domain>/v1` (where domain is derived
      from the service name) and extracts the gRPC method names that are used
      via `<alias>.<Method>Request{` patterns.

Exit codes:
  0 — scan completed (report on stdout, possibly with empty arrays)
  2 — usage error (missing/unreadable directory or arguments)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {"vendor", "gen", ".git", "node_modules", "testdata"}

# Directory names that the aggregate detector considers "in scope". A Mutex
# living outside these directories (e.g. in usecase/, handler/, cmd/) is not
# evidence of a domain aggregate.
_AGGREGATE_SCOPE_DIRS = {"repository", "repo", "domain", "infra"}

# Method-name suffixes that indicate compare-and-set / atomic write semantics.
_CAS_METHOD_SUFFIXES = ("WithEvent", "IfAbsent", "CAS")

# Receiver-type suffixes to strip when deriving an aggregate name.
_REPO_TYPE_SUFFIXES = ("Repository", "MemoryRepo", "Repo", "Store")

_HTTP_VERB_METHODS = ("Get", "Post", "Put", "Patch", "Delete", "Head", "Options")

_HTTP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ANY", re.compile(r'\b(?:[A-Za-z_]\w*\.)?HandleFunc\s*\(\s*"([^"]+)"')),
    *[
        (verb.upper(), re.compile(rf'\b[A-Za-z_]\w*\.{verb}\s*\(\s*"([^"]+)"'))
        for verb in _HTTP_VERB_METHODS
    ],
    *[
        (verb, re.compile(rf'\b[A-Za-z_]\w*\.{verb}\s*\(\s*"([^"]+)"'))
        for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
    ],
]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


_GRPC_REGISTER_PATTERN = re.compile(
    r'\b(?:[A-Za-z_]\w*\.)?Register([A-Z][A-Za-z0-9_]*Server)\s*\('
)

# How many parent directories of the service to walk up looking for proto/.
_PROTO_LOOKUP_DEPTH = 5


def _domain_from_grpc_server(name: str) -> str:
    """`GeoServiceServer` → `geo`, `TaskServer` → `task`, `ABCServer` → `abc`."""
    n = name[: -len("Server")] if name.endswith("Server") else name
    if n.endswith("Service"):
        n = n[: -len("Service")]
    parts = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+|[A-Z]+(?=[A-Z]|$)", n)
    return "-".join(p.lower() for p in parts) or n.lower()


def _find_proto_contract(service_dir: Path, domain: str) -> str | None:
    """Walk up from service_dir looking for proto/<domain>/v1/*.proto.

    Returns the path relative to service_dir (so it stays portable across
    machines) or None if no candidate is found.
    """
    abs_path = _find_proto_contract_abs(service_dir, domain)
    if abs_path is None:
        return None
    try:
        return str(abs_path.relative_to(service_dir.resolve()))
    except ValueError:
        return str(abs_path)


def _find_proto_contract_abs(service_dir: Path, domain: str) -> Path | None:
    """Same as ``_find_proto_contract`` but returns the absolute path.

    Internal helper — used by RPC-method enumeration which needs to actually
    read the proto file.
    """
    cursor = service_dir.resolve()
    for _ in range(_PROTO_LOOKUP_DEPTH):
        candidate_dir = cursor / "proto" / domain / "v1"
        if candidate_dir.is_dir():
            protos = sorted(candidate_dir.glob("*.proto"))
            if protos:
                return protos[0]
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return None


_PROTO_RPC_METHOD = re.compile(r"\brpc\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_PROTO_SERVICE_HEADER = re.compile(r"\bservice\s+([A-Za-z_]\w*)\s*\{")


def _extract_service_body(text: str, service_name: str) -> str | None:
    """Return the contents between matched braces of ``service <service_name> { ... }``.

    Walks the text with a brace-balance counter so nested ``message { ... }``
    blocks (rare in proto, but legal) do not confuse the parser. Returns None
    when no matching service header is found.
    """
    for header in _PROTO_SERVICE_HEADER.finditer(text):
        if header.group(1) != service_name:
            continue
        # `header.end()` points just past the opening `{`.
        depth = 1
        i = header.end()
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[header.end():i]
            i += 1
        return None
    return None


def _parse_proto_rpc_methods(proto_path: Path, server_name: str) -> list[str]:
    """Extract RPC method names declared inside ``service <server_name> { ... }``.

    ``server_name`` is the name from ``Register<X>Server`` with the trailing
    ``Server`` stripped (e.g. ``OrderServiceServer`` → ``OrderService``).
    Limiting to one service-block prevents bleed when a proto file declares
    multiple services side-by-side (admin + public, etc.).

    Returns names in source order with duplicates removed. Empty list when
    the file is unreadable, the named service is missing, or the block has
    no rpc declarations — the caller falls back to a single summary entry.
    """
    try:
        text = proto_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    body = _extract_service_body(text, server_name)
    if body is None:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _PROTO_RPC_METHOD.finditer(body):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out

_GRPC_CLIENT_PATTERN = re.compile(
    r'\bgrpc\.(?:NewClient|Dial)\s*\(\s*([A-Za-z_]\w*|"[^"]+")'
)
_CONST_OR_VAR_ASSIGN = re.compile(
    r'\b([A-Za-z_]\w*)\s*(?::?=|=)\s*"([^"]+)"'
)
_IDENT_ALIAS = re.compile(r'\b([A-Za-z_]\w*)\s*(?::=|=)\s*([A-Za-z_]\w*)\s*(?:$|\n|//)')


def _build_string_const_table(text: str) -> dict[str, str]:
    """Map identifier → string literal it is assigned to.

    Two passes so identifier aliases resolve: first capture all literal
    assignments, then resolve `x := otherIdent` chains up to depth 4.
    """
    literals: dict[str, str] = {}
    for m in _CONST_OR_VAR_ASSIGN.finditer(text):
        literals[m.group(1)] = m.group(2)
    aliases: dict[str, str] = {}
    for m in _IDENT_ALIAS.finditer(text):
        if m.group(1) not in literals:
            aliases[m.group(1)] = m.group(2)
    for _ in range(4):
        for k, v in list(aliases.items()):
            if v in literals:
                literals[k] = literals[v]
                del aliases[k]
    return literals


def _build_alias_to_root(text: str) -> dict[str, str]:
    """Map alias identifier → its root identifier (for `x := y` chains).

    Used to derive a meaningful service name from the root constant when the
    grpc.NewClient call passes an alias variable.
    """
    aliases: dict[str, str] = {}
    for m in _IDENT_ALIAS.finditer(text):
        aliases[m.group(1)] = m.group(2)
    for _ in range(4):
        for k, v in list(aliases.items()):
            if v in aliases:
                aliases[k] = aliases[v]
    return aliases


def _service_name_from_const(ident: str) -> str:
    s = ident
    if s.startswith("default"):
        s = s[len("default") :]
    for suf in ("Address", "Addr"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    parts = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", s)
    return "-".join(p.lower() for p in parts) or ident.lower()


def _service_name_from_literal(literal: str) -> str:
    head = literal.split(":", 1)[0].strip()
    return head or "unknown"


_TOPIC_FIELD = re.compile(r'\bTopic\s*:\s*"([^"]+)"')
# `Topics: []string{...}` (struct field), `topics := []string{...}`, `topics = ...`.
_SARAMA_TOPICS_LITERAL = re.compile(
    r'\b(?:Topics|topics)\s*[:=]+\s*\[\]string\s*\{\s*("[^"]+"(?:\s*,\s*"[^"]+")*)\s*\}'
)
# Block bodies allow one level of nested `{...}` (e.g. `Brokers: []string{...}`).
_NESTED_BRACE_BODY = r"(?:[^{}]|\{[^{}]*\})*"
_KAFKA_WRITER_BLOCK = re.compile(
    rf"kafka\.NewWriter\s*\(\s*kafka\.WriterConfig\s*\{{(?P<body>{_NESTED_BRACE_BODY})\}}",
    re.DOTALL,
)
_KAFKA_READER_BLOCK = re.compile(
    rf"kafka\.NewReader\s*\(\s*kafka\.ReaderConfig\s*\{{(?P<body>{_NESTED_BRACE_BODY})\}}",
    re.DOTALL,
)
_SARAMA_PRODUCER_MSG = re.compile(
    rf"sarama\.ProducerMessage\s*\{{(?P<body>{_NESTED_BRACE_BODY})\}}",
    re.DOTALL,
)
_NATS_PUBLISH = re.compile(
    r'\b[A-Za-z_]\w*\.Publish\s*\(\s*((?:[A-Za-z_]\w*)|"[^"]+")'
)
_NATS_SUBSCRIBE = re.compile(
    r'\b[A-Za-z_]\w*\.Subscribe\s*\(\s*((?:[A-Za-z_]\w*)|"[^"]+")'
)
_NATS_QUEUE_SUBSCRIBE = re.compile(
    r'\b[A-Za-z_]\w*\.QueueSubscribe\s*\(\s*((?:[A-Za-z_]\w*)|"[^"]+")'
)
# JetStream `js.Publish(ctx, subject, ...)` — first arg may contain balanced `(...)`.
_JETSTREAM_PUBLISH = re.compile(
    r'\b[A-Za-z_]\w*\.Publish(?:Async)?\s*\((?:\([^()]*\)|[^,()])*,\s*((?:[A-Za-z_]\w*)|"[^"]+")'
)


def _resolve_subject(arg: str, const_table: dict[str, str]) -> str | None:
    if arg.startswith('"') and arg.endswith('"'):
        return arg[1:-1]
    return const_table.get(arg)


def _scan_kafka(text: str, rel: Path) -> tuple[list[dict], list[dict]]:
    pub: list[dict] = []
    con: list[dict] = []
    for m in _KAFKA_WRITER_BLOCK.finditer(text):
        line = _line_of(text, m.start())
        for topic in _TOPIC_FIELD.findall(m.group("body")):
            pub.append({"kind": "event", "backend": "kafka", "topic": topic,
                        "source": f"{rel}:{line}", "confidence": "medium"})
    for m in _SARAMA_PRODUCER_MSG.finditer(text):
        line = _line_of(text, m.start())
        for topic in _TOPIC_FIELD.findall(m.group("body")):
            pub.append({"kind": "event", "backend": "kafka", "topic": topic,
                        "source": f"{rel}:{line}", "confidence": "medium"})
    for m in _KAFKA_READER_BLOCK.finditer(text):
        line = _line_of(text, m.start())
        for topic in _TOPIC_FIELD.findall(m.group("body")):
            con.append({"kind": "event", "backend": "kafka", "topic": topic,
                        "source": f"{rel}:{line}", "confidence": "medium"})
    if "sarama.NewConsumerGroup" in text:
        for m in _SARAMA_TOPICS_LITERAL.finditer(text):
            line = _line_of(text, m.start())
            for topic in re.findall(r'"([^"]+)"', m.group(1)):
                con.append({"kind": "event", "backend": "kafka", "topic": topic,
                            "source": f"{rel}:{line}", "confidence": "low"})
    return pub, con


_OUTBOX_WRAPPER = re.compile(
    r"^func\s+\([^)]+\)\s+Publish([A-Z][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)
_OUTBOX_BODY_LITERAL = re.compile(r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"')


def _camel_to_dotted(name: str) -> str:
    """Convert ``MatchFound`` to ``match.found`` for outbox-wrapper topic guess."""
    parts = re.findall(r"[A-Z][a-z0-9]*|[A-Z]+(?=[A-Z]|$)|[a-z0-9]+", name)
    return ".".join(p.lower() for p in parts) if parts else name.lower()


def _find_func_body_offsets(text: str, params_open_after: int) -> tuple[int, int] | None:
    """Locate a Go function body's brace span from just past the params' ``(``.

    ``params_open_after`` is the offset right after the opening ``(`` of the
    parameter list (i.e. ``_OUTBOX_WRAPPER`` match's ``end()``). Steps:

      1. Paren-balance forward to the matching ``)`` of the parameter list.
      2. Scan ahead past the return type until the body's ``{``.
      3. Brace-balance to the matching ``}``.

    Returns ``(body_open_offset, body_close_offset)`` inclusive of both braces,
    or ``None`` for malformed input (mismatched parens/braces, truncated
    file). Naive — does not handle string or comment escapes inside
    signatures, which is fine for typical Go code where braces don't appear
    in parameter types or return types.
    """
    n = len(text)
    depth = 1
    i = params_open_after
    while i < n and depth > 0:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    while i < n and text[i] != "{":
        i += 1
    if i >= n:
        return None
    body_open = i
    depth = 1
    i += 1
    while i < n and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (body_open, i)
        i += 1
    return None


def _scan_outbox_wrapper_publish(
    text: str, rel: Path
) -> tuple[list[dict], list[tuple[int, int]]]:
    """Emit medium-confidence publish findings for ``func (...) PublishX(...)``.

    Returns ``(findings, wrapper_ranges)``. Each wrapper range is
    ``(start_line, end_line)`` inclusive — the actual brace-balanced body
    span of the wrapper function (NOT a fixed lookahead window). The range
    is used by ``_collapse_events`` to suppress ``<dynamic>`` findings that
    originate from a publish call inside the same wrapper body — the wrapper
    finding already documents that publish.

    Why the real body and not a lookahead window: a short wrapper like
    ``func PublishFoo() error { return nc.Publish("foo", x) }`` followed by an
    independent ``nc.Publish(deriveSubject(), nil)`` a few lines later would
    otherwise have its dynamic publish silently swallowed by the wrapper's
    suppression range, even though they are two unrelated call sites.

    Heuristic: when a ``Publish<Name>`` method exists, read its body for
    either an inline topic literal (medium confidence) or a NATS publish
    call (low confidence, topic guessed from the method name in dotted form,
    e.g. ``MatchFound`` → ``match.found``).
    """
    out: list[dict] = []
    ranges: list[tuple[int, int]] = []
    seen: set[tuple[str, str]] = set()
    for m in _OUTBOX_WRAPPER.finditer(text):
        method_name = m.group(1)
        line_no = _line_of(text, m.start())
        body_offsets = _find_func_body_offsets(text, m.end())
        if body_offsets is None:
            continue
        body_open, body_close = body_offsets
        snippet = text[body_open : body_close + 1]
        end_no = _line_of(text, body_close)
        topic_match = _OUTBOX_BODY_LITERAL.search(snippet)
        if topic_match:
            topic = topic_match.group(1)
            confidence = "medium"
        elif "nats." in snippet or ".Publish(" in snippet:
            topic = _camel_to_dotted(method_name)
            confidence = "low"
        else:
            continue
        ranges.append((line_no, end_no))
        key = (topic, str(rel))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "kind": "event",
                "backend": "nats",
                "topic": topic,
                "source": f"{rel}:{line_no}",
                "confidence": confidence,
            }
        )
    return out, ranges


def _scan_nats(
    text: str, rel: Path, const_table: dict[str, str]
) -> tuple[list[dict], list[dict], list[tuple[int, int]]]:
    if "nats-io/nats.go" not in text and "nats.Connect" not in text and "jetstream." not in text:
        return [], [], []
    pub: list[dict] = []
    con: list[dict] = []

    def _emit(target: list[dict], pat: re.Pattern[str], confidence: str) -> None:
        for m in pat.finditer(text):
            subject = _resolve_subject(m.group(1), const_table)
            if subject is None:
                # Dynamic subject (fmt.Sprintf, function arg, etc.) — record as
                # low-confidence so the user sees the call site and confirms
                # the topic by hand.
                target.append(
                    {
                        "kind": "event",
                        "backend": "nats",
                        "topic": "<dynamic>",
                        "source": f"{rel}:{_line_of(text, m.start())}",
                        "confidence": "low",
                    }
                )
                continue
            target.append({"kind": "event", "backend": "nats", "topic": subject,
                           "source": f"{rel}:{_line_of(text, m.start())}",
                           "confidence": confidence})

    _emit(pub, _NATS_PUBLISH, "medium")
    _emit(pub, _JETSTREAM_PUBLISH, "medium")
    _emit(con, _NATS_SUBSCRIBE, "medium")
    _emit(con, _NATS_QUEUE_SUBSCRIBE, "medium")
    wrapper_pub, wrapper_ranges = _scan_outbox_wrapper_publish(text, rel)
    pub.extend(wrapper_pub)
    return pub, con, wrapper_ranges


_MESSAGING_BACKENDS = ("kafka", "nats")


_DYNAMIC_TOPIC = "<dynamic>"
_CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def _collapse_events(
    events: list[dict],
    wrapper_ranges_by_file: dict[str, list[tuple[int, int]]] | None = None,
) -> list[dict]:
    """Collapse duplicate event findings.

    Two-pass:
      1. Suppress ``<dynamic>`` entries whose source line falls inside the
         body of a wrapper-derived publish (``func PublishX(...)``). The
         wrapper finding already documents that publish, so ``<dynamic>``
         from the inner ``nc.Publish(...)`` is redundant. Independent
         dynamic publishes outside any wrapper survive — the user must see
         them, since nothing else explains the call site.
      2. De-dup by (backend, topic), retaining the highest-confidence record.
         When confidences tie, keep the first occurrence (source order).

    Without (1) the user would confirm one publish twice — once through the
    wrapper-derived topic, once through the inner ``<dynamic>`` marker.
    Without (2) we'd duplicate findings that the same publish produces via
    different detection paths (e.g. literal-resolve + outbox-wrapper).
    """
    ranges = wrapper_ranges_by_file or {}

    def _covered_by_wrapper(source: str) -> bool:
        try:
            file_part, line_part = source.rsplit(":", 1)
            line_n = int(line_part)
        except (ValueError, AttributeError):
            return False
        for start, end in ranges.get(file_part, []):
            if start <= line_n <= end:
                return True
        return False

    after_dynamic_filter = [
        e for e in events
        if e["topic"] != _DYNAMIC_TOPIC or not _covered_by_wrapper(e["source"])
    ]
    by_key: dict[tuple[str, str], dict] = {}
    for e in after_dynamic_filter:
        key = (e["backend"], e["topic"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = e
            continue
        if _CONFIDENCE_RANK[e["confidence"]] > _CONFIDENCE_RANK[existing["confidence"]]:
            by_key[key] = e
    return list(by_key.values())


def _scan_events(file: Path, root: Path) -> tuple[list[dict], list[dict]]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    const_table = _build_string_const_table(text)
    pub: list[dict] = []
    con: list[dict] = []
    wrapper_ranges_by_file: dict[str, list[tuple[int, int]]] = {}
    if "kafka" in _MESSAGING_BACKENDS:
        kp, kc = _scan_kafka(text, rel)
        pub.extend(kp)
        con.extend(kc)
    if "nats" in _MESSAGING_BACKENDS:
        np, nc, wrapper_ranges = _scan_nats(text, rel, const_table)
        pub.extend(np)
        con.extend(nc)
        if wrapper_ranges:
            wrapper_ranges_by_file[str(rel)] = wrapper_ranges
    return (
        _collapse_events(pub, wrapper_ranges_by_file),
        _collapse_events(con, wrapper_ranges_by_file),
    )


_STORAGE_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("postgres", "high", re.compile(r"\bpgx\.Connect\s*\(")),
    ("postgres", "high", re.compile(r"\bpgxpool\.(?:New|NewWithConfig|Connect)\s*\(")),
    ("redis", "high", re.compile(r"\bredis\.New(?:Failover)?Client\s*\(")),
    ("mongodb", "high", re.compile(r"\bmongo\.Connect\s*\(")),
    ("sql", "medium", re.compile(r"\bsql(?:x)?\.Open\s*\(")),
    (
        "in-memory",
        "low",
        re.compile(r"\b[A-Za-z_]\w*\.New[A-Z][A-Za-z0-9_]*MemoryRepo\s*\(|\bNewMemoryRepo\s*\("),
    ),
]


def _scan_storage(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    seen: set[tuple[str, int]] = set()
    out: list[dict] = []
    for storage_type, confidence, pat in _STORAGE_PATTERNS:
        for m in pat.finditer(text):
            line = _line_of(text, m.start())
            key = (storage_type, line)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "kind": "storage",
                    "type": storage_type,
                    "source": f"{rel}:{line}",
                    "confidence": confidence,
                }
            )
    return out


def _scan_downstream_sync(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    consts = _build_string_const_table(text)
    aliases = _build_alias_to_root(text)
    seen: set[str] = set()
    out: list[dict] = []
    for m in _GRPC_CLIENT_PATTERN.finditer(text):
        arg = m.group(1)
        if arg.startswith('"'):
            literal = arg[1:-1]
            name = _service_name_from_literal(literal)
            confidence = "medium"
        else:
            literal = consts.get(arg)
            if literal is not None:
                root_ident = aliases.get(arg, arg)
                name = _service_name_from_const(root_ident)
                confidence = "high"
            else:
                name = arg.lower()
                confidence = "low"
        if name in seen:
            continue
        seen.add(name)
        out.append(
            {
                "kind": "downstream_sync",
                "protocol": "gRPC",
                "service": name,
                "address_arg": arg,
                "source": f"{rel}:{_line_of(text, m.start())}",
                "confidence": confidence,
            }
        )
    return out


def _scan_grpc_endpoints(file: Path, root: Path) -> list[dict]:
    """Emit one endpoint finding per RPC method.

    Strategy: locate ``Register<X>Server(...)`` calls, then enumerate methods
    of the matching ``proto/<domain>/v1/*.proto`` (when present). Two-pass:
      1. For each server registration, try domain-based proto lookup
         (``_find_proto_contract_abs(root, domain)``). Cache successful protos
         as candidates.
      2. For servers whose direct lookup failed (or whose proto lacked a
         matching ``service`` block), probe the file-level candidate list. This
         catches admin/public service splits where one ``.proto`` package
         declares both ``BillingService`` and ``BillingAdminService``: domain
         derivation gives ``billing-admin`` for the admin server, but the real
         file lives under ``proto/billing/v1/billing.proto``.

    When neither pass yields RPC methods, fall back to a single summary entry
    naming the server interface — the questionnaire then asks the user to
    enumerate methods manually.
    """
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    registrations: list[tuple[str, int]] = []
    seen_servers: set[str] = set()
    for m in _GRPC_REGISTER_PATTERN.finditer(text):
        server_name = m.group(1)
        if server_name in seen_servers:
            continue
        seen_servers.add(server_name)
        registrations.append((server_name, _line_of(text, m.start())))

    proto_by_server: dict[str, Path | None] = {}
    candidate_protos: list[Path] = []
    for server_name, _ in registrations:
        domain = _domain_from_grpc_server(server_name)
        proto_abs = _find_proto_contract_abs(root, domain)
        proto_by_server[server_name] = proto_abs
        if proto_abs is not None and proto_abs not in candidate_protos:
            candidate_protos.append(proto_abs)

    out: list[dict] = []
    for server_name, line in registrations:
        proto_abs = proto_by_server[server_name]
        # `server_name` is `<X>ServiceServer`; the matching `service <X>Service { ... }`
        # block in proto identifies which RPC methods belong to this server.
        proto_service_name = (
            server_name[: -len("Server")] if server_name.endswith("Server") else server_name
        )
        methods: list[str] = (
            _parse_proto_rpc_methods(proto_abs, proto_service_name) if proto_abs else []
        )
        if not methods:
            for candidate in candidate_protos:
                if candidate == proto_abs:
                    continue
                fallback = _parse_proto_rpc_methods(candidate, proto_service_name)
                if fallback:
                    methods = fallback
                    proto_abs = candidate
                    break
        contract = None
        if proto_abs is not None:
            try:
                contract = str(proto_abs.relative_to(root.resolve()))
            except ValueError:
                contract = str(proto_abs)
        if not methods:
            finding: dict = {
                "kind": "endpoint",
                "protocol": "gRPC",
                "method": "RPC",
                "name": server_name,
                "path": server_name,
                "source": f"{rel}:{line}",
                "confidence": "high",
            }
            if contract:
                finding["contract_hint"] = contract
            out.append(finding)
            continue
        for method in methods:
            finding = {
                "kind": "endpoint",
                "protocol": "gRPC",
                "method": "RPC",
                "name": method,
                "path": f"{server_name}/{method}",
                "source": f"{rel}:{line}",
                "confidence": "high",
            }
            if contract:
                finding["contract_hint"] = contract
            out.append(finding)
    return out


_OPENAPI_CANDIDATES = (
    Path("api") / "schema.yaml",
    Path("api") / "openapi.yaml",
    Path("docs") / "openapi.yaml",
    Path("openapi.yaml"),
    Path("openapi") / "openapi.yaml",
)


def _find_openapi_contract(service_dir: Path) -> str | None:
    """Return relative path to the first OpenAPI schema found under known locations.

    Mirrors ``_find_proto_contract`` for HTTP services. Searches a small set of
    conventional paths within ``service_dir`` only — does not walk parents
    (HTTP schemas are typically scoped to a single service).
    """
    for candidate in _OPENAPI_CANDIDATES:
        full = service_dir / candidate
        if full.is_file():
            try:
                return str(full.resolve().relative_to(service_dir.resolve()))
            except ValueError:
                return str(candidate)
    return None


def _scan_http_endpoints(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    contract_hint = _find_openapi_contract(root)
    for method, pat in _HTTP_PATTERNS:
        for m in pat.finditer(text):
            path = m.group(1)
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            finding: dict = {
                "kind": "endpoint",
                "protocol": "HTTP",
                "method": method,
                "path": path,
                "source": f"{rel}:{_line_of(text, m.start())}",
                "confidence": "medium",
            }
            if contract_hint:
                finding["contract_hint"] = contract_hint
            out.append(finding)
    return out


_CAS_FUNC_PATTERN = re.compile(
    r'\bfunc\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+(\w+)\s*\('
)
_MUTEX_PATTERN = re.compile(r'\bsync\.(?:RW)?Mutex\b')
_REPO_STRUCT_PATTERN = re.compile(r'\btype\s+(\w+)\s+struct\b')


def _strip_repo_suffix(name: str) -> str:
    for suf in _REPO_TYPE_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            return name[: -len(suf)]
    return name


def _aggregate_in_scope(rel: Path) -> bool:
    return any(part in _AGGREGATE_SCOPE_DIRS for part in rel.parts[:-1])


def _scan_aggregates(file: Path, root: Path) -> list[dict]:
    """Detect domain aggregates from Go repository code.

    Heuristics:
      * func with name suffix WithEvent / IfAbsent / CAS → optimistic strategy
        (compare-and-set semantics).
      * sync.Mutex / sync.RWMutex inside a `type *Repo struct` → pessimistic.

    Only files under repository/ / repo/ / domain/ / infra/ are scanned —
    Mutex in cmd/ or usecase/ is not aggregate evidence.
    """
    rel = file.relative_to(root)
    if not _aggregate_in_scope(rel):
        return []
    text = file.read_text(encoding="utf-8", errors="replace")
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for m in _CAS_FUNC_PATTERN.finditer(text):
        receiver, method = m.group(1), m.group(2)
        if not any(method.endswith(suf) for suf in _CAS_METHOD_SUFFIXES):
            continue
        name = _strip_repo_suffix(receiver)
        key = (name, "optimistic")
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "kind": "aggregate",
                "name": name,
                "write_strategy": "optimistic",
                "source": f"{rel}:{_line_of(text, m.start())}",
                "confidence": "high",
            }
        )
    if _MUTEX_PATTERN.search(text):
        struct_match = _REPO_STRUCT_PATTERN.search(text)
        if struct_match:
            name = _strip_repo_suffix(struct_match.group(1))
        else:
            name = file.stem.split("_")[0].rstrip("s").capitalize() or "Aggregate"
        key = (name, "pessimistic")
        if key not in seen and not any(s == name for s, _ in seen):
            seen.add(key)
            mutex_match = _MUTEX_PATTERN.search(text)
            line = _line_of(text, mutex_match.start()) if mutex_match else 1
            out.append(
                {
                    "kind": "aggregate",
                    "name": name,
                    "write_strategy": "pessimistic",
                    "source": f"{rel}:{line}",
                    "confidence": "medium",
                }
            )
    return out


def _iter_go_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*.go")):
        if p.name.endswith("_test.go"):
            continue
        if any(part in EXCLUDE_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        out.append(p)
    return out


def scan(service_dir: Path) -> dict:
    """Return the discovery report as a Python dict."""
    files = _iter_go_files(service_dir)
    endpoints: list[dict] = []
    downstream: list[dict] = []
    storage: list[dict] = []
    pub: list[dict] = []
    con: list[dict] = []
    aggregates: list[dict] = []
    for f in files:
        endpoints.extend(_scan_http_endpoints(f, service_dir))
        endpoints.extend(_scan_grpc_endpoints(f, service_dir))
        downstream.extend(_scan_downstream_sync(f, service_dir))
        storage.extend(_scan_storage(f, service_dir))
        p, c = _scan_events(f, service_dir)
        pub.extend(p)
        con.extend(c)
        aggregates.extend(_scan_aggregates(f, service_dir))
    endpoints.sort(key=lambda e: (e["protocol"], e["method"], e.get("path", ""), e["source"]))
    downstream.sort(key=lambda d: (d["service"], d["source"]))
    storage.sort(key=lambda s: (s["type"], s["source"]))
    pub.sort(key=lambda e: (e["backend"], e["topic"], e["source"]))
    con.sort(key=lambda e: (e["backend"], e["topic"], e["source"]))
    aggregates = _dedupe_aggregates(aggregates)
    return {
        "service_dir": str(service_dir),
        "files_scanned": len(files),
        "endpoints": endpoints,
        "downstream_sync": downstream,
        "storage": storage,
        "events_published": pub,
        "events_consumed": con,
        "aggregates": aggregates,
    }


def _dedupe_aggregates(aggregates: list[dict]) -> list[dict]:
    """Collapse duplicate aggregate findings: keep the highest-confidence entry per name."""
    by_name: dict[str, dict] = {}
    rank = {"high": 2, "medium": 1, "low": 0}
    for agg in aggregates:
        name = agg["name"]
        existing = by_name.get(name)
        if existing is None or rank[agg["confidence"]] > rank[existing["confidence"]]:
            by_name[name] = agg
    return sorted(by_name.values(), key=lambda a: (a["name"], a["source"]))


_SERVICE_NAME_SUFFIXES = ("-service", "_service")


def _domain_from_service_name(name: str) -> str:
    """`geo-service` → `geo`, `task_service` → `task`, `geo` → `geo`."""
    n = name
    for suf in _SERVICE_NAME_SUFFIXES:
        if n.endswith(suf):
            return n[: -len(suf)]
    return n


_CONSUMER_DIR_MARKERS = ("services", "cmd", "apps")


def _detect_consumer_service(go_file: Path, repo_root: Path) -> str:
    """Walk go_file path against repo_root to find the owning service name.

    Recognises common monorepo layouts: `services/<name>/...`, `cmd/<name>/...`,
    `apps/<name>/...`. Falls back to the top-level directory under repo_root.
    """
    rel_parts = go_file.relative_to(repo_root).parts
    for i, part in enumerate(rel_parts[:-1]):
        if part in _CONSUMER_DIR_MARKERS and i + 1 < len(rel_parts):
            return rel_parts[i + 1]
    return rel_parts[0] if rel_parts else go_file.parent.name


def _iter_repo_go_files(repo_root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(repo_root.rglob("*.go")):
        if p.name.endswith("_test.go"):
            continue
        if any(part in EXCLUDE_DIRS for part in p.relative_to(repo_root).parts[:-1]):
            continue
        out.append(p)
    return out


def reverse_scan(repo_root: Path, target: str) -> dict:
    """Discover consumers of ``target`` service in a monorepo.

    Heuristic: a Go file is a consumer if it imports a path ending in
    ``/<domain>/v1`` (where domain = target without `-service` suffix) and
    references at least one ``<alias>.<Method>Request{`` pattern.
    """
    domain = _domain_from_service_name(target)
    import_re = re.compile(
        r'(?:([A-Za-z_]\w*)\s+)?"[^"]*/' + re.escape(domain) + r'/v1"'
    )
    files = _iter_repo_go_files(repo_root)
    by_consumer: dict[str, dict] = {}
    for go_file in files:
        rel = go_file.relative_to(repo_root)
        # Skip the target's own directory.
        if target in rel.parts:
            continue
        text = go_file.read_text(encoding="utf-8", errors="replace")
        m_import = import_re.search(text)
        if m_import is None:
            continue
        alias = m_import.group(1) or "v1"
        # Method names used via `<alias>.<Method>Request{` literal.
        method_re = re.compile(
            r'\b' + re.escape(alias) + r'\.([A-Z][A-Za-z0-9_]*)Request\b'
        )
        methods = sorted({m.group(1) for m in method_re.finditer(text)})
        consumer = _detect_consumer_service(go_file, repo_root)
        if consumer == target:
            continue
        entry = by_consumer.setdefault(
            consumer,
            {
                "name": consumer,
                "protocol": "gRPC",
                "endpoints_used": [],
                "source": f"{rel}:{_line_of(text, m_import.start())}",
                "confidence": "high" if methods else "medium",
                "discovered_via": "monorepo-scan",
            },
        )
        merged = sorted(set(entry["endpoints_used"]) | set(methods))
        entry["endpoints_used"] = merged
        if methods and entry["confidence"] != "high":
            entry["confidence"] = "high"
    consumers = sorted(by_consumer.values(), key=lambda c: c["name"])
    return {
        "repo_root": str(repo_root),
        "target": target,
        "files_scanned": len(files),
        "consumers": consumers,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="archspec Go scanner")
    parser.add_argument(
        "service_dir",
        type=Path,
        nargs="?",
        help="Path to the Go service root (forward scan)",
    )
    parser.add_argument(
        "--reverse-scan",
        type=Path,
        metavar="REPO_ROOT",
        help="Run reverse scan over a monorepo to discover consumers of --target",
    )
    parser.add_argument(
        "--target",
        type=str,
        help="Target service name for reverse scan (e.g. geo-service)",
    )
    args = parser.parse_args(argv)

    if args.reverse_scan is not None:
        if args.target is None:
            print("error: --reverse-scan requires --target", file=sys.stderr)
            return 2
        if not args.reverse_scan.is_dir():
            print(f"error: not a directory: {args.reverse_scan}", file=sys.stderr)
            return 2
        report = reverse_scan(args.reverse_scan, args.target)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.service_dir is None:
        parser.print_usage(sys.stderr)
        return 2
    if not args.service_dir.is_dir():
        print(f"error: not a directory: {args.service_dir}", file=sys.stderr)
        return 2
    report = scan(args.service_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
