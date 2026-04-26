"""DET-002: no self-loops or duplicates in dependencies.downstream.sync."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    targets = [s for s in staged if s.endswith("SERVICE_MAP.yaml")]
    findings: list[Finding] = []
    for path in targets:
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd))
        except yaml.YAMLError:
            continue  # DET-001 will report
        if not doc:
            continue
        own = (doc.get("service") or {}).get("name", "")
        sync = ((doc.get("dependencies") or {}).get("downstream") or {}).get("sync") or []
        names = [d.get("service") for d in sync if isinstance(d, dict)]
        if own and own in names:
            findings.append(
                Finding("DET-002", "BLOCK", f"self-loop: '{own}' depends on itself", file=path)
            )
        for name, count in Counter(names).items():
            if count > 1:
                findings.append(
                    Finding(
                        "DET-002",
                        "BLOCK",
                        f"duplicate downstream '{name}' (x{count})",
                        file=path,
                    )
                )
    return findings
