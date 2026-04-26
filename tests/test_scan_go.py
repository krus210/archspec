"""Tests for skills/architecture-sync/scripts/scan_go.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "skills" / "architecture-sync" / "scripts" / "scan_go.py"
FIXTURES = ROOT / "tests" / "fixtures" / "go"


def _run(service_dir: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCAN), str(service_dir)],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert r.returncode == 0, f"scan_go.py failed: {r.stderr}"
    return json.loads(r.stdout)


def test_scan_empty_directory_returns_all_keys_empty():
    report = _run(FIXTURES / "empty")
    assert report["service_dir"].endswith("empty")
    assert report["endpoints"] == []
    assert report["downstream_sync"] == []
    assert report["storage"] == []
    assert report["events_published"] == []
    assert report["events_consumed"] == []


def test_scan_nonexistent_directory_exits_2():
    r = subprocess.run(
        [sys.executable, str(SCAN), str(FIXTURES / "does-not-exist")],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert r.returncode == 2
    assert "not a directory" in r.stderr.lower()
