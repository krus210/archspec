import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_todos import run as check_todos  # noqa: E402


def _yaml_with(fixture_yaml_text, mutate):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    mutate(base)
    return yaml.safe_dump(base)


def test_clean_yaml_no_findings(stage_file, fixture_yaml_text, git_repo):
    text = fixture_yaml_text("valid/minimal.yaml")
    stage_file("docs/SERVICE_MAP.yaml", text)
    assert check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []


def test_todo_in_endpoint_contract_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["api"]["endpoints"] = [
            {
                "name": "GetX",
                "protocol": "gRPC",
                "idempotency": {"required": False},
                "contract": "TODO",
                "sla": {"p99_latency": "100ms", "availability": "99.9%"},
            }
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert findings[0].rule == "DET-006"
    assert findings[0].severity == "WARN"
    assert "api.endpoints[0].contract" in findings[0].message


def test_todo_in_strict_mode_blocks(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["metadata"]["archspec_strict"] = True
        doc["api"]["endpoints"] = [
            {
                "name": "GetX",
                "protocol": "gRPC",
                "idempotency": {"required": False},
                "contract": "TODO",
                "sla": {"p99_latency": "TODO", "availability": "TODO"},
            }
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 3
    assert all(f.severity == "BLOCK" for f in findings)


def test_todo_in_downstream_timeout_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["dependencies"]["downstream"]["sync"] = [
            {
                "service": "x",
                "timeout": "TODO",
                "retries": 0,
                "fallback": "none",
                "on_failure": "propagate",
            }
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert "dependencies.downstream.sync[0].timeout" in findings[0].message


def test_todo_in_event_contracts_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["events"]["published"] = [
            {"topic": "x.created", "contract": "TODO", "version": 1}
        ]
        doc["events"]["consumed"] = [
            {"topic": "y.updated", "contract": "TODO", "expected_version": 1}
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 2
    msgs = {f.message for f in findings}
    assert any("events.published[0].contract" in m for m in msgs)
    assert any("events.consumed[0].contract" in m for m in msgs)


def test_todo_in_storage_name_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["dependencies"]["storage"] = [
            {"type": "in-memory", "name": "TODO", "owned_by": "this service"}
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert "dependencies.storage[0].name" in findings[0].message


def test_non_todo_strings_are_ignored(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["api"]["endpoints"] = [
            {
                "name": "GetX",
                "protocol": "gRPC",
                "idempotency": {"required": False},
                "contract": "proto/x/v1/x.proto",
                "sla": {"p99_latency": "100ms", "availability": "99.9%"},
            }
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    assert check_todos(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []
