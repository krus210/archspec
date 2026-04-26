"""Structured findings emitted by archspec deterministic checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["BLOCK", "WARN", "INFO", "AUTO-FIX"]


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    file: str = ""
    line: int = 0
    fix_hint: str = ""


def has_blockers(findings: list[Finding]) -> bool:
    return any(f.severity == "BLOCK" for f in findings)


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "archspec pre-commit: OK"
    lines = ["archspec pre-commit:"]
    counts = {"BLOCK": 0, "WARN": 0, "INFO": 0, "AUTO-FIX": 0}
    for f in findings:
        counts[f.severity] += 1
    summary = ", ".join(f"{n} {sev}" for sev, n in counts.items() if n)
    lines.append(f"  {summary}")
    for f in sorted(findings, key=lambda x: (x.severity != "BLOCK", x.rule, x.file, x.line)):
        loc = f"{f.file}:{f.line}" if f.file else "-"
        lines.append(f"  {f.severity} {f.rule}  {loc}  {f.message}")
        if f.fix_hint:
            lines.append(f"    hint: {f.fix_hint}")
    return "\n".join(lines)
