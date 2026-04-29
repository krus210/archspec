import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_write_path_events import run as check_wpe  # noqa: E402


def _yaml_with(fixture_yaml_text, mutate):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    mutate(base)
    return yaml.safe_dump(base)


def test_outbox_with_published_events_passes(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["consistency"]["write_path"]["pattern"] = "outbox"
        doc["events"]["published"] = [
            {"topic": "x.created", "contract": "x.proto", "version": 1}
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    assert check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []


def test_outbox_without_events_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["consistency"]["write_path"]["pattern"] = "outbox"
        doc["events"]["published"] = []
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert findings[0].rule == "DEP-001"
    assert findings[0].severity == "WARN"
    assert "outbox pattern declared but events.published is empty" in findings[0].message


def test_direct_with_published_events_warns(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["consistency"]["write_path"]["pattern"] = "direct"
        doc["events"]["published"] = [
            {"topic": "x.created", "contract": "x.proto", "version": 1}
        ]
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert findings[0].severity == "WARN"
    assert "no atomicity guarantee" in findings[0].message


def test_strict_mode_promotes_to_block(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["metadata"]["archspec_strict"] = True
        doc["consistency"]["write_path"]["pattern"] = "outbox"
        doc["events"]["published"] = []
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    findings = check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert len(findings) == 1
    assert findings[0].severity == "BLOCK"


def test_direct_without_events_passes(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["consistency"]["write_path"]["pattern"] = "direct"
        doc["events"]["published"] = []
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    assert check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []


def test_saga_pattern_silent(stage_file, fixture_yaml_text, git_repo):
    def mutate(doc):
        doc["consistency"]["write_path"]["pattern"] = "saga"
        doc["events"]["published"] = []
    stage_file("docs/SERVICE_MAP.yaml", _yaml_with(fixture_yaml_text, mutate))
    assert check_wpe(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []
