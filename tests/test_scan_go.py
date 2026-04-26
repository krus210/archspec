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


def test_scan_storage_finds_clients():
    report = _run(FIXTURES / "storage")
    types = sorted({s["type"] for s in report["storage"]})
    assert types == ["in-memory", "mongodb", "postgres", "redis", "sql"]
    by_type = {s["type"]: s for s in report["storage"]}
    assert by_type["in-memory"]["confidence"] == "low"
    assert by_type["postgres"]["confidence"] == "high"
    for s in report["storage"]:
        assert s["source"].startswith("main.go:")


def test_scan_grpc_client_extracts_downstream_targets():
    report = _run(FIXTURES / "grpc_client")
    targets = sorted(d["service"] for d in report["downstream_sync"])
    assert targets == ["geo-service", "matching-service", "task-service"]
    for d in report["downstream_sync"]:
        assert d["protocol"] == "gRPC"
        assert d["source"].startswith("main.go:")
        assert d["confidence"] in {"high", "medium", "low"}


def test_scan_grpc_server_finds_registered_services():
    report = _run(FIXTURES / "grpc_server")
    grpc = sorted(
        e["name"] for e in report["endpoints"] if e["protocol"] == "gRPC"
    )
    assert grpc == ["GeoServiceServer", "TaskServiceServer"]
    for ep in report["endpoints"]:
        if ep["protocol"] == "gRPC":
            assert ep["source"].startswith("main.go:")
            assert ep["confidence"] == "high"


def test_scan_http_routes_finds_all_routers():
    report = _run(FIXTURES / "http_routes")
    paths = sorted({(e["method"], e["path"]) for e in report["endpoints"] if e["protocol"] == "HTTP"})
    assert paths == [
        ("ANY", "/api/v1/tasks"),
        ("ANY", "/api/v1/tasks/"),
        ("DELETE", "/files/:name"),
        ("GET", "/healthz"),
        ("GET", "/users/{id}"),
        ("POST", "/users"),
        ("PUT", "/items/:id"),
    ]
    for ep in report["endpoints"]:
        assert ep["protocol"] == "HTTP"
        assert ep["source"].startswith("main.go:")
        assert ep["confidence"] in {"high", "medium", "low"}
