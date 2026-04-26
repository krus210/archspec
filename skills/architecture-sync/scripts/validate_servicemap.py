"""Validate a SERVICE_MAP.yaml file against the JSON Schema.

Exit codes:
  0 — valid
  1 — invalid (schema or YAML parse error)
  2 — usage error (missing/unreadable file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "servicemap.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _format_error(err: jsonschema.ValidationError) -> str:
    path = "/".join(str(p) for p in err.absolute_path) or "<root>"
    return f"  - {path}: {err.message}"


def validate(yaml_path: Path) -> int:
    if not yaml_path.is_file():
        print(f"error: file not found: {yaml_path}", file=sys.stderr)
        return 2
    try:
        doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"error: invalid YAML in {yaml_path}: {e}", file=sys.stderr)
        return 1

    validator = jsonschema.Draft7Validator(_load_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if not errors:
        return 0

    print(f"DET-001: {yaml_path} does not conform to schema:")
    for err in errors:
        print(_format_error(err))
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate SERVICE_MAP.yaml")
    parser.add_argument("path", type=Path, help="Path to SERVICE_MAP.yaml")
    args = parser.parse_args(argv)
    return validate(args.path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
