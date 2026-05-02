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
    a["dependencies"]["storage"] = [
        {"type": "postgres", "name": "main-db", "owned_by": "this service"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-001" in r.stdout
    assert "DEP-001b" not in r.stdout  # storage present, only DEP-001


def test_dep001b_outbox_without_storage(tmp_path):
    """Reproduces freelance-marketplace api-gateway: outbox declared, no storage."""
    gw = _base("api-gateway")
    gw["consistency"]["write_path"]["pattern"] = "outbox"
    gw["dependencies"]["storage"] = []
    _write(tmp_path, "api-gateway", gw)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-001b" in r.stdout
    assert "outbox needs durable storage" in r.stdout


def test_dep001b_silent_when_storage_present(tmp_path):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [
        {"topic": "x.created", "contract": "x.proto", "version": 1}
    ]
    a["dependencies"]["storage"] = [
        {"type": "postgres", "name": "main-db", "owned_by": "this service"}
    ]
    b = _base("b")
    b["events"]["consumed"] = [
        {"topic": "x.created", "contract": "x.proto", "expected_version": 1}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", b)
    r = _run(tmp_path)
    assert "DEP-001b" not in r.stdout


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


def _endpoint(
    name: str,
    *,
    idempotency=None,
    contract: str = "x.proto",
    p99: str = "100ms",
    availability: str = "99.9%",
) -> dict:
    return {
        "name": name,
        "protocol": "gRPC",
        "idempotency": idempotency or {"required": False},
        "contract": contract,
        "sla": {"p99_latency": p99, "availability": availability},
    }


def test_idemp001_storage_not_implemented(tmp_path):
    a = _base("a")
    a["api"]["endpoints"] = [
        _endpoint(
            "GetX",
            idempotency={
                "required": True,
                "key_source": "metadata: x",
                "storage": "not-implemented",
            },
        )
    ]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "IDEMP-001" in r.stdout
    assert "visible debt" in r.stdout


def test_idemp002_storage_lies_about_redis(tmp_path):
    """Reproduces freelance-marketplace task-service: redis idempotency without redis storage."""
    a = _base("a")
    a["api"]["endpoints"] = [
        _endpoint(
            "GetX",
            idempotency={
                "required": True,
                "key_source": "metadata: x",
                "storage": "redis: idemp:{key}",
            },
        )
    ]
    # No redis in dependencies.storage[]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "IDEMP-002" in r.stdout
    assert "redis" in r.stdout
    assert "YAML lies" in r.stdout


def test_idemp002_silent_when_storage_matches(tmp_path):
    a = _base("a")
    a["api"]["endpoints"] = [
        _endpoint(
            "GetX",
            idempotency={
                "required": True,
                "key_source": "metadata: x",
                "storage": "redis: idemp:{key}",
            },
        )
    ]
    a["dependencies"]["storage"] = [
        {"type": "redis", "name": "main-cache", "owned_by": "this service"}
    ]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "IDEMP-002" not in r.stdout


def test_doc001_endpoint_contract_not_documented(tmp_path):
    a = _base("a")
    a["api"]["endpoints"] = [_endpoint("GetX", contract="not-documented")]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DOC-001" in r.stdout


def test_doc002_event_contract_not_documented(tmp_path):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["dependencies"]["storage"] = [
        {"type": "postgres", "name": "main-db", "owned_by": "this service"}
    ]
    a["events"]["published"] = [
        {"topic": "x.created", "contract": "not-documented", "version": 1}
    ]
    b = _base("b")
    b["events"]["consumed"] = [
        {"topic": "x.created", "contract": "x.proto", "expected_version": 1}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", b)
    r = _run(tmp_path)
    assert "DOC-002" in r.stdout


def test_sla001_only_under_strict_mode(tmp_path):
    a = _base("a")
    a["metadata"]["archspec_strict"] = True
    a["api"]["endpoints"] = [
        _endpoint("GetX", p99="not-measured", availability="not-measured")
    ]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "SLA-001" in r.stdout
    assert r.stdout.count("SLA-001") == 2  # p99 + availability


def test_sla001_silent_in_non_strict_mode(tmp_path):
    a = _base("a")
    a["api"]["endpoints"] = [
        _endpoint("GetX", p99="not-measured", availability="not-measured")
    ]
    a["dependencies"]["upstream"] = [
        {"name": "b", "endpoints_used": ["GetX"], "discovered_via": "manual"}
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "SLA-001" not in r.stdout


def test_dep005_orphan_write_endpoint(tmp_path):
    """Mutating endpoint with no caller listed in upstream[] → DEP-005.

    Reproduces freelance-marketplace verification-service.VerifyIdentity scenario:
    only GetVerificationStatus is listed as called by upstream; VerifyIdentity
    is orphan.
    """
    a = _base("a")
    a["api"]["endpoints"] = [
        {
            "name": "VerifyIdentity",
            "protocol": "gRPC",
            "idempotency": {"required": True, "key_source": "metadata: x", "storage": "redis: x"},
            "contract": "x.proto",
            "sla": {"p99_latency": "500ms", "availability": "99.9%"},
        },
        {
            "name": "GetVerificationStatus",
            "protocol": "gRPC",
            "idempotency": {"required": False},
            "contract": "x.proto",
            "sla": {"p99_latency": "100ms", "availability": "99.9%"},
        },
    ]
    a["dependencies"]["upstream"] = [
        {
            "name": "b",
            "protocol": "gRPC",
            "endpoints_used": ["GetVerificationStatus"],
            "discovered_via": "monorepo-scan",
        }
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-005" in r.stdout
    assert "VerifyIdentity" in r.stdout
    # Read endpoint must NOT trigger DEP-005.
    issues_section = r.stdout.split("DEP-005")[1] if "DEP-005" in r.stdout else ""
    first_line = issues_section.split("\n")[0]
    assert "GetVerificationStatus" not in first_line


def test_dep005_silent_for_http_get_gateway_endpoint(tmp_path):
    """Bucket 5.3: HTTP `GET /...` endpoints must NOT be flagged as orphan writes.

    Reproduces the freelance-marketplace api-gateway scenario: 6 HTTP endpoints
    with names like `GET /api/v1/tasks` would all hit DEP-005 under the old
    is_read_endpoint heuristic.
    """
    a = _base("a")
    a["api"]["endpoints"] = [
        {
            "name": "GET /api/v1/tasks",
            "protocol": "HTTP",
            "idempotency": {"required": False},
            "contract": "api/openapi.yaml",
            "sla": {"p99_latency": "100ms", "availability": "99.9%"},
        },
        {
            "name": "POST /api/v1/tasks",
            "protocol": "HTTP",
            "idempotency": {
                "required": True,
                "key_source": "header: X-Idempotency-Key",
                "storage": "redis: idemp:{key}",
            },
            "contract": "api/openapi.yaml",
            "sla": {"p99_latency": "500ms", "availability": "99.9%"},
        },
    ]
    a["dependencies"]["upstream"] = []
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    # GET endpoint stays silent; POST is mutating + no caller → DEP-005 fires for it.
    assert "GET /api/v1/tasks" not in r.stdout
    assert "DEP-005" in r.stdout
    assert "POST /api/v1/tasks" in r.stdout


def test_dep005_silent_when_caller_uses_endpoint(tmp_path):
    """When upstream[].endpoints_used includes the endpoint, no DEP-005."""
    a = _base("a")
    a["api"]["endpoints"] = [
        {
            "name": "CreateThing",
            "protocol": "gRPC",
            "idempotency": {"required": True, "key_source": "metadata: x", "storage": "redis: x"},
            "contract": "x.proto",
            "sla": {"p99_latency": "500ms", "availability": "99.9%"},
        }
    ]
    a["dependencies"]["upstream"] = [
        {
            "name": "b",
            "protocol": "gRPC",
            "endpoints_used": ["CreateThing"],
            "discovered_via": "monorepo-scan",
        }
    ]
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    r = _run(tmp_path)
    assert "DEP-005" not in r.stdout


def test_apply_upstream_fixes_writes_missing_entries(tmp_path):
    """Reproduces freelance-marketplace task-service: api-gateway calls it, no upstream."""
    gw_yaml = tmp_path / "services" / "api-gateway" / "docs" / "SERVICE_MAP.yaml"
    gw_yaml.parent.mkdir(parents=True, exist_ok=True)
    gw = _base("api-gateway")
    gw["dependencies"]["downstream"]["sync"] = [
        {
            "service": "task-service",
            "timeout": "1s",
            "retries": 0,
            "fallback": "none",
            "on_failure": "propagate",
        }
    ]
    gw_yaml.write_text(yaml.safe_dump(gw, sort_keys=False), encoding="utf-8")

    task_doc = _base("task-service")
    task_yaml = tmp_path / "services" / "task-service" / "docs" / "SERVICE_MAP.yaml"
    task_yaml.parent.mkdir(parents=True, exist_ok=True)
    task_yaml.write_text(yaml.safe_dump(task_doc, sort_keys=False), encoding="utf-8")

    # Add a Go file in api-gateway that imports task/v1 and uses CreateTaskRequest
    proto_pkg = tmp_path / "services" / "api-gateway" / "internal"
    proto_pkg.mkdir(parents=True, exist_ok=True)
    (proto_pkg / "client.go").write_text(
        'package internal\n'
        'import taskv1 "github.com/x/task/v1"\n'
        'func F() { _ = taskv1.CreateTaskRequest{} }\n',
        encoding="utf-8",
    )

    # Pre-check: DEP-002 reported.
    pre = _run(tmp_path)
    assert "DEP-002" in pre.stdout

    # Default --apply-upstream-fixes is dry-run — file untouched.
    dry = _run(tmp_path, "--apply-upstream-fixes")
    assert dry.returncode == 0
    assert "dry-run" in dry.stdout
    assert "would add" in dry.stdout
    assert "Re-run with --write to apply." in dry.stdout
    assert task_yaml.read_text(encoding="utf-8") == yaml.safe_dump(task_doc, sort_keys=False)

    # With --write, file is mutated.
    fix = _run(tmp_path, "--apply-upstream-fixes", "--write")
    assert fix.returncode == 0
    assert "applied" in fix.stdout
    assert "task-service" in fix.stdout

    new_task_text = task_yaml.read_text(encoding="utf-8")
    assert "name: api-gateway" in new_task_text
    assert "discovered_via: monorepo-scan" in new_task_text

    # Post-check: DEP-002 cleared.
    post = _run(tmp_path)
    assert "DEP-002" not in post.stdout


def test_apply_upstream_fixes_no_callers_summary(tmp_path):
    """If reverse-scan finds no Go consumer for the missing edge, leave a summary line."""
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
    _write(tmp_path, "a", a)
    _write(tmp_path, "b", _base("b"))
    fix = _run(tmp_path, "--apply-upstream-fixes", "--write")
    assert fix.returncode == 0
    assert "Services modified: 0" in fix.stdout
    assert "no matching consumers" in fix.stdout


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
