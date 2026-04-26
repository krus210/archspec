"""Shared helpers for archspec benchmark suites."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_REPO_ROOT_MARKER = "benchmarks"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / _REPO_ROOT_MARKER).is_dir() and (parent / "skills").is_dir():
            return parent
    raise RuntimeError("could not locate archspec repo root")


def results_dir() -> Path:
    override = os.environ.get("ARCHSPEC_BENCHMARK_RESULTS")
    target = Path(override) if override else repo_root() / "benchmarks" / "results"
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json_report(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
