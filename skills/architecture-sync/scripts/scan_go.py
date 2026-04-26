"""archspec Go scanner: discover architectural artefacts in Go source.

Scans a service directory's `*.go` files (excluding `_test.go`, `vendor/`,
`gen/`, `.git/`) and emits a JSON report describing endpoints, downstream
synchronous calls, storage clients, and messaging topics that the user should
record in `SERVICE_MAP.yaml`.

Read-only. Deterministic — same input ⇒ same JSON bytes.

CLI: scan_go.py <service_dir>

Exit codes:
  0 — scan completed (report on stdout, possibly with empty arrays)
  2 — usage error (missing/unreadable directory)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {"vendor", "gen", ".git", "node_modules", "testdata"}

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
    cursor = service_dir.resolve()
    for _ in range(_PROTO_LOOKUP_DEPTH):
        candidate_dir = cursor / "proto" / domain / "v1"
        if candidate_dir.is_dir():
            protos = sorted(candidate_dir.glob("*.proto"))
            if protos:
                try:
                    return str(protos[0].relative_to(service_dir.resolve()))
                except ValueError:
                    # Service is under a different subtree; emit absolute repo-rooted path.
                    return str(protos[0])
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return None

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


def _scan_nats(text: str, rel: Path, const_table: dict[str, str]) -> tuple[list[dict], list[dict]]:
    if "nats-io/nats.go" not in text and "nats.Connect" not in text and "jetstream." not in text:
        return [], []
    pub: list[dict] = []
    con: list[dict] = []

    def _emit(target: list[dict], pat: re.Pattern[str], confidence: str) -> None:
        for m in pat.finditer(text):
            subject = _resolve_subject(m.group(1), const_table)
            if subject is None:
                continue
            target.append({"kind": "event", "backend": "nats", "topic": subject,
                           "source": f"{rel}:{_line_of(text, m.start())}",
                           "confidence": confidence})

    _emit(pub, _NATS_PUBLISH, "medium")
    _emit(pub, _JETSTREAM_PUBLISH, "medium")
    _emit(con, _NATS_SUBSCRIBE, "medium")
    _emit(con, _NATS_QUEUE_SUBSCRIBE, "medium")
    return pub, con


_MESSAGING_BACKENDS = ("kafka", "nats")


def _scan_events(file: Path, root: Path) -> tuple[list[dict], list[dict]]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    const_table = _build_string_const_table(text)
    pub: list[dict] = []
    con: list[dict] = []
    if "kafka" in _MESSAGING_BACKENDS:
        kp, kc = _scan_kafka(text, rel)
        pub.extend(kp)
        con.extend(kc)
    if "nats" in _MESSAGING_BACKENDS:
        np, nc = _scan_nats(text, rel, const_table)
        pub.extend(np)
        con.extend(nc)
    seen: set[tuple[str, str, str]] = set()
    pub = [
        e for e in pub
        if (e["backend"], e["topic"], e["source"]) not in seen
        and not seen.add((e["backend"], e["topic"], e["source"]))
    ]
    seen.clear()
    con = [
        e for e in con
        if (e["backend"], e["topic"], e["source"]) not in seen
        and not seen.add((e["backend"], e["topic"], e["source"]))
    ]
    return pub, con


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
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    seen: set[str] = set()
    out: list[dict] = []
    for m in _GRPC_REGISTER_PATTERN.finditer(text):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        finding: dict = {
            "kind": "endpoint",
            "protocol": "gRPC",
            "method": "RPC",
            "name": name,
            "path": name,
            "source": f"{rel}:{_line_of(text, m.start())}",
            "confidence": "high",
        }
        contract = _find_proto_contract(root, _domain_from_grpc_server(name))
        if contract:
            finding["contract_hint"] = contract
        out.append(finding)
    return out


def _scan_http_endpoints(file: Path, root: Path) -> list[dict]:
    text = file.read_text(encoding="utf-8", errors="replace")
    rel = file.relative_to(root)
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for method, pat in _HTTP_PATTERNS:
        for m in pat.finditer(text):
            path = m.group(1)
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "kind": "endpoint",
                    "protocol": "HTTP",
                    "method": method,
                    "path": path,
                    "source": f"{rel}:{_line_of(text, m.start())}",
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
    for f in files:
        endpoints.extend(_scan_http_endpoints(f, service_dir))
        endpoints.extend(_scan_grpc_endpoints(f, service_dir))
        downstream.extend(_scan_downstream_sync(f, service_dir))
        storage.extend(_scan_storage(f, service_dir))
        p, c = _scan_events(f, service_dir)
        pub.extend(p)
        con.extend(c)
    endpoints.sort(key=lambda e: (e["protocol"], e["method"], e.get("path", ""), e["source"]))
    downstream.sort(key=lambda d: (d["service"], d["source"]))
    storage.sort(key=lambda s: (s["type"], s["source"]))
    pub.sort(key=lambda e: (e["backend"], e["topic"], e["source"]))
    con.sort(key=lambda e: (e["backend"], e["topic"], e["source"]))
    return {
        "service_dir": str(service_dir),
        "files_scanned": len(files),
        "endpoints": endpoints,
        "downstream_sync": downstream,
        "storage": storage,
        "events_published": pub,
        "events_consumed": con,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="archspec Go scanner")
    parser.add_argument("service_dir", type=Path, help="Path to the Go service root")
    args = parser.parse_args(argv)
    if not args.service_dir.is_dir():
        print(f"error: not a directory: {args.service_dir}", file=sys.stderr)
        return 2
    report = scan(args.service_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
