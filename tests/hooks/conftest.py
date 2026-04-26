import subprocess
from pathlib import Path

import pytest


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path):
    """Initialise a fresh git repo with one initial empty commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "test@archspec.dev")
    _git(repo, "config", "user.name", "archspec-test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def stage_file(git_repo):
    def _stage(rel: str, content: str) -> None:
        path = git_repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _git(git_repo, "add", rel)
    return _stage


@pytest.fixture
def commit_file(git_repo):
    def _commit(rel: str, content: str, msg: str = "add") -> None:
        path = git_repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _git(git_repo, "add", rel)
        _git(git_repo, "commit", "-m", msg)
    return _commit


@pytest.fixture
def fixture_yaml_text():
    """Return the content of a fixture YAML by relative path under tests/fixtures/yaml/."""
    base = Path(__file__).resolve().parent.parent / "fixtures" / "yaml"

    def _read(rel: str) -> str:
        return (base / rel).read_text(encoding="utf-8")
    return _read
