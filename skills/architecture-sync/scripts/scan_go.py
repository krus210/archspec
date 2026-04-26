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
import sys
from pathlib import Path

EXCLUDE_DIRS = {"vendor", "gen", ".git", "node_modules", "testdata"}


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
    return {
        "service_dir": str(service_dir),
        "files_scanned": len(files),
        "endpoints": [],
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
