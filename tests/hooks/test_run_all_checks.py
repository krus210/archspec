import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
RUNNER = ROOT / "hooks" / "pre-commit" / "run_all_checks.py"


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=repo, capture_output=True, text=True,
    )


def test_no_archspec_files_staged_exits_zero(git_repo, stage_file):
    stage_file("README.md", "hi\n")
    assert _run(git_repo).returncode == 0


def test_block_finding_exits_one(git_repo, stage_file, fixture_yaml_text):
    stage_file("docs/SERVICE_MAP.yaml", fixture_yaml_text("invalid/missing_metadata.yaml"))
    r = _run(git_repo)
    assert r.returncode == 1
    assert "DET-001" in r.stdout + r.stderr


def test_warn_only_exits_zero(git_repo, stage_file, fixture_yaml_text):
    base = yaml.safe_load(fixture_yaml_text("valid/minimal.yaml"))
    (git_repo / "docs").mkdir(exist_ok=True)
    (git_repo / "docs" / "SERVICE_MAP.yaml").write_text(
        yaml.safe_dump(base), encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "docs/SERVICE_MAP.yaml"],
        cwd=git_repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "seed"],
        cwd=git_repo, check=True, capture_output=True,
    )
    base["consistency"]["model"] = "strong"
    stage_file("docs/SERVICE_MAP.yaml", yaml.safe_dump(base))
    # also need to keep diagrams in sync — easiest: stage them too
    sync = ROOT / "skills" / "architecture-sync" / "scripts" / "sync.py"
    subprocess.run(
        [
            sys.executable, str(sync),
            str(git_repo / "docs" / "SERVICE_MAP.yaml"),
            str(git_repo / "docs"),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "add", "docs"],
        cwd=git_repo, check=True, capture_output=True,
    )
    r = _run(git_repo)
    assert r.returncode == 0  # DET-009 is WARN
    assert "DET-009" in r.stdout + r.stderr
