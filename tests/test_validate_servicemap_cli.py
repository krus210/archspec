import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "architecture-sync" / "scripts" / "validate_servicemap.py"
FIXTURES = ROOT / "tests" / "fixtures" / "yaml"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_valid_minimal_exits_zero():
    r = _run([str(FIXTURES / "valid" / "minimal.yaml")])
    assert r.returncode == 0, r.stderr


def test_invalid_missing_metadata_exits_one_with_diagnostic():
    r = _run([str(FIXTURES / "invalid" / "missing_metadata.yaml")])
    assert r.returncode == 1
    assert "metadata" in r.stdout + r.stderr


def test_unknown_path_exits_two():
    r = _run(["/nonexistent/path.yaml"])
    assert r.returncode == 2
