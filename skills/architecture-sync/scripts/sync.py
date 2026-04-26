"""archspec sync: regenerate diagrams and ARCHITECTURE.md from SERVICE_MAP.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import apply_managed_region, read_yaml, write_text_atomic
from generate_mermaid import generate_container, generate_context, generate_sequence
from render_architecture_md import render_architecture_md


def sync(yaml_path: Path, docs_dir: Path) -> None:
    doc = read_yaml(yaml_path)
    diagrams = docs_dir / "diagrams"
    write_text_atomic(diagrams / "context.mmd", generate_context(doc))
    write_text_atomic(diagrams / "container.mmd", generate_container(doc))
    write_text_atomic(diagrams / "sequence.mmd", generate_sequence(doc))
    arch_path = docs_dir / "ARCHITECTURE.md"
    write_text_atomic(arch_path, apply_managed_region(arch_path, render_architecture_md(doc)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("yaml", type=Path)
    parser.add_argument("docs_dir", type=Path)
    args = parser.parse_args(argv)
    sync(args.yaml, args.docs_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
