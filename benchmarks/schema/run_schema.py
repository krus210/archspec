"""Schema benchmark.

Valid YAMLs must validate against the SERVICE_MAP schema; invalid YAMLs must
fail with an error containing the expected substring from their .expected.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

from benchmarks._common import repo_root, results_dir, write_json_report

VALID_SUBDIR = Path("benchmarks/schema/valid_yamls")
INVALID_SUBDIR = Path("benchmarks/schema/invalid_yamls")
SCHEMA_PATH = Path("skills/architecture-sync/schema/servicemap.schema.json")


def _validator():
    schema = json.loads((repo_root() / SCHEMA_PATH).read_text(encoding="utf-8"))
    return jsonschema.Draft7Validator(schema)


def _validate(yaml_path: Path) -> tuple[bool, str]:
    try:
        doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return False, f"YAML parse error: {exc}"
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(e.absolute_path))
    if not errors:
        return True, ""
    msgs = []
    for err in errors:
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        msgs.append(f"{path}: {err.message}")
    return False, "; ".join(msgs)


def _run_valid(root: Path) -> list[dict]:
    out: list[dict] = []
    for yaml_path in sorted(root.glob("*.yaml")):
        ok, msg = _validate(yaml_path)
        out.append({
            "name": yaml_path.stem,
            "status": "pass" if ok else "fail",
            "error": msg if not ok else None,
        })
    return out


def _run_invalid(root: Path) -> list[dict]:
    out: list[dict] = []
    for yaml_path in sorted(root.glob("*.yaml")):
        expected_path = yaml_path.with_suffix(".expected.json")
        if not expected_path.is_file():
            out.append({
                "name": yaml_path.stem,
                "status": "fail",
                "error": f"missing expected json at {expected_path}",
            })
            continue
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        ok, msg = _validate(yaml_path)
        if ok:
            out.append({
                "name": yaml_path.stem,
                "status": "fail",
                "expected_error_code": expected["expected_error_code"],
                "error": "fixture validated unexpectedly",
            })
            continue
        needle = expected["expected_message_contains"]
        status = "pass" if needle in msg else "fail"
        out.append({
            "name": yaml_path.stem,
            "status": status,
            "expected_error_code": expected["expected_error_code"],
            "expected_message_contains": needle,
            "actual_error": msg,
        })
    return out


def run_schema_suite(*, results_path: Path) -> dict:
    root = repo_root()
    valid = _run_valid(root / VALID_SUBDIR)
    invalid = _run_invalid(root / INVALID_SUBDIR)
    suite_status = "pass" if all(e["status"] == "pass" for e in valid + invalid) else "fail"
    report = {
        "suite": "schema",
        "status": suite_status,
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid": valid,
        "invalid": invalid,
    }
    write_json_report(results_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="archspec schema benchmark")
    parser.add_argument("--out", type=Path, default=results_dir() / "schema.json")
    args = parser.parse_args()
    report = run_schema_suite(results_path=args.out)
    print(
        f"schema: {report['status']} "
        f"({report['valid_count']} valid, {report['invalid_count']} invalid)"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
