"""Violations benchmark.

Each fixture's expected.json must match actual linter output (F1 >= 0.95).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from benchmarks._common import repo_root, results_dir, write_json_report

FIXTURES_SUBDIR = Path("benchmarks/violations/fixtures")
F1_THRESHOLD = 0.95
SUBCOMMANDS = ("handler-idempotency", "outbox-pattern", "optimistic-locking")


def _finding_key(finding: dict) -> tuple:
    return (finding["rule"], finding["file"], int(finding["line"]))


def compute_metrics(*, expected: list[dict], actual: list[dict]) -> dict:
    expected_keys = {_finding_key(f) for f in expected}
    actual_keys = {_finding_key(f) for f in actual}

    tp = len(expected_keys & actual_keys)
    fp = len(actual_keys - expected_keys)
    fn = len(expected_keys - actual_keys)

    if tp + fp == 0 and tp + fn == 0:
        precision = recall = f1 = 1.0
    else:
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def _run_go_linter(fixture: Path) -> list[dict]:
    """Invoke all three Plan 05 subcommands and aggregate findings.

    The Go module is rooted at ``linters/go``, so we set cwd there and use
    ``.`` as the package; absolute paths to the fixture remain valid.
    """
    linter_dir = repo_root() / "linters" / "go"
    findings: list[dict] = []
    sm = fixture / "SERVICE_MAP.yaml"
    code = fixture / "code"
    for sub in SUBCOMMANDS:
        cmd = ["go", "run", ".", sub,
               "--service-map", str(sm),
               "--code", str(code)]
        proc = subprocess.run(
            cmd, cwd=str(linter_dir), capture_output=True, text=True, check=False
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"go linter {sub} failed: rc={proc.returncode} stderr={proc.stderr!r}"
            )
        if proc.stdout.strip():
            try:
                findings.extend(json.loads(proc.stdout))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"go linter {sub} returned non-JSON: {proc.stdout!r}"
                ) from exc
    return findings


def _load_expected(fixture: Path) -> list[dict]:
    expected_path = fixture / "expected.json"
    if not expected_path.is_file():
        return []
    return json.loads(expected_path.read_text(encoding="utf-8"))


def run_violations_suite(*, results_path: Path, threshold: float = F1_THRESHOLD) -> dict:
    root = repo_root()
    fixtures_root = root / FIXTURES_SUBDIR
    if fixtures_root.is_dir():
        fixtures = sorted(p for p in fixtures_root.iterdir() if p.is_dir())
    else:
        fixtures = []

    fixture_reports: list[dict] = []
    suite_status = "pass"

    for fixture in fixtures:
        expected = _load_expected(fixture)
        try:
            actual = _run_go_linter(fixture)
        except Exception as exc:  # noqa: BLE001 — surface any subprocess error in the report
            fixture_reports.append({"name": fixture.name, "status": "fail", "error": str(exc)})
            suite_status = "fail"
            continue
        metrics = compute_metrics(expected=expected, actual=actual)
        status = "pass" if metrics["f1"] >= threshold else "fail"
        if status == "fail":
            suite_status = "fail"
        fixture_reports.append({
            "name": fixture.name,
            "status": status,
            "metrics": metrics,
            "expected_count": len(expected),
            "actual_count": len(actual),
        })

    report = {
        "suite": "violations",
        "status": suite_status,
        "threshold_f1": threshold,
        "fixtures": fixture_reports,
        "fixture_count": len(fixtures),
    }
    write_json_report(results_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="archspec violations benchmark")
    parser.add_argument("--threshold", type=float, default=F1_THRESHOLD)
    parser.add_argument("--out", type=Path, default=results_dir() / "violations.json")
    args = parser.parse_args()
    report = run_violations_suite(results_path=args.out, threshold=args.threshold)
    print(
        f"violations: {report['status']} "
        f"({report['fixture_count']} fixtures, threshold F1>={args.threshold})"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
