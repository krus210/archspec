"""Record `expected.json` for a violations fixture by running the linter against it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.violations.run_violations import _run_go_linter


def record_fixture(fixture_dir: Path) -> Path:
    if not (fixture_dir / "SERVICE_MAP.yaml").is_file():
        raise FileNotFoundError(f"missing SERVICE_MAP.yaml in {fixture_dir}")
    findings = _run_go_linter(fixture_dir)
    target = fixture_dir / "expected.json"
    target.write_text(
        json.dumps(findings, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="record expected.json for a violations fixture")
    parser.add_argument("fixture", type=Path, help="path to violations/fixtures/<NN_name>")
    args = parser.parse_args()
    target = record_fixture(args.fixture.resolve())
    print(f"recorded {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
