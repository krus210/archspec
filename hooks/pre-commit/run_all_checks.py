#!/usr/bin/env python3
"""archspec pre-commit runner. Exits 1 only on BLOCK; WARN/INFO/AUTO-FIX are reported but pass."""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _finding import Finding, format_report, has_blockers  # noqa: E402
from _git import staged_files  # noqa: E402
from checks import (  # noqa: E402
    check_breaking_changes,
    check_cycles,
    check_diagrams,
    check_exceptions,
    check_pragmas,
    check_references,
    check_schema,
)

_CHECKS = (
    check_schema,
    check_cycles,
    check_references,
    check_diagrams,
    check_breaking_changes,
    check_exceptions,
    check_pragmas,
)


def main() -> int:
    started = time.monotonic()
    staged = staged_files()
    findings: list[Finding] = []
    for mod in _CHECKS:
        findings.extend(mod.run(staged))
    print(format_report(findings))
    elapsed_ms = int((time.monotonic() - started) * 1000)
    print(f"  ({elapsed_ms} ms)")
    return 1 if has_blockers(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
