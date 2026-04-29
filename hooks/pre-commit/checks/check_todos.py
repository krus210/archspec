"""DET-006: literal "TODO" left in fields that are required to be concrete.

WARN by default — coexists with in-progress specs. Becomes BLOCK only if the
SERVICE_MAP.yaml opts in via ``metadata.archspec_strict: true``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

_TODO_LITERAL = "TODO"


def _todo_jsonpaths(doc: dict[str, Any]) -> list[str]:
    """Return jsonpath strings for every required-concrete field equal to TODO."""
    paths: list[str] = []
    api = doc.get("api") or {}
    for i, ep in enumerate(api.get("endpoints") or []):
        if ep.get("contract") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].contract")
        sla = ep.get("sla") or {}
        if sla.get("p99_latency") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].sla.p99_latency")
        if sla.get("availability") == _TODO_LITERAL:
            paths.append(f"api.endpoints[{i}].sla.availability")
    deps = doc.get("dependencies") or {}
    for i, d in enumerate((deps.get("downstream") or {}).get("sync") or []):
        if d.get("timeout") == _TODO_LITERAL:
            paths.append(f"dependencies.downstream.sync[{i}].timeout")
    for i, s in enumerate(deps.get("storage") or []):
        if s.get("name") == _TODO_LITERAL:
            paths.append(f"dependencies.storage[{i}].name")
    events = doc.get("events") or {}
    for i, e in enumerate(events.get("published") or []):
        if e.get("contract") == _TODO_LITERAL:
            paths.append(f"events.published[{i}].contract")
    for i, e in enumerate(events.get("consumed") or []):
        if e.get("contract") == _TODO_LITERAL:
            paths.append(f"events.consumed[{i}].contract")
    return paths


def _is_strict(doc: dict[str, Any]) -> bool:
    return bool((doc.get("metadata") or {}).get("archspec_strict"))


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in (s for s in staged if s.endswith("SERVICE_MAP.yaml")):
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd))
        except yaml.YAMLError:
            continue  # DET-001 will surface this
        if not doc:
            continue
        severity = "BLOCK" if _is_strict(doc) else "WARN"
        for jsonpath in _todo_jsonpaths(doc):
            findings.append(
                Finding(
                    "DET-006",
                    severity,
                    f"TODO at {jsonpath} — replace before deploy",
                    file=path,
                )
            )
    return findings
