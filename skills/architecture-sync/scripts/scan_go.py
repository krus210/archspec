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
        out.append(
            {
                "kind": "endpoint",
                "protocol": "gRPC",
                "method": "RPC",
                "name": name,
                "path": name,
                "source": f"{rel}:{_line_of(text, m.start())}",
                "confidence": "high",
            }
        )
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
    for f in files:
        endpoints.extend(_scan_http_endpoints(f, service_dir))
        endpoints.extend(_scan_grpc_endpoints(f, service_dir))
    endpoints.sort(key=lambda e: (e["protocol"], e["method"], e.get("path", ""), e["source"]))
    return {
        "service_dir": str(service_dir),
        "files_scanned": len(files),
        "endpoints": endpoints,
        "downstream_sync": [],
        "storage": [],
        "events_published": [],
        "events_consumed": [],
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
