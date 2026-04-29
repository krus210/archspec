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


def test_todo_in_default_mode_warns_and_exits_zero(tmp_path):
    base = (FIXTURES / "valid" / "minimal.yaml").read_text(encoding="utf-8")
    import yaml
    doc = yaml.safe_load(base)
    doc["api"]["endpoints"] = [
        {
            "name": "GetX",
            "protocol": "gRPC",
            "idempotency": {"required": False},
            "contract": "TODO",
            "sla": {"p99_latency": "100ms", "availability": "99.9%"},
        }
    ]
    target = tmp_path / "SERVICE_MAP.yaml"
    target.write_text(yaml.safe_dump(doc), encoding="utf-8")
    r = _run([str(target)])
    assert r.returncode == 0
    assert "WARN DET-006" in r.stderr
    assert "api.endpoints[0].contract" in r.stderr


def test_todo_in_strict_mode_blocks(tmp_path):
    base = (FIXTURES / "valid" / "minimal.yaml").read_text(encoding="utf-8")
    import yaml
    doc = yaml.safe_load(base)
    doc["metadata"]["archspec_strict"] = True
    doc["api"]["endpoints"] = [
        {
            "name": "GetX",
            "protocol": "gRPC",
            "idempotency": {"required": False},
            "contract": "TODO",
            "sla": {"p99_latency": "100ms", "availability": "99.9%"},
        }
    ]
    target = tmp_path / "SERVICE_MAP.yaml"
    target.write_text(yaml.safe_dump(doc), encoding="utf-8")
    r = _run([str(target)])
    assert r.returncode == 1
    assert "BLOCK DET-006" in r.stderr
