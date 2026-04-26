import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_cycles import run as check_cycles  # noqa: E402


def _yaml_with_sync(downstream_sync: list[dict], fixture_yaml_text):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    base["service"]["name"] = "self"
    base["dependencies"]["downstream"]["sync"] = downstream_sync
    return yaml.safe_dump(base)


def test_self_loop_blocks(stage_file, fixture_yaml_text, git_repo):
    text = _yaml_with_sync(
        [
            {
                "service": "self",
                "timeout": "1s",
                "retries": 0,
                "fallback": "fail",
                "on_failure": "err",
            }
        ],
        fixture_yaml_text,
    )
    stage_file("docs/SERVICE_MAP.yaml", text)
    findings = check_cycles(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(
        f.rule == "DET-002" and f.severity == "BLOCK" and "self-loop" in f.message
        for f in findings
    )


def test_duplicate_downstream_blocks(stage_file, fixture_yaml_text, git_repo):
    text = _yaml_with_sync(
        [
            {
                "service": "x",
                "timeout": "1s",
                "retries": 0,
                "fallback": "fail",
                "on_failure": "err",
            },
            {
                "service": "x",
                "timeout": "5s",
                "retries": 1,
                "fallback": "fail",
                "on_failure": "err",
            },
        ],
        fixture_yaml_text,
    )
    stage_file("docs/SERVICE_MAP.yaml", text)
    findings = check_cycles(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any("duplicate" in f.message for f in findings)


def test_distinct_downstreams_pass(stage_file, fixture_yaml_text, git_repo):
    text = _yaml_with_sync(
        [
            {
                "service": "a",
                "timeout": "1s",
                "retries": 0,
                "fallback": "fail",
                "on_failure": "err",
            },
            {
                "service": "b",
                "timeout": "1s",
                "retries": 0,
                "fallback": "fail",
                "on_failure": "err",
            },
        ],
        fixture_yaml_text,
    )
    stage_file("docs/SERVICE_MAP.yaml", text)
    assert check_cycles(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []
