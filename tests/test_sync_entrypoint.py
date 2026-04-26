import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYNC = ROOT / "skills" / "architecture-sync" / "scripts" / "sync.py"
FULL = ROOT / "tests" / "fixtures" / "yaml" / "valid" / "full.yaml"


def test_sync_writes_diagrams_and_architecture_md(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    r = subprocess.run(
        [sys.executable, str(SYNC), str(FULL), str(docs)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stderr
    assert (docs / "ARCHITECTURE.md").is_file()
    assert (docs / "diagrams" / "context.mmd").is_file()
    assert (docs / "diagrams" / "container.mmd").is_file()
    assert (docs / "diagrams" / "sequence.mmd").is_file()


def test_sync_idempotent(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for _ in range(3):
        r = subprocess.run(
            [sys.executable, str(SYNC), str(FULL), str(docs)],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert r.returncode == 0
    arch = (docs / "ARCHITECTURE.md").read_bytes()
    # Run once more, compare bytes.
    subprocess.run([sys.executable, str(SYNC), str(FULL), str(docs)], cwd=ROOT, check=True)
    assert (docs / "ARCHITECTURE.md").read_bytes() == arch
