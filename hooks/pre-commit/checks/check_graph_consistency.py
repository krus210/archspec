"""DEP-002/003/004: cross-service graph consistency for monorepos.

Walks every ``**/SERVICE_MAP.yaml`` reachable from ``cwd`` (or the repo root in
pre-commit context) and emits WARN findings when the declared graph is
internally inconsistent. WARN only — never BLOCK, even with archspec_strict —
because false-positives are unavoidable (HTTP-only consumers, ingress, k8s,
legacy services without SERVICE_MAP).

Pairs are checked only when both sides have a SERVICE_MAP. If service B has no
SERVICE_MAP, A→B references are silent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402

_RULE_DOWNSTREAM_MISSING_UPSTREAM = "DEP-002"
_RULE_ORPHAN_PUBLISHED = "DEP-003"
_RULE_UPSTREAM_NOT_REFLECTED = "DEP-004"


def _load_doc(path: Path) -> dict[str, Any] | None:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return doc if isinstance(doc, dict) else None


def _service_name(doc: dict[str, Any]) -> str:
    return (doc.get("service") or {}).get("name") or ""


def _downstream_sync_services(doc: dict[str, Any]) -> list[str]:
    sync = ((doc.get("dependencies") or {}).get("downstream") or {}).get("sync") or []
    return [d.get("service") for d in sync if isinstance(d, dict) and d.get("service")]


def _upstream_names(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for u in (doc.get("dependencies") or {}).get("upstream") or []:
        if isinstance(u, str):
            out.append(u)
        elif isinstance(u, dict) and u.get("name"):
            out.append(u["name"])
    return out


def _published_topics(doc: dict[str, Any]) -> list[str]:
    return [
        e.get("topic")
        for e in (doc.get("events") or {}).get("published") or []
        if isinstance(e, dict) and e.get("topic")
    ]


def _consumed_topics(doc: dict[str, Any]) -> list[str]:
    return [
        e.get("topic")
        for e in (doc.get("events") or {}).get("consumed") or []
        if isinstance(e, dict) and e.get("topic")
    ]


def _collect_repo_docs(repo: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Return name → (path, parsed-doc) for every SERVICE_MAP.yaml under ``repo``."""
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    for yaml_path in sorted(repo.rglob("SERVICE_MAP.yaml")):
        doc = _load_doc(yaml_path)
        if not doc:
            continue
        name = _service_name(doc)
        if name:
            out[name] = (yaml_path.relative_to(repo), doc)
    return out


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    repo = Path(cwd) if cwd else Path.cwd()
    targets = [s for s in staged if s.endswith("SERVICE_MAP.yaml")]
    if not targets:
        return []
    docs = _collect_repo_docs(repo)
    if len(docs) < 2:
        return []  # single-service repo — graph lint not meaningful

    # Index for fast lookups
    upstreams_by_service = {n: set(_upstream_names(d)) for n, (_, d) in docs.items()}
    downstreams_by_service = {n: set(_downstream_sync_services(d)) for n, (_, d) in docs.items()}
    consumed_by_service = {n: set(_consumed_topics(d)) for n, (_, d) in docs.items()}

    findings: list[Finding] = []

    # We only emit findings for staged SERVICE_MAP.yaml — but the *evidence* may
    # involve sibling specs we did not stage.
    staged_names = set()
    for path in targets:
        doc = _load_doc(repo / path)
        if doc:
            staged_names.add(_service_name(doc))

    for name in staged_names:
        if name not in docs:
            continue
        rel_path, doc = docs[name]
        path_str = str(rel_path)

        # DEP-002: A.downstream.sync = B → B.upstream should include A.
        for callee in _downstream_sync_services(doc):
            if callee not in docs:
                continue  # silent: B has no SERVICE_MAP
            if name not in upstreams_by_service.get(callee, set()):
                findings.append(
                    Finding(
                        _RULE_DOWNSTREAM_MISSING_UPSTREAM,
                        "WARN",
                        f"'{name}' calls '{callee}' but '{callee}' does not list "
                        f"it as upstream — re-run reverse-scan or add manually",
                        file=path_str,
                    )
                )

        # DEP-003: A publishes T → some sibling must consume T.
        for topic in _published_topics(doc):
            consumed_anywhere = any(topic in consumed_by_service[n] for n in docs)
            if not consumed_anywhere:
                findings.append(
                    Finding(
                        _RULE_ORPHAN_PUBLISHED,
                        "WARN",
                        f"published topic '{topic}' has no consumer in this "
                        f"monorepo (may be normal if consumer lives outside)",
                        file=path_str,
                    )
                )

        # DEP-004: A.upstream = B → B must call A (sync) or share an event with A.
        for upstream_name in _upstream_names(doc):
            if upstream_name not in docs:
                continue  # silent
            calls_a = name in downstreams_by_service.get(upstream_name, set())
            shares_event = bool(
                consumed_by_service[upstream_name] & set(_published_topics(doc))
            ) or bool(
                _consumed_topics(doc)
                and set(_consumed_topics(doc)) & set(
                    _published_topics(docs[upstream_name][1])
                )
            )
            if not calls_a and not shares_event:
                findings.append(
                    Finding(
                        _RULE_UPSTREAM_NOT_REFLECTED,
                        "WARN",
                        f"'{name}' lists '{upstream_name}' as upstream but "
                        f"'{upstream_name}' does not call '{name}' and shares "
                        f"no event with it",
                        file=path_str,
                    )
                )
    return findings
