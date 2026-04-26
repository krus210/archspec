import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_breaking_changes import run as check_breaking  # noqa: E402


def _commit_yaml(commit_file, doc):
    commit_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(doc), msg="seed")


def test_idempotency_required_flipped_off_blocks(
    commit_file, stage_file, fixture_yaml_text, git_repo,
):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["api"]["endpoints"] = [{
        "name": "X", "protocol": "HTTP",
        "idempotency": {"required": True, "key_source": "header: K", "storage": "redis"},
        "contract": "api/x.yaml",
        "sla": {"p99_latency": "1s", "availability": "99%"}
    }]
    _commit_yaml(commit_file, base)
    base["api"]["endpoints"][0]["idempotency"]["required"] = False
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    findings = check_breaking(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-006" and f.severity == "BLOCK" for f in findings)


def test_removed_edge_case_blocks(commit_file, stage_file, fixture_yaml_text, git_repo):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["edge_cases"] = [{"id": "EC-001", "description": "x", "test": "tests/x.go"}]
    _commit_yaml(commit_file, base)
    base["edge_cases"] = []
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    findings = check_breaking(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-007" and f.severity == "BLOCK" for f in findings)


def test_api_changed_without_changelog_blocks(commit_file, stage_file, fixture_yaml_text, git_repo):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["api"]["endpoints"] = []
    _commit_yaml(commit_file, base)
    base["api"]["endpoints"] = [{
        "name": "Y", "protocol": "HTTP",
        "idempotency": {"required": False},
        "contract": "api/y.yaml",
        "sla": {"p99_latency": "1s", "availability": "99%"}
    }]
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    findings = check_breaking(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-008" for f in findings)


def test_consistency_model_change_warns(commit_file, stage_file, fixture_yaml_text, git_repo):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    _commit_yaml(commit_file, base)
    base["consistency"]["model"] = "strong"
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    findings = check_breaking(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-009" and f.severity == "WARN" for f in findings)


def test_idempotency_change_with_adr_passes(commit_file, stage_file, fixture_yaml_text, git_repo):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["api"]["endpoints"] = [{
        "name": "X", "protocol": "HTTP",
        "idempotency": {"required": True, "key_source": "header: K", "storage": "redis"},
        "contract": "api/x.yaml",
        "sla": {"p99_latency": "1s", "availability": "99%"}
    }]
    _commit_yaml(commit_file, base)
    adr_dir = git_repo / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-relax-idempotency.md").write_text("# 0001\n", encoding="utf-8")
    base["api"]["endpoints"][0]["idempotency"]["required"] = False
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    stage_file("docs/adr/0001-relax-idempotency.md", "# 0001\n")
    findings = check_breaking(
        ["docs/SERVICE_MAP.yaml", "docs/adr/0001-relax-idempotency.md"],
        cwd=git_repo,
    )
    assert not any(f.rule == "DET-006" and f.severity == "BLOCK" for f in findings)
