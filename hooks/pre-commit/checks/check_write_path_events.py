"""DEP-001: write_path pattern is consistent with declared events.

Two failure modes:

1. ``consistency.write_path.pattern == 'outbox'`` but ``events.published`` is
   empty — likely incomplete spec.
2. ``events.published`` is non-empty but ``consistency.write_path.pattern ==
   'direct'`` — at-least-once event delivery is not guaranteed because the
   state mutation and the publish are not atomic.

WARN by default. Promoted to BLOCK when ``metadata.archspec_strict: true``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

_OUTBOX_NO_EVENTS = (
    "outbox pattern declared but events.published is empty — "
    "likely incomplete spec; add events or switch pattern to direct"
)
_DIRECT_WITH_EVENTS = (
    "events.published declared with direct write path — no atomicity "
    "guarantee between state mutation and event emission; consider outbox"
)


def _is_strict(doc: dict[str, Any]) -> bool:
    return bool((doc.get("metadata") or {}).get("archspec_strict"))


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in (s for s in staged if s.endswith("SERVICE_MAP.yaml")):
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd))
        except yaml.YAMLError:
            continue
        if not doc:
            continue
        pattern = ((doc.get("consistency") or {}).get("write_path") or {}).get("pattern")
        published = (doc.get("events") or {}).get("published") or []
        severity = "BLOCK" if _is_strict(doc) else "WARN"
        if pattern == "outbox" and not published:
            findings.append(Finding("DEP-001", severity, _OUTBOX_NO_EVENTS, file=path))
        elif pattern == "direct" and published:
            findings.append(Finding("DEP-001", severity, _DIRECT_WITH_EVENTS, file=path))
    return findings
