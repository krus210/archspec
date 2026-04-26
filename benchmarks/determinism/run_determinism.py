"""Determinism benchmark: every input must hash identically across N runs."""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

from benchmarks._common import repo_root, results_dir, write_json_report

DEFAULT_RUNS = 20
INPUTS_SUBDIR = Path("benchmarks/determinism/inputs")


def _ensure_sync_on_path() -> None:
    sync_scripts = repo_root() / "skills" / "architecture-sync" / "scripts"
    if str(sync_scripts) not in sys.path:
        sys.path.insert(0, str(sync_scripts))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_outputs(yaml_path: Path, output_dir: Path) -> dict[str, Path]:
    """Run the Plan 02 sync entry point, then enumerate written outputs by relative name."""
    _ensure_sync_on_path()
    from sync import sync  # Plan 02 entry point

    output_dir.mkdir(parents=True, exist_ok=True)
    sync(yaml_path, output_dir)

    outputs: dict[str, Path] = {}
    diagrams_dir = output_dir / "diagrams"
    if diagrams_dir.is_dir():
        for mmd in sorted(diagrams_dir.glob("*.mmd")):
            outputs[f"diagrams/{mmd.name}"] = mmd
    arch = output_dir / "ARCHITECTURE.md"
    if arch.is_file():
        outputs["ARCHITECTURE.md"] = arch
    return outputs


def run_determinism_suite(*, results_path: Path, runs: int = DEFAULT_RUNS) -> dict:
    inputs_dir = repo_root() / INPUTS_SUBDIR
    inputs = sorted(inputs_dir.glob("*.yaml"))

    suite_status = "pass"
    input_reports: list[dict] = []

    for yaml_path in inputs:
        per_output_hashes: dict[str, list[str]] = {}
        for _ in range(runs):
            with tempfile.TemporaryDirectory() as td:
                outputs = _generate_outputs(yaml_path, Path(td))
                for name, out_path in outputs.items():
                    per_output_hashes.setdefault(name, []).append(_hash_file(out_path))
        unique_per_output = {k: sorted(set(v)) for k, v in per_output_hashes.items()}
        input_status = "pass" if all(len(v) == 1 for v in unique_per_output.values()) else "fail"
        if input_status == "fail":
            suite_status = "fail"
        input_reports.append({
            "name": yaml_path.stem,
            "status": input_status,
            "per_output_hashes": per_output_hashes,
            "unique_hashes_per_output": unique_per_output,
        })

    report = {
        "suite": "determinism",
        "status": suite_status,
        "runs_per_input": runs,
        "inputs": input_reports,
    }
    write_json_report(results_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="archspec determinism benchmark")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--out", type=Path, default=results_dir() / "determinism.json")
    args = parser.parse_args()
    report = run_determinism_suite(results_path=args.out, runs=args.runs)
    print(
        f"determinism: {report['status']} "
        f"({len(report['inputs'])} inputs, {args.runs} runs each)"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
