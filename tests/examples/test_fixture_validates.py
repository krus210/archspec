import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "examples" / "go-microservice-fixture"


def test_fixture_yaml_validates():
    cmd = [
        sys.executable,
        str(REPO_ROOT / "skills" / "architecture-sync" / "scripts" / "validate_servicemap.py"),
        str(FIXTURE / "docs" / "SERVICE_MAP.yaml"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_fixture_diagrams_match_generators():
    sys.path.insert(0, str(REPO_ROOT / "skills" / "architecture-sync" / "scripts"))
    from sync import sync
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sync(FIXTURE / "docs" / "SERVICE_MAP.yaml", td_path)
        for relative in ("diagrams/context.mmd", "diagrams/container.mmd",
                         "diagrams/sequence.mmd", "ARCHITECTURE.md"):
            actual = FIXTURE / "docs" / relative
            fresh = td_path / relative
            assert actual.read_bytes() == fresh.read_bytes(), f"{relative} drift"


@pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")
def test_fixture_go_compiles():
    proc = subprocess.run(["go", "build", "./..."], cwd=str(FIXTURE),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
