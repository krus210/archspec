import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))
from checks.check_diagrams import run as check_diagrams  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_yaml_staged_without_regenerated_diagrams_is_autofix(
    stage_file, fixture_yaml_text, git_repo
):
    stage_file("docs/SERVICE_MAP.yaml", fixture_yaml_text("valid/full.yaml"))
    findings = check_diagrams(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    assert any(f.rule == "DET-004" and f.severity == "AUTO-FIX" for f in findings)


def test_only_mmd_staged_blocks(stage_file, git_repo):
    stage_file("docs/diagrams/context.mmd", "flowchart LR\n  a-->b\n")
    findings = check_diagrams(["docs/diagrams/context.mmd"], cwd=git_repo)
    assert any(f.rule == "DET-005" and f.severity == "BLOCK" for f in findings)


def test_invalid_yaml_does_not_crash_check_diagrams(stage_file, git_repo):
    """When sync.py fails (because YAML is invalid), check_diagrams should not raise.

    DET-001 owns the error reporting; check_diagrams should silently skip.
    """
    stage_file("docs/SERVICE_MAP.yaml", "service:\n")  # missing required keys; sync will fail
    findings = check_diagrams(["docs/SERVICE_MAP.yaml"], cwd=git_repo)
    # Should not raise. May return empty or some findings, but no exception.
    assert isinstance(findings, list)


def test_yaml_with_regenerated_diagrams_passes(stage_file, fixture_yaml_text, git_repo, tmp_path):
    (git_repo / "docs").mkdir()
    yaml_text = fixture_yaml_text("valid/full.yaml")
    (git_repo / "docs" / "SERVICE_MAP.yaml").write_text(yaml_text, encoding="utf-8")
    sync_script = ROOT / "skills" / "architecture-sync" / "scripts" / "sync.py"
    subprocess.run(
        [
            sys.executable,
            str(sync_script),
            str(git_repo / "docs" / "SERVICE_MAP.yaml"),
            str(git_repo / "docs"),
        ],
        check=True,
    )
    _git(git_repo, "add", "docs")
    findings = check_diagrams(
        [
            "docs/SERVICE_MAP.yaml",
            "docs/diagrams/context.mmd",
            "docs/diagrams/container.mmd",
            "docs/diagrams/sequence.mmd",
            "docs/ARCHITECTURE.md",
        ],
        cwd=git_repo,
    )
    assert findings == []
