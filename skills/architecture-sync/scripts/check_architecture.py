"""Audit a monorepo of SERVICE_MAP.yaml files.

Walks every `SERVICE_MAP.yaml` reachable from `<repo-root>` and prints a
markdown report listing graph mismatches, orphan events, TODO leaks and
write_path/events inconsistencies. Read-only.

CLI: check_architecture.py <repo-root> [--issues-only] [--full]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

_TODO_LITERAL = "TODO"


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


def _todo_paths(doc: dict[str, Any]) -> list[str]:
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


def _collect(repo: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    for yaml_path in sorted(repo.rglob("SERVICE_MAP.yaml")):
        doc = _load_doc(yaml_path)
        if not doc:
            continue
        name = _service_name(doc)
        if name:
            out[name] = (yaml_path.relative_to(repo), doc)
    return out


def _service_issues(name: str, docs: dict[str, tuple[Path, dict]]) -> list[str]:
    """Return human-readable issue lines for one service."""
    issues: list[str] = []
    _, doc = docs[name]

    # DET-006 — TODO leaks
    for jp in _todo_paths(doc):
        issues.append(f"DET-006 TODO at {jp}")

    # DEP-001 — write_path/events consistency
    pattern = ((doc.get("consistency") or {}).get("write_path") or {}).get("pattern")
    published = _published_topics(doc)
    if pattern == "outbox" and not published:
        issues.append("DEP-001 outbox declared but events.published empty")
    elif pattern == "direct" and published:
        issues.append("DEP-001 events.published with direct write path — no atomicity")

    # DEP-002 — caller not listed as upstream by callee
    upstreams_by = {n: set(_upstream_names(d)) for n, (_, d) in docs.items()}
    for callee in _downstream_sync_services(doc):
        if callee not in docs:
            continue
        if name not in upstreams_by.get(callee, set()):
            issues.append(f"DEP-002 calls '{callee}' but '{callee}' lacks upstream entry")

    # DEP-003 — orphan published topic
    consumed_by = {n: set(_consumed_topics(d)) for n, (_, d) in docs.items()}
    for topic in published:
        if not any(topic in consumed_by[n] for n in docs):
            issues.append(f"DEP-003 published '{topic}' has no consumer in monorepo")

    # DEP-004 — upstream entry not reflected by claimed caller
    downstreams_by = {n: set(_downstream_sync_services(d)) for n, (_, d) in docs.items()}
    consumed_self = set(_consumed_topics(doc))
    for upstream_name in _upstream_names(doc):
        if upstream_name not in docs:
            continue
        calls_self = name in downstreams_by.get(upstream_name, set())
        b_consumes_a_pub = bool(consumed_by[upstream_name] & set(published))
        a_consumes_b_pub = bool(
            consumed_self & set(_published_topics(docs[upstream_name][1]))
        )
        if not calls_self and not b_consumes_a_pub and not a_consumes_b_pub:
            issues.append(
                f"DEP-004 lists '{upstream_name}' as upstream but '{upstream_name}' "
                f"does not call '{name}' / shares no event"
            )

    return issues


def render_report(repo: Path, issues_only: bool, full: bool) -> str:
    docs = _collect(repo)
    lines = [f"# archspec audit — {repo}"]
    lines.append("")
    if not docs:
        lines.append("No SERVICE_MAP.yaml found.")
        return "\n".join(lines) + "\n"

    lines.append(f"Found {len(docs)} services: {', '.join(sorted(docs))}")
    lines.append("")

    if full:
        lines.append("## Service summary")
        lines.append("")
        lines.append(
            "| Service | Sync downstream | Sync upstream (declared) | "
            "Sync upstream (computed) | Pubs | Subs |"
        )
        lines.append("|---|---|---|---|---|---|")
        for name in sorted(docs):
            _, doc = docs[name]
            ds = ", ".join(sorted(_downstream_sync_services(doc))) or "—"
            us_decl = ", ".join(sorted(_upstream_names(doc))) or "—"
            us_comp = sorted(
                {
                    other
                    for other, (_, d) in docs.items()
                    if other != name
                    and (
                        name in _downstream_sync_services(d)
                        or set(_consumed_topics(d)) & set(_published_topics(doc))
                    )
                }
            )
            us_comp_s = ", ".join(us_comp) or "—"
            pubs = ", ".join(sorted(_published_topics(doc))) or "—"
            subs = ", ".join(sorted(_consumed_topics(doc))) or "—"
            lines.append(f"| {name} | {ds} | {us_decl} | {us_comp_s} | {pubs} | {subs} |")
        lines.append("")

    lines.append("## Issues")
    lines.append("")
    any_issues = False
    for name in sorted(docs):
        issues = _service_issues(name, docs)
        if not issues:
            continue
        any_issues = True
        lines.append(f"### {name} ({docs[name][0]})")
        for it in issues:
            lines.append(f"- {it}")
        lines.append("")
    if not any_issues:
        lines.append("_No issues._")
        lines.append("")

    if issues_only and not any_issues:
        return ""

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a monorepo of SERVICE_MAP.yaml files"
    )
    parser.add_argument("repo_root", type=Path)
    parser.add_argument(
        "--issues-only",
        action="store_true",
        help="Suppress output entirely when no issues are found.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include the full per-service summary table.",
    )
    args = parser.parse_args(argv)

    if not args.repo_root.is_dir():
        print(f"error: not a directory: {args.repo_root}", file=sys.stderr)
        return 2

    report = render_report(args.repo_root, args.issues_only, args.full)
    if report:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
