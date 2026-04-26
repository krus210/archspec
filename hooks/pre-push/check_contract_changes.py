"""Pre-push contract-change detection across the full commit range vs origin/main."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml as pyyaml

YAML_RELATIVE = Path("docs/SERVICE_MAP.yaml")
_ADR_DIR = "docs/adr/"
_ADR_SUFFIX = ".md"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    contract_ref: str
    message: str
    suggested_fix: str = ""


def _git_show(repo_root: Path, ref: str, relative: Path) -> str | None:
    target = f"{ref}:{relative.as_posix()}"
    proc = subprocess.run(
        ["git", "show", target],
        cwd=str(repo_root), capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _has_adr_in_range(repo_root: Path, base_ref: str) -> bool:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base_ref}..HEAD"],
        cwd=str(repo_root), capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return False
    return any(
        name.startswith(_ADR_DIR) and name.endswith(_ADR_SUFFIX)
        for name in proc.stdout.splitlines() if name
    )


def _endpoints_by_name(doc: dict) -> dict[str, dict]:
    return {ep["name"]: ep for ep in doc.get("api", {}).get("endpoints", []) if "name" in ep}


def _changelog_entries(doc: dict) -> list[dict]:
    return list(doc.get("api", {}).get("changelog", []))


def check_contract_changes(*, repo_root: Path, base_ref: str = "origin/main") -> list[Finding]:
    head_text = _git_show(repo_root, "HEAD", YAML_RELATIVE)
    base_text = _git_show(repo_root, base_ref, YAML_RELATIVE)
    if head_text is None or base_text is None:
        return []
    head = pyyaml.safe_load(head_text) or {}
    base = pyyaml.safe_load(base_text) or {}

    head_eps = _endpoints_by_name(head)
    base_eps = _endpoints_by_name(base)

    findings: list[Finding] = []
    base_changelog_count = len(_changelog_entries(base))
    head_changelog_count = len(_changelog_entries(head))
    has_new_changelog = head_changelog_count > base_changelog_count
    has_adr = _has_adr_in_range(repo_root, base_ref)

    for name, head_ep in head_eps.items():
        base_ep = base_eps.get(name)
        if base_ep is None:
            continue
        base_required = bool(base_ep.get("idempotency", {}).get("required"))
        head_required = bool(head_ep.get("idempotency", {}).get("required"))
        if base_required and not head_required and not has_adr:
            findings.append(Finding(
                rule="DET-006", severity="BLOCK",
                file=str(YAML_RELATIVE), line=0,
                contract_ref=f"{base_ref}..HEAD",
                message=f"idempotency.required flipped true→false on endpoint {name} without ADR",
                suggested_fix=f"add an ADR under {_ADR_DIR} and reference it in api.changelog",
            ))

    if head_eps != base_eps and not has_new_changelog:
        findings.append(Finding(
            rule="DET-008", severity="BLOCK",
            file=str(YAML_RELATIVE), line=0,
            contract_ref=f"{base_ref}..HEAD",
            message="api.endpoints changed but no new api.changelog entry detected",
            suggested_fix="append an entry to api.changelog describing the change",
        ))
    return findings


def main() -> int:
    repo_root = Path.cwd()
    findings = check_contract_changes(repo_root=repo_root)
    blocking = [f for f in findings if f.severity == "BLOCK"]
    for f in findings:
        print(f"{f.severity} {f.rule} {f.file}: {f.message}", file=sys.stderr)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
