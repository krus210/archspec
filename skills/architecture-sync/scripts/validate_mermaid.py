"""Sanity-check generated Mermaid files.

Not a full parser — only catches the failure modes our generators could plausibly produce.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KNOWN_HEADERS = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram")


class MermaidError(Exception):
    pass


def validate_mermaid_text(text: str) -> None:
    stripped = text.strip()
    if not stripped:
        raise MermaidError("empty mermaid file")
    body_lines = [
        ln for ln in stripped.splitlines() if ln.strip() and not ln.lstrip().startswith("%%")
    ]
    if not body_lines:
        raise MermaidError("empty mermaid file (only comments)")
    first = body_lines[0].lstrip()
    if not any(first.startswith(h) for h in KNOWN_HEADERS):
        raise MermaidError(f"unknown diagram type: {first!r}")
    opens = sum(1 for ln in body_lines if ln.strip().startswith("subgraph "))
    closes = sum(1 for ln in body_lines if ln.strip() == "end")
    if opens != closes:
        raise MermaidError(f"unbalanced subgraph blocks: {opens} open vs {closes} end")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = 0
    for p in args.paths:
        try:
            validate_mermaid_text(p.read_text(encoding="utf-8"))
        except MermaidError as e:
            print(f"{p}: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
