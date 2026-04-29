"""Tests for /archspec:check-architecture monorepo audit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "architecture-sync" / "scripts" / "check_architecture.py"


def _run(repo: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo), *flags],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )


def _base(name: str) -> dict:
    return {
        "metadata": {
            "schema_version": "1.0",
            "source_of_truth": "local",
            "drift_check_in_ci": True,
            "last_reviewed": "2026-04-28",
        },
        "service": {
            "name": name,
            "team": "x",
            "language": "go",
            "repo": "github.com/x/y",
            "domain": name,
            "ownership": {"primary": "@x", "oncall": "@x"},
            "responsibilities": ["x"],
            "invariants": ["x"],
        },
        "api": {"version": 1, "endpoints": [], "changelog": []},
        "dependencies": {
            "upstream": [],
            "downstream": {"sync": [], "async": []},
            "storage": [],
        },
        "events": {"published": [], "consumed": []},
        "consistency": {
            "model": "eventual",
            "bounded_aggregate": name,
            "write_path": {"pattern": "direct"},
            "read_path": {"consistency": "eventual"},
            "cross_service_invariants": [],
        },
        "concurrency": {"aggregates": [], "hot_keys": [], "shared_state": []},
    }


def _write(repo: Path, service_name: str, doc: dict) -> None:
    path = repo / "services" / service_name / "docs" / "SERVICE_MAP.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_empty_repo_no_servicemaps(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 0
    assert "No SERVICE_MAP.yaml found" in r.stdout


def test_clean_pair_reports_no_issues(tmp_path):
    a = _base("a")
    a["dependencies"]["downstream"]["sync"] = [
        {
            "service": "b",
            "timeout": "1s",
            "retries": 0,
            "fallback": "none",
            "on_failure": "propagate",
        }
    ]
    b = _base("b")
    b["dependencies"]["upstream"] = [
        {"name": "a", "protocol": "gRPC", "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", b)
    r = _run(tmp_path)
    assert r.returncode == 0
    assert "_No issues._" in r.stdout


def test_dep002_caller_not_listed_as_upstream(tmp_path):
    a = _base("a")
    a["dependencies"]["downstream"]["sync"] = [
        {
            "service": "b",
            "timeout": "1s",
            "retries": 0,
            "fallback": "none",
            "on_failure": "propagate",
        }
    ]
    b = _base("b")  # no upstream
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", b)
    r = _run(tmp_path)
    assert "DEP-002" in r.stdout
    assert "calls 'b' but 'b' lacks upstream entry" in r.stdout


def test_dep003_orphan_published_event(tmp_path):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [
        {"topic": "x.created", "contract": "x.proto", "version": 1}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-003" in r.stdout
    assert "x.created" in r.stdout


def test_dep004_upstream_not_reflected(tmp_path):
    """Reproduces freelance-marketplace geo-service.upstream=api-gateway bug."""
    geo = _base("geo")
    geo["dependencies"]["upstream"] = [
        {"name": "gw", "protocol": "gRPC", "discovered_via": "manual"}
    ]
    gw = _base("gw")
    _write(tmp_path, "geo", geo)
    _write(tmp_path, "gw", gw)
    r = _run(tmp_path)
    assert "DEP-004" in r.stdout
    assert "geo" in r.stdout and "gw" in r.stdout


def test_det006_todo_in_endpoint(tmp_path):
    a = _base("a")
    a["api"]["endpoints"] = [
        {
            "name": "GetX",
            "protocol": "gRPC",
            "idempotency": {"required": False},
            "contract": "TODO",
            "sla": {"p99_latency": "100ms", "availability": "99.9%"},
        }
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DET-006" in r.stdout
    assert "api.endpoints[0].contract" in r.stdout


def test_dep001_outbox_without_events(tmp_path):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = []
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-001" in r.stdout


def test_full_includes_summary_table(tmp_path):
    _write(tmp_path, "a", _base("a"))
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path, "--full")
    assert "Service summary" in r.stdout
    assert "| Service |" in r.stdout


def test_issues_only_silent_when_clean(tmp_path):
    _write(tmp_path, "a", _base("a"))
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path, "--issues-only")
    assert r.returncode == 0
    assert r.stdout == ""


def test_unknown_repo_root_exits_2(tmp_path):
    r = _run(tmp_path / "does-not-exist")
    assert r.returncode == 2


def test_dep004_silent_with_event_link(tmp_path):
    """If A.upstream lists B and B consumes A's event, no DEP-004."""
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [
        {"topic": "x.created", "contract": "x.proto", "version": 1}
    ]
    a["dependencies"]["upstream"] = [
        {"name": "b", "protocol": "gRPC", "discovered_via": "manual"}
    ]
    b = _base("b")
    b["events"]["consumed"] = [
        {"topic": "x.created", "contract": "x.proto", "expected_version": 1}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", b)
    r = _run(tmp_path)
    assert "DEP-004" not in r.stdout
