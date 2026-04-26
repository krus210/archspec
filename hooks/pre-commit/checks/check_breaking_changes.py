"""DET-006/007/008/009 — flag breaking changes between HEAD and the staged YAML."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import head_blob, staged_blob  # noqa: E402


def _has_adr(staged: list[str]) -> bool:
    return any(s.startswith("docs/adr/") and s.endswith(".md") for s in staged)


def _eps_by_name(doc: dict) -> dict[str, dict]:
    return {
        ep["name"]: ep
        for ep in (doc.get("api") or {}).get("endpoints", []) or []
        if "name" in ep
    }


def _ids(items, key: str = "id") -> set[str]:
    return {it[key] for it in (items or []) if isinstance(it, dict) and key in it}


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    targets = [s for s in staged if s.endswith("SERVICE_MAP.yaml")]
    if not targets:
        return []
    findings: list[Finding] = []
    has_adr = _has_adr(staged)

    for path in targets:
        before_text = head_blob(path, cwd=cwd)
        if before_text is None:
            continue
        try:
            before = yaml.safe_load(before_text) or {}
            after = yaml.safe_load(staged_blob(path, cwd=cwd)) or {}
        except yaml.YAMLError:
            continue

        # DET-006: idempotency.required: true -> false
        before_eps = _eps_by_name(before)
        after_eps = _eps_by_name(after)
        for name, after_ep in after_eps.items():
            before_ep = before_eps.get(name)
            if not before_ep:
                continue
            was = (before_ep.get("idempotency") or {}).get("required")
            now = (after_ep.get("idempotency") or {}).get("required")
            if was is True and now is False and not has_adr:
                findings.append(Finding(
                    "DET-006", "BLOCK",
                    f"endpoint '{name}': idempotency.required true → false without ADR",
                    file=path,
                    fix_hint="add docs/adr/NNNN-*.md and stage it",
                ))

        # DET-007: removed edge_case or scenario
        removed_ec = _ids(before.get("edge_cases")) - _ids(after.get("edge_cases"))
        removed_sc = _ids(before.get("scenarios")) - _ids(after.get("scenarios"))
        if (removed_ec or removed_sc) and not has_adr:
            for rid in sorted(removed_ec | removed_sc):
                findings.append(Finding(
                    "DET-007", "BLOCK",
                    f"removed {rid} without ADR",
                    file=path,
                ))

        # DET-008: api changed without changelog entry
        before_api_struct = {**before.get("api", {})}
        after_api_struct = {**after.get("api", {})}
        before_log_len = len(before_api_struct.pop("changelog", None) or [])
        after_log_len = len(after_api_struct.pop("changelog", None) or [])
        if before_api_struct != after_api_struct and after_log_len <= before_log_len:
            findings.append(Finding(
                "DET-008", "BLOCK",
                "api section changed without a new api.changelog entry",
                file=path,
                fix_hint="append a new entry to api.changelog",
            ))

        # DET-009: consistency.model change → WARN
        before_model = (before.get("consistency") or {}).get("model")
        after_model = (after.get("consistency") or {}).get("model")
        if before_model != after_model:
            findings.append(Finding(
                "DET-009", "WARN",
                f"consistency.model changed: {before_model} → {after_model}",
                file=path,
            ))

    return findings
