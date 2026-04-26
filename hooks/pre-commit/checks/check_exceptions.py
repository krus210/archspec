"""DET-010..014: exceptions are well-formed, time-bounded, and reviewable.

Note: DET-012 (expired exceptions) accepts an injected `today` for testability.
The system clock is consulted only as a default — never as a determinism source.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

_TEMP_RE = re.compile(r"\b(migration|temporary|legacy)\b", re.IGNORECASE)


def _today_str(today: str | None) -> str:
    if today is not None:
        return today
    # Reading the wall clock here is the ONE place archspec is allowed to.
    import datetime as _dt  # noqa: PLC0415 — isolated import on purpose

    return _dt.date.today().isoformat()


def run(staged: list[str], cwd: Path | None = None, today: str | None = None) -> list[Finding]:
    repo = Path(cwd) if cwd else Path.cwd()
    findings: list[Finding] = []
    today_iso = _today_str(today)
    for path in (s for s in staged if s.endswith("SERVICE_MAP.yaml")):
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd)) or {}
        except yaml.YAMLError:
            continue
        for i, exc in enumerate(doc.get("exceptions") or []):
            loc = f"exceptions[{i}]"
            # DET-010
            if not exc.get("reason") or not exc.get("approved_by"):
                findings.append(Finding(
                    "DET-010", "BLOCK",
                    f"{loc}: every exception requires reason and approved_by", file=path,
                ))
            # DET-011
            adr = exc.get("adr")
            if not adr:
                findings.append(Finding(
                    "DET-011", "BLOCK", f"{loc}: missing adr link", file=path,
                ))
            elif not (repo / adr).exists():
                findings.append(Finding(
                    "DET-011", "BLOCK", f"{loc}: adr file not found: {adr}", file=path,
                ))
            # DET-012
            expires = exc.get("expires")
            if expires and expires < today_iso:
                findings.append(Finding(
                    "DET-012", "WARN",
                    f"{loc}: exception expired on {expires}", file=path,
                ))
            # DET-014
            if exc.get("reason") and _TEMP_RE.search(exc["reason"]) and not expires:
                findings.append(Finding(
                    "DET-014", "WARN",
                    f"{loc}: temporary exception without expires", file=path,
                ))
        # DET-013 (INFO) — surfaced by run_all_checks summary if any change in exceptions block
    return findings
