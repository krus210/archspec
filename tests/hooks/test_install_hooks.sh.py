import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INSTALL = ROOT / "hooks" / "pre-commit" / "install_hooks.sh"


def test_install_is_idempotent_and_creates_chained_runner(git_repo):
    for _ in range(2):
        r = subprocess.run(["bash", str(INSTALL)], cwd=git_repo, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    hook = git_repo / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    assert os.access(hook, os.X_OK)
    text = hook.read_text(encoding="utf-8")
    assert ".git/hooks/pre-commit.d" in text
    archspec_part = git_repo / ".git" / "hooks" / "pre-commit.d" / "10-archspec"
    assert archspec_part.is_file()
    assert os.access(archspec_part, os.X_OK)


def test_installed_archspec_parts_prefer_repo_venv_python(git_repo):
    r = subprocess.run(["bash", str(INSTALL)], cwd=git_repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    pre_commit_part = git_repo / ".git" / "hooks" / "pre-commit.d" / "10-archspec"
    pre_push_part = git_repo / ".git" / "hooks" / "pre-push.d" / "10-archspec"

    for hook_part in (pre_commit_part, pre_push_part):
        text = hook_part.read_text(encoding="utf-8")
        assert "PYTHON=\"$REPO_ROOT/.venv/bin/python\"" in text
        assert 'if [ ! -x "$PYTHON" ]; then' in text
        assert 'PYTHON="python3"' in text
        assert 'exec "$PYTHON"' in text


def test_install_preserves_existing_hook(git_repo):
    existing = git_repo / ".git" / "hooks" / "pre-commit"
    existing.write_text("#!/usr/bin/env bash\necho husky\nexit 0\n", encoding="utf-8")
    existing.chmod(existing.stat().st_mode | stat.S_IXUSR)
    r = subprocess.run(["bash", str(INSTALL)], cwd=git_repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # The pre-existing script is preserved as a `.d/05-existing` part.
    parts = list((git_repo / ".git" / "hooks" / "pre-commit.d").glob("*"))
    assert any("existing" in p.name for p in parts)
