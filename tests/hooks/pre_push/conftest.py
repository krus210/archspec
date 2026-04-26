import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_FIXTURE = REPO_ROOT / "examples" / "go-microservice-fixture"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _bootstrap(tmp_path: Path) -> Path:
    if not EXAMPLE_FIXTURE.is_dir():
        pytest.skip(f"example fixture not yet present at {EXAMPLE_FIXTURE} (Task 6)")
    repo = tmp_path / "repo"
    shutil.copytree(EXAMPLE_FIXTURE, repo)
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    return repo


@pytest.fixture
def synced_repo(tmp_path):
    return _bootstrap(tmp_path)


@pytest.fixture
def stale_diagrams_repo(tmp_path):
    repo = _bootstrap(tmp_path)
    yaml = repo / "docs" / "SERVICE_MAP.yaml"
    # Add a new responsibility — generator output gains a line while every
    # currently-committed line is still present, so the heuristic in
    # check_drift correctly classifies this as DET-004 (yaml changed,
    # diagrams stale) rather than DET-005 (hand edit).
    text = yaml.read_text(encoding="utf-8")
    yaml.write_text(
        text.replace(
            "    - \"create and update listings\"",
            "    - \"create and update listings\"\n    - \"reindex on demand\"",
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "docs/SERVICE_MAP.yaml")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "edit yaml only")
    return repo


@pytest.fixture
def hand_edited_diagram_repo(tmp_path):
    repo = _bootstrap(tmp_path)
    diag = repo / "docs" / "diagrams" / "context.mmd"
    diag.write_text(diag.read_text(encoding="utf-8") + "\n%% hand edit\n", encoding="utf-8")
    _git(repo, "add", "docs/diagrams/context.mmd")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "hand edit diagram")
    return repo
