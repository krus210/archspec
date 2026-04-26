# Extending archspec

archspec ships with a Go linter on day one. The architecture is designed
so that adding a linter for another language (Python, Node, Java, Rust,
Kotlin, ...) does not require any change to the core schema, hooks, or
templates.

This document covers:

1. Where new linters live and how they activate.
2. The JSON contract every linter must produce.
3. The `<lang>_extensions` block that lets a linter read
   language-specific configuration without a schema PR.
4. A complete worked example: contributing `linters/python/` with one
   `AI-001` (idempotency) check.

---

## 1. Folder layout

```
linters/
├── go/                       (ships day one)
│   ├── README.md
│   ├── main.go
│   ├── handler_idempotency.go
│   ├── outbox_pattern.go
│   ├── optimistic_locking.go
│   └── testdata/
└── <your-language>/          (add yours here)
    ├── README.md
    ├── ...                   (any language and build system)
    └── testdata/
```

There are no naming requirements beyond the directory name itself,
because activation is data-driven (see next section). Use whatever
language tooling you prefer. The Go linter is a Go binary invoked via
`go run`; a Python linter would be a script invoked via `python3 -m`;
Node would be `node`. The only contract is the JSON output (section 3).

---

## 2. Activation

A linter activates when `service.language` in the target service's
`SERVICE_MAP.yaml` matches the directory name.

```yaml
service:
  language: python      # → /archspec:validate runs linters/python/
```

The validate skill iterates over `linters/<lang>/` for whichever
language the YAML declares, then aggregates findings into a single
report. There is no central registry to update; dropping a directory in
the right place is enough.

A service may declare any string for `service.language`. If the
matching directory does not exist, `/archspec:validate` reports
"language `<lang>` has no linter installed" but does not fail. The
deterministic layer (`DET-001..015`) still runs because it is
language-agnostic.

---

## 3. The JSON Finding contract

Every linter writes a JSON array of `Finding` objects to stdout. This
schema is taken verbatim from the design spec §4.5:

```json
{
  "rule": "AI-001",
  "severity": "BLOCK",
  "file": "internal/handler/listing_create.go",
  "line": 42,
  "contract_ref": "SERVICE_MAP.yaml:78",
  "message": "...",
  "suggested_fix": "..."
}
```

Field semantics:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `rule` | string | yes | Stable id (`AI-001` etc.); reserve new ids in [`VALIDATION_RULES.md`](./VALIDATION_RULES.md) before shipping. |
| `severity` | string | yes | One of `BLOCK`, `WARN`, `INFO`. |
| `file` | string | yes when applicable | Repo-relative path. Empty string is allowed for whole-service findings (e.g. "no handler matches endpoint"). |
| `line` | integer | yes when applicable | 1-based. Use `0` when the finding is file- or service-level. |
| `contract_ref` | string | yes | Cross-reference to the YAML section that motivated the rule. Format: `SERVICE_MAP.yaml — <pointer>`. |
| `message` | string | yes | One-line description of the violation. |
| `suggested_fix` | string | optional | If present, surfaced as the fix hint in the validate report. |

Output rules:

- Always emit a JSON array, never `null`. An empty array means "no
  findings".
- Use UTF-8, LF line endings, no BOM.
- Do not pretty-print with timestamps, colors, or other entropy. The
  benchmarks in `benchmarks/violations/` will compare your output
  byte-for-byte against `expected.json`.
- Sort by `(file, line, rule)` so two runs against the same input
  produce the same output. The Go reference linter relies on AST
  traversal order, which is already sorted.

Exit codes:

- `0` — no findings emitted.
- `1` — at least one finding emitted (any severity).
- `2` — usage error (bad flags, missing input).

Other exit codes are reserved.

---

## 4. The `<lang>_extensions` block

Language-specific configuration that does not belong in the
language-agnostic schema lives in a top-level `<prefix>_extensions`
object. The schema permits any object whose key matches `*_extensions$`
(see `skills/architecture-sync/schema/servicemap.schema.json`,
`patternProperties`).

By convention, the prefix matches `service.language`:

```yaml
service:
  language: python

python_extensions:
  framework: fastapi
  idempotency_decorator: "@idempotent"
  outbox_helper: "events.OutboxPublisher"
```

The Go linter's reference shape:

```yaml
go_extensions:
  optimistic_locking_field: "row_version"
  outbox_table: "outbox_events"
```

Linters are responsible for declaring their own defaults. The schema
does not validate the contents of an `*_extensions` block (it is
`additionalProperties: true`), so document expected keys in your
linter's `README.md`. Users with conflicting keys across multiple
linters can use distinct prefixes (e.g.
`python_idempotency_extensions`).

---

## 5. Worked example: `linters/python/handler_idempotency.py`

This walkthrough adds a single rule (`AI-001`) for Python services
using FastAPI. It mirrors the Go reference implementation in
`linters/go/handler_idempotency.go`.

### 5.1 Scaffolding

```
linters/python/
├── README.md
├── archspec_python_linter/
│   ├── __init__.py
│   ├── __main__.py
│   ├── finding.py
│   ├── servicemap.py
│   └── handler_idempotency.py
├── pyproject.toml
└── testdata/
    └── handler_idempotency/
        ├── ok/
        │   ├── SERVICE_MAP.yaml
        │   └── app.py
        └── bad/
            ├── SERVICE_MAP.yaml
            └── app.py
```

### 5.2 `finding.py`

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    contract_ref: str
    message: str
    suggested_fix: str = ""


def encode_findings(findings: list[Finding]) -> str:
    """Sort, then emit a JSON array. Never None, no trailing newline."""
    findings = sorted(findings, key=lambda f: (f.file, f.line, f.rule))
    return json.dumps([asdict(f) for f in findings], ensure_ascii=False)
```

### 5.3 `servicemap.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Idempotency:
    required: bool = False
    key_source: str = ""
    storage: str = ""


@dataclass
class Endpoint:
    name: str = ""
    protocol: str = ""
    idempotency: Idempotency = field(default_factory=Idempotency)


@dataclass
class ServiceMap:
    path: str
    language: str
    endpoints: list[Endpoint]
    extensions: dict


def load(path: str | Path) -> ServiceMap:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    endpoints = []
    for ep in (raw.get("api") or {}).get("endpoints", []) or []:
        idem = ep.get("idempotency") or {}
        endpoints.append(Endpoint(
            name=ep.get("name", ""),
            protocol=ep.get("protocol", ""),
            idempotency=Idempotency(
                required=bool(idem.get("required")),
                key_source=idem.get("key_source", ""),
                storage=idem.get("storage", ""),
            ),
        ))
    return ServiceMap(
        path=str(path),
        language=(raw.get("service") or {}).get("language", ""),
        endpoints=endpoints,
        extensions=raw.get("python_extensions") or {},
    )
```

### 5.4 `handler_idempotency.py` (the rule)

The check uses `ast.NodeVisitor` to find every function whose name
matches a declared endpoint, then walks its body for
`request.headers.get("<header>")` calls.

```python
from __future__ import annotations

import ast
from pathlib import Path

from .finding import Finding
from .servicemap import Endpoint, ServiceMap


_HEADER_PREFIX = "header:"


def _header_name(key_source: str) -> str:
    """`header: X-Idempotency-Key` -> `x-idempotency-key`."""
    if not key_source.lower().startswith(_HEADER_PREFIX):
        return ""
    return key_source.split(":", 1)[1].strip().lower()


class _HandlerScanner(ast.NodeVisitor):
    def __init__(self, header: str) -> None:
        self.header = header
        self.reads_header = False

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # request.headers.get("X-Idempotency-Key") or
        # request.headers["X-Idempotency-Key"]
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "headers"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.lower() == self.header
        ):
            self.reads_header = True
        self.generic_visit(node)


def _walk_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "/.venv/" not in str(p))


def run(sm: ServiceMap, code_root: Path) -> list[Finding]:
    required: list[Endpoint] = [e for e in sm.endpoints if e.idempotency.required]
    if not required:
        return []

    handlers: dict[str, tuple[Path, int]] = {}
    bodies: dict[str, ast.FunctionDef] = {}
    for path in _walk_python_files(code_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                handlers.setdefault(node.name, (path, node.lineno))
                bodies.setdefault(node.name, node)

    findings: list[Finding] = []
    for ep in required:
        header = _header_name(ep.idempotency.key_source)
        body = bodies.get(ep.name)
        if body is None:
            findings.append(Finding(
                rule="AI-001", severity="BLOCK",
                file="", line=0,
                contract_ref=f"{sm.path} — endpoint {ep.name}",
                message=(
                    "endpoint declared idempotency.required=true "
                    "but no matching handler function found"
                ),
                suggested_fix=(
                    f"name the handler function exactly `{ep.name}` "
                    "or add a registration mapping"
                ),
            ))
            continue
        scanner = _HandlerScanner(header)
        scanner.visit(body)
        if header and not scanner.reads_header:
            path, lineno = handlers[ep.name]
            findings.append(Finding(
                rule="AI-001", severity="BLOCK",
                file=str(path.relative_to(code_root)),
                line=lineno,
                contract_ref=f"{sm.path} — endpoint {ep.name}",
                message=f"handler does not read declared idempotency key {header}",
                suggested_fix=(
                    f'key = request.headers.get("{header}")'
                ),
            ))
    return findings
```

### 5.5 `__main__.py` (CLI)

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .finding import encode_findings
from .handler_idempotency import run as run_handler_idempotency
from .servicemap import load


_SUBCOMMANDS = {"handler-idempotency": run_handler_idempotency}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archspec-python-linter")
    parser.add_argument("subcommand", choices=sorted(_SUBCOMMANDS))
    parser.add_argument("--service-map", default="docs/SERVICE_MAP.yaml")
    parser.add_argument("--code", default=".")
    args = parser.parse_args(argv)

    sm = load(args.service_map)
    findings = _SUBCOMMANDS[args.subcommand](sm, Path(args.code))
    sys.stdout.write(encode_findings(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### 5.6 Fixture: `testdata/handler_idempotency/bad/`

`SERVICE_MAP.yaml`:

```yaml
metadata:
  schema_version: "1.0"
  source_of_truth: local
  drift_check_in_ci: true
  last_reviewed: "2026-04-25"
service:
  name: orders
  team: payments
  language: python
  repo: github.com/example/orders
  domain: orders
  ownership: { primary: "@alice", oncall: "@oncall" }
  responsibilities: ["accept order requests"]
  invariants: ["idempotent create"]
api:
  version: 1
  endpoints:
    - name: create_order
      protocol: HTTP
      idempotency:
        required: true
        key_source: "header: X-Idempotency-Key"
        storage: redis
      contract: "openapi/orders.yaml#/paths/~1orders/post"
      sla: { p99_latency: "200ms", availability: "99.9%" }
  changelog: []
dependencies:
  upstream: []
  downstream: { sync: [], async: [] }
  storage: []
events: { published: [], consumed: [] }
consistency:
  model: eventual
  bounded_aggregate: order
  write_path: { pattern: outbox }
  read_path: { consistency: eventual }
  cross_service_invariants: []
concurrency: { aggregates: [], hot_keys: [], shared_state: [] }
```

`app.py` (handler does not read the header, so the rule must fire):

```python
from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/orders")
async def create_order(request: Request):
    payload = await request.json()
    return {"id": payload.get("id")}
```

Expected output (`expected.json`):

```json
[
  {
    "rule": "AI-001",
    "severity": "BLOCK",
    "file": "app.py",
    "line": 6,
    "contract_ref": "testdata/handler_idempotency/bad/SERVICE_MAP.yaml — endpoint create_order",
    "message": "handler does not read declared idempotency key x-idempotency-key",
    "suggested_fix": "key = request.headers.get(\"x-idempotency-key\")"
  }
]
```

Mirror the layout for the `ok/` case (handler that calls
`request.headers.get("X-Idempotency-Key")` returns an empty array).

### 5.7 Wire into the validate skill

Once the linter passes its own tests, register the language directory
by creating `linters/python/README.md`. The validate skill discovers
linters by directory name; no other registration is needed.

In a follow-up PR, add a benchmark fixture under
`benchmarks/violations/fixtures/<NN>_python_handler_idempotency/` so
the F1 metric covers the new rule.

---

## See also

- [`SERVICE_MAP_SPEC.md`](./SERVICE_MAP_SPEC.md) — every key your
  linter is allowed to read.
- [`VALIDATION_RULES.md`](./VALIDATION_RULES.md) — reserve new `AI-*`
  ids here before shipping.
- [`EXCEPTIONS.md`](./EXCEPTIONS.md) — how users will suppress your
  rules.
- `linters/go/` — reference implementation; mirror its directory
  layout if your language has no strong convention.
