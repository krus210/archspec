"""Render ARCHITECTURE.md from SERVICE_MAP.yaml. Pure-functional, deterministic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import JINJA_ENV, read_yaml, write_text_atomic


def render_architecture_md(doc: dict, diagram_dir: str = "diagrams") -> str:
    return JINJA_ENV.get_template("architecture.md.j2").render(
        service=doc["service"],
        api=doc["api"],
        dependencies=doc["dependencies"],
        events=doc["events"],
        consistency=doc["consistency"],
        concurrency=doc["concurrency"],
        diagram_dir=diagram_dir,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--diagram-dir", default="diagrams")
    args = parser.parse_args(argv)
    text = render_architecture_md(read_yaml(args.yaml), args.diagram_dir)
    write_text_atomic(args.out, text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
