import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_references import run as check_refs  # noqa: E402


def _yaml_with_refs(fixture_yaml_text, contract: str | None, ec_test: str | None) -> str:
    doc = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    if contract is not None:
        doc["api"]["endpoints"] = [{
            "name": "X", "protocol": "HTTP",
            "idempotency": {"required": False},
            "contract": contract,
            "sla": {"p99_latency": "1s", "availability": "99%"}
        }]
    if ec_test is not None:
        doc["edge_cases"] = [{"id": "EC-001", "description": "x", "test": ec_test}]
    return yaml.safe_dump(doc)


def test_existing_paths_pass(stage_file, fixture_yaml_text, git_repo):
    (git_repo / "api").mkdir()
    (git_repo / "api" / "openapi.yaml").write_text("openapi: 3.0.0\n")
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "edge_test.go").write_text("package x\n")
    stage_file(
        "docs/SERVICE_MAP.yaml",
        _yaml_with_refs(fixture_yaml_text, "api/openapi.yaml", "tests/edge_test.go"),
    )
    assert check_refs(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []


def test_missing_contract_blocks(stage_file, fixture_yaml_text, git_repo):
    stage_file(
        "docs/SERVICE_MAP.yaml",
        _yaml_with_refs(fixture_yaml_text, "api/missing.yaml", None),
    )
    findings = check_refs(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-003" and "missing.yaml" in f.message for f in findings)


def test_missing_test_blocks(stage_file, fixture_yaml_text, git_repo):
    stage_file(
        "docs/SERVICE_MAP.yaml",
        _yaml_with_refs(fixture_yaml_text, None, "tests/no_such.go"),
    )
    findings = check_refs(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any("no_such.go" in f.message for f in findings)
