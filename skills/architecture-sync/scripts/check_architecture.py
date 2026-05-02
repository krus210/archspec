"""Audit a monorepo of SERVICE_MAP.yaml files.

Walks every `SERVICE_MAP.yaml` reachable from `<repo-root>` and prints a
markdown report listing graph mismatches, orphan events, TODO leaks and
write_path/events inconsistencies. Read-only by default; ``--apply-upstream-fixes``
mutates SERVICE_MAP.yaml files to add missing upstream entries discovered via
reverse-scan.

CLI: check_architecture.py <repo-root> [--issues-only] [--full]
                           [--apply-upstream-fixes]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import is_read_endpoint  # noqa: E402
from apply_upstream import (  # noqa: E402
    merge_upstream,
    render_upstream_block,
    replace_upstream_block,
)
from scan_go import reverse_scan  # noqa: E402

_TODO_LITERAL = "TODO"
_NOT_DOCUMENTED = "not-documented"
_NOT_IMPLEMENTED = "not-implemented"
_NOT_MEASURED = "not-measured"
_STORAGE_TECH_RE = re.compile(r"^(redis|postgres|mysql|mongodb|memcached)\b")


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
    storage = (doc.get("dependencies") or {}).get("storage") or []
    if pattern == "outbox" and not published:
        issues.append("DEP-001 outbox declared but events.published empty")
    elif pattern == "direct" and published:
        issues.append("DEP-001 events.published with direct write path — no atomicity")
    if pattern == "outbox" and not storage:
        issues.append(
            "DEP-001b outbox declared but dependencies.storage is empty — "
            "outbox needs durable storage"
        )

    # DEP-002 — caller not listed as upstream by callee
    upstreams_by = {n: set(_upstream_names(d)) for n, (_, d) in docs.items()}
    for callee in _downstream_sync_services(doc):
        if callee not in docs:
            continue
        if name not in upstreams_by.get(callee, set()):
            issues.append(f"DEP-002 calls '{callee}' but '{callee}' lacks upstream entry")

    # IDEMP-001/002 — idempotency truthfulness.
    storage_types = {
        s.get("type")
        for s in (doc.get("dependencies") or {}).get("storage") or []
        if isinstance(s, dict) and s.get("type")
    }
    for i, ep in enumerate((doc.get("api") or {}).get("endpoints") or []):
        idemp = ep.get("idempotency") or {}
        if not idemp.get("required"):
            continue
        storage_decl = idemp.get("storage") or ""
        if storage_decl == _NOT_IMPLEMENTED:
            issues.append(
                f"IDEMP-001 api.endpoints[{i}].idempotency: required=true but "
                f"storage='not-implemented' (visible debt — wire a durable store)"
            )
            continue
        m = _STORAGE_TECH_RE.match(storage_decl)
        if m and m.group(1) not in storage_types:
            issues.append(
                f"IDEMP-002 api.endpoints[{i}].idempotency.storage references "
                f"'{m.group(1)}' but no '{m.group(1)}' entry in dependencies.storage[] "
                f"— YAML lies about infrastructure"
            )

    # DOC-001/002 — contract documentation gaps.
    for i, ep in enumerate((doc.get("api") or {}).get("endpoints") or []):
        if ep.get("contract") == _NOT_DOCUMENTED:
            issues.append(
                f"DOC-001 api.endpoints[{i}].contract='not-documented' — "
                f"contract is undocumented debt"
            )
    for i, e in enumerate((doc.get("events") or {}).get("published") or []):
        if e.get("contract") in {_NOT_DOCUMENTED, _NOT_IMPLEMENTED}:
            issues.append(
                f"DOC-002 events.published[{i}].contract='{e.get('contract')}' — "
                f"published event has no schema"
            )

    # SLA-001 — `not-measured` SLA fields under archspec_strict.
    strict = bool((doc.get("metadata") or {}).get("archspec_strict"))
    if strict:
        for i, ep in enumerate((doc.get("api") or {}).get("endpoints") or []):
            sla = ep.get("sla") or {}
            for field in ("p99_latency", "availability"):
                if sla.get(field) == _NOT_MEASURED:
                    issues.append(
                        f"SLA-001 api.endpoints[{i}].sla.{field}='not-measured' "
                        f"under archspec_strict — wire metrics/SLO before declaring"
                    )

    # DEP-005 — orphan mutating endpoint (no caller in monorepo).
    # Looks at THIS service's own upstream[i].endpoints_used — that's the
    # method-level provenance recorded by the reverse-scan / questionnaire.
    used_by_callers: set[str] = set()
    for u in (doc.get("dependencies") or {}).get("upstream") or []:
        if isinstance(u, dict):
            for ep in u.get("endpoints_used") or []:
                used_by_callers.add(ep)
    for ep in (doc.get("api") or {}).get("endpoints") or []:
        ep_name = ep.get("name")
        if not ep_name or is_read_endpoint(ep_name):
            continue
        if ep_name in used_by_callers:
            continue
        issues.append(
            f"DEP-005 endpoint '{ep_name}' has no caller in monorepo "
            f"(orphan write — dead code or undocumented external client)"
        )

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


def apply_upstream_fixes(repo: Path, write: bool) -> tuple[int, list[str]]:
    """Walk DEP-002 findings, run reverse_scan(repo, callee), merge into callee YAML.

    When ``write`` is False, computes the merge but does NOT touch the files —
    summary lines describe what would change. Set ``write=True`` to commit
    the edits. The default for the CLI is dry-run so an accidental run does
    not silently mutate the entire monorepo.

    Returns (services_modified, summary_lines).
    """
    docs = _collect(repo)
    summary: list[str] = []
    modified = 0

    for callee_name in sorted(docs):
        callee_relpath, callee_doc = docs[callee_name]
        # Find services that call this callee but are not listed in upstream.
        missing_callers: list[str] = []
        declared = set(_upstream_names(callee_doc))
        for caller_name, (_, caller_doc) in docs.items():
            if caller_name == callee_name:
                continue
            if callee_name in _downstream_sync_services(caller_doc) and caller_name not in declared:
                missing_callers.append(caller_name)
        if not missing_callers:
            continue

        scan_report = reverse_scan(repo, callee_name)
        relevant = [c for c in scan_report["consumers"] if c["name"] in missing_callers]
        if not relevant:
            summary.append(
                f"- {callee_name}: missing upstream from {missing_callers}, "
                f"reverse-scan found no matching consumers (HTTP-only? non-Go?)"
            )
            continue

        existing = (callee_doc.get("dependencies") or {}).get("upstream") or []
        merged = merge_upstream(existing, relevant)
        new_block = render_upstream_block(merged)
        callee_path = repo / callee_relpath
        old_text = callee_path.read_text(encoding="utf-8")
        try:
            new_text = replace_upstream_block(old_text, new_block)
        except ValueError as e:
            summary.append(f"- {callee_name}: skipped — {e}")
            continue
        if new_text == old_text:
            continue
        verb = "added" if write else "would add"
        if write:
            callee_path.write_text(new_text, encoding="utf-8")
        modified += 1
        summary.append(
            f"- {callee_name} ({callee_relpath}): {verb} {len(relevant)} upstream "
            f"entries from {sorted(c['name'] for c in relevant)}"
        )

    return modified, summary


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
    parser.add_argument(
        "--apply-upstream-fixes",
        action="store_true",
        help="Auto-apply DEP-002 fixes by running reverse-scan and merging "
        "discovered upstream entries into each callee's SERVICE_MAP.yaml. "
        "By default this is a dry-run that prints the planned edits — "
        "pass --write to actually rewrite the YAML files.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Commit changes for --apply-upstream-fixes (otherwise dry-run).",
    )
    args = parser.parse_args(argv)

    if not args.repo_root.is_dir():
        print(f"error: not a directory: {args.repo_root}", file=sys.stderr)
        return 2

    if args.apply_upstream_fixes:
        modified, summary = apply_upstream_fixes(args.repo_root, write=args.write)
        mode = "applied" if args.write else "dry-run"
        sys.stdout.write(
            f"# archspec --apply-upstream-fixes ({mode}) — {args.repo_root}\n\n"
        )
        verb = "modified" if args.write else "would modify"
        sys.stdout.write(f"Services {verb}: {modified}\n\n")
        if summary:
            sys.stdout.write("\n".join(summary) + "\n")
        if not args.write and modified:
            sys.stdout.write("\nRe-run with --write to apply.\n")
        return 0

    report = render_report(args.repo_root, args.issues_only, args.full)
    if report:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
