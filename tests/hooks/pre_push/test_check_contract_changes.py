import subprocess

from hooks.pre_push import check_contract_changes


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_no_findings_when_yaml_unchanged_vs_origin(synced_repo):
    _git(synced_repo, "checkout", "-b", "feature/no-contract")
    findings = check_contract_changes(repo_root=synced_repo, base_ref="main")
    assert findings == []


def test_block_on_idempotency_required_flip_without_changelog(synced_repo):
    _git(synced_repo, "checkout", "-b", "feature/break")
    yaml = synced_repo / "docs" / "SERVICE_MAP.yaml"
    text = yaml.read_text(encoding="utf-8")
    text = text.replace("required: true", "required: false")
    yaml.write_text(text, encoding="utf-8")
    _git(synced_repo, "add", "docs/SERVICE_MAP.yaml")
    _git(
        synced_repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", "flip idempotency",
    )
    findings = check_contract_changes(repo_root=synced_repo, base_ref="main")
    assert any(f.rule == "DET-006" and f.severity == "BLOCK" for f in findings)


def test_no_block_on_idempotency_downgrade_when_adr_added(synced_repo):
    _git(synced_repo, "checkout", "-b", "feature/break-with-adr")
    yaml = synced_repo / "docs" / "SERVICE_MAP.yaml"
    text = yaml.read_text(encoding="utf-8")
    text = text.replace("required: true", "required: false")
    yaml.write_text(text, encoding="utf-8")
    adr = synced_repo / "docs" / "adr" / "0042-skip-idempotency.md"
    adr.parent.mkdir(parents=True, exist_ok=True)
    adr.write_text("# 0042 skip idempotency\n\nrationale here\n", encoding="utf-8")
    _git(synced_repo, "add", "docs/SERVICE_MAP.yaml", "docs/adr/0042-skip-idempotency.md")
    _git(
        synced_repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-m", "flip idempotency with ADR",
    )
    findings = check_contract_changes(repo_root=synced_repo, base_ref="main")
    assert not any(f.rule == "DET-006" for f in findings)
