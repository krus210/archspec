import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_schema import run as check_schema  # noqa: E402


def test_valid_yaml_no_findings(stage_file, fixture_yaml_text, git_repo):
    stage_file("docs/SERVICE_MAP.yaml", fixture_yaml_text("valid/minimal.yaml"))
    findings = check_schema(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert findings == []


def test_invalid_yaml_yields_block(stage_file, fixture_yaml_text, git_repo):
    stage_file("docs/SERVICE_MAP.yaml", fixture_yaml_text("invalid/missing_metadata.yaml"))
    findings = check_schema(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) >= 1
    assert findings[0].rule == "DET-001"
    assert findings[0].severity == "BLOCK"


def test_no_yaml_in_staged_returns_empty(git_repo):
    assert check_schema([], cwd=git_repo) == []
