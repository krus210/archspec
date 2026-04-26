"""Aggregate pre-push checks: drift + contract changes. Exit 1 on any BLOCK."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_contract_changes import check_contract_changes
from check_drift import check_drift


def run_all(*, repo_root: Path, base_ref: str = "origin/main") -> int:
    findings = check_drift(repo_root=repo_root) + check_contract_changes(
        repo_root=repo_root, base_ref=base_ref,
    )
    blocking = [f for f in findings if f.severity == "BLOCK"]
    for f in findings:
        print(f"{f.severity} {f.rule} {f.file}: {f.message}", file=sys.stderr)
    return 1 if blocking else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="archspec pre-push checks")
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    return run_all(repo_root=Path.cwd(), base_ref=args.base_ref)


if __name__ == "__main__":
    raise SystemExit(main())
