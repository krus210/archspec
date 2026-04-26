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


def test_scan_kafka_finds_published_and_consumed_topics():
    report = _run(FIXTURES / "kafka")
    pub = sorted(t["topic"] for t in report["events_published"])
    con = sorted(t["topic"] for t in report["events_consumed"])
    assert pub == ["geo.points.v1", "tasks.created.v1"]
    assert con == ["profiles.updated.v1", "tasks.assigned.v1"]
    for ev in report["events_published"] + report["events_consumed"]:
        assert ev["source"].startswith("main.go:")
        assert ev["confidence"] in {"medium", "low"}
        assert ev["backend"] == "kafka"


def test_scan_nats_finds_subjects_and_resolves_constants():
    report = _run(FIXTURES / "nats")
    pub = sorted(t["topic"] for t in report["events_published"])
    con = sorted(t["topic"] for t in report["events_consumed"])
    assert pub == ["billing.invoice.v1", "geo.points.v1", "task.created"]
    assert con == ["match.found", "notifications.push"]
    for ev in report["events_published"] + report["events_consumed"]:
        assert ev["backend"] == "nats"
        assert ev["source"].startswith("main.go:")
    assert "x" not in pub


def test_scan_unknown_messaging_library_produces_zero_events_no_crash():
    report = _run(FIXTURES / "unknown_messaging")
    assert report["events_published"] == []
    assert report["events_consumed"] == []
    assert report["files_scanned"] == 1


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
    paths = sorted(
        {(e["method"], e["path"]) for e in report["endpoints"] if e["protocol"] == "HTTP"}
    )
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
