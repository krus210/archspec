"""Validate a SERVICE_MAP.yaml file against the JSON Schema.

Exit codes:
  0 — valid (warnings may be printed to stderr)
  1 — invalid (schema or YAML parse error, or DET-006 in strict mode)
  2 — usage error (missing/unreadable file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "servicemap.schema.json"

_TODO_LITERAL = "TODO"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _format_error(err: jsonschema.ValidationError) -> str:
    path = "/".join(str(p) for p in err.absolute_path) or "<root>"
    return f"  - {path}: {err.message}"


def _todo_jsonpaths(doc: dict[str, Any]) -> list[str]:
    """Required-concrete fields where a literal TODO is meaningful enough to flag."""
    paths: list[str] = []
    api = doc.get("api") or {}
    for i, ep in enumerate(api.get("endpoints") or []):
        if ep.get("contract") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].contract")
        sla = ep.get("sla") or {}
        if sla.get("p99_latency") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].sla.p99_latency")
        if sla.get("availability") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].sla.availability")
    deps = doc.get("dependencies") or {}
    for i, d in enumerate((deps.get("downstream") or {}).get("sync") or []):
        if d.get("timeout") == _TODO_LITERAL:
            paths.append(f"dependencies.downstream.sync[{i}].timeout")
    for i, s in enumerate(deps.get("storage") or []):
        if s.get("name") == _TODO_LITERAL:
            paths.append(f"dependencies.storage[{i}].name")
    events = doc.get("events") or {}
    for i, e in enumerate(events.get("published") or []):
        if e.get("contract") == _TODO_LITERAL:
            paths.append(f"events.published[{i}].contract")
    for i, e in enumerate(events.get("consumed") or []):
        if e.get("contract") == _TODO_LITERAL:
            paths.append(f"events.consumed[{i}].contract")
    return paths


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
    if errors:
        print(f"DET-001: {yaml_path} does not conform to schema:")
        for err in errors:
            print(_format_error(err))
        return 1

    todo_paths = _todo_jsonpaths(doc) if isinstance(doc, dict) else []
    if not todo_paths:
        return 0

    strict = bool(((doc or {}).get("metadata") or {}).get("archspec_strict"))
    severity = "BLOCK" if strict else "WARN"
    for jsonpath in todo_paths:
        print(
            f"{severity} DET-006: TODO at {jsonpath} — replace before deploy",
            file=sys.stderr,
        )
    return 1 if strict else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate SERVICE_MAP.yaml")
    parser.add_argument("path", type=Path, help="Path to SERVICE_MAP.yaml")
    args = parser.parse_args(argv)
    return validate(args.path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
