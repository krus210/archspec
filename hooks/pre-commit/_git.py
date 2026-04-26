"""Thin wrappers around git plumbing used by deterministic checks."""

from __future__ import annotations

import subprocess
from pathlib import Path


def staged_files(cwd: Path | None = None) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
        check=True, capture_output=True, text=True, cwd=cwd,
    ).stdout
    return [ln for ln in out.splitlines() if ln]


def staged_blob(path: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", "show", f":{path}"],
        check=True, capture_output=True, text=True, cwd=cwd,
    ).stdout


def head_blob(path: str, cwd: Path | None = None) -> str | None:
    r = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        capture_output=True, text=True, cwd=cwd,
    )
    return r.stdout if r.returncode == 0 else None
