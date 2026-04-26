import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))
from checks.check_exceptions import run as check_exc  # noqa: E402


def _yaml_with_exc(fixture_yaml_text, exceptions: list[dict]) -> str:
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["exceptions"] = exceptions
    return yaml.safe_dump(base)


def test_exception_missing_reason_blocks(stage_file, fixture_yaml_text, git_repo):
    # no reason
    bad = [{
        "rule": "AI-001", "scope": {}, "approved_by": "@a", "adr": "docs/adr/0001.md",
    }]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with_exc(fixture_yaml_text, bad))
    # DET-010: missing reason/approved_by — schema-level catches it too,
    # but check_exceptions is the gate.
    findings = check_exc(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-010" for f in findings)


def test_exception_with_missing_adr_file_blocks(stage_file, fixture_yaml_text, git_repo):
    bad = [{
        "rule": "AI-001", "scope": {}, "reason": "x", "approved_by": "@a",
        "adr": "docs/adr/missing.md",
    }]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with_exc(fixture_yaml_text, bad))
    findings = check_exc(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-011" for f in findings)


def test_expired_exception_warns(stage_file, fixture_yaml_text, git_repo):
    (git_repo / "docs" / "adr").mkdir(parents=True)
    (git_repo / "docs" / "adr" / "0001.md").write_text("# 0001\n")
    expired = [{
        "rule": "AI-001", "scope": {}, "reason": "x", "approved_by": "@a",
        "adr": "docs/adr/0001.md", "expires": "2020-01-01",
    }]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with_exc(fixture_yaml_text, expired))
    findings = check_exc(["docs/SERVICE_MAP.yaml"], cwd=git_repo, today="2026-04-25")
    assert any(f.rule == "DET-012" and f.severity == "WARN" for f in findings)


def test_temporary_exception_without_expires_warns(stage_file, fixture_yaml_text, git_repo):
    (git_repo / "docs" / "adr").mkdir(parents=True)
    (git_repo / "docs" / "adr" / "0001.md").write_text("# 0001\n")
    bad = [{
        "rule": "AI-001", "scope": {}, "reason": "temporary fix during migration",
        "approved_by": "@a", "adr": "docs/adr/0001.md",
    }]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with_exc(fixture_yaml_text, bad))
    findings = check_exc(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-014" and f.severity == "WARN" for f in findings)
