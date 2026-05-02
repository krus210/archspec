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
    assert report["aggregates"] == []


def test_scan_aggregates_detects_optimistic_via_cas_methods():
    report = _run(FIXTURES / "aggregates")
    by_name = {a["name"]: a for a in report["aggregates"]}
    assert "Task" in by_name
    assert by_name["Task"]["write_strategy"] == "optimistic"
    assert by_name["Task"]["confidence"] == "high"
    assert "Match" in by_name
    assert by_name["Match"]["write_strategy"] == "optimistic"


def test_scan_aggregates_ignores_mutex_outside_repository_scope():
    """A Mutex in usecase/ must not produce an aggregate finding."""
    report = _run(FIXTURES / "aggregates")
    names = {a["name"] for a in report["aggregates"]}
    assert "Service" not in names  # the usecase/handler.go Mutex


def test_scan_aggregates_detects_pessimistic_via_mutex_only():
    report = _run(FIXTURES / "aggregates_pessimistic")
    by_name = {a["name"]: a for a in report["aggregates"]}
    assert "Profile" in by_name
    assert by_name["Profile"]["write_strategy"] == "pessimistic"
    assert by_name["Profile"]["confidence"] == "medium"


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
    # Three resolved subjects (literals + const-table identifiers) PLUS
    # `<dynamic>` from `nc.Publish(e.Subject, ...)`. The dynamic call site
    # lives outside any wrapper body, so suppressing it would silently drop
    # publish-detection coverage — the user must see the call site to
    # confirm the topic by hand.
    assert pub == ["<dynamic>", "billing.invoice.v1", "geo.points.v1", "task.created"]
    assert con == ["match.found", "notifications.push"]
    for ev in report["events_published"] + report["events_consumed"]:
        assert ev["backend"] == "nats"
        assert ev["source"].startswith("main.go:")
    by_topic = {ev["topic"]: ev for ev in report["events_published"]}
    assert by_topic["task.created"]["confidence"] == "medium"
    assert by_topic["<dynamic>"]["confidence"] == "low"
    assert "x" not in pub


def test_scan_nats_outbox_wrapper_emits_publish_findings():
    """`func (o *Outbox) PublishMatchFound(...)` triggers wrapper heuristic.

    Reproduces freelance-marketplace finding #5 — task-service publishes via
    outbox poller; static scanner used to miss it.

    Also exercises the Bucket 5.2 collapse: there must be no `<dynamic>`
    duplicates and no double `match.found` entries despite both `_emit`
    (via const-resolved local var) and the wrapper heuristic firing.
    """
    report = _run(FIXTURES / "nats_outbox_wrapper")
    pub_topics = sorted(t["topic"] for t in report["events_published"])
    assert pub_topics == ["match.found", "task.created"]
    by_topic = {t["topic"]: t for t in report["events_published"]}
    assert by_topic["match.found"]["confidence"] == "medium"
    assert by_topic["task.created"]["confidence"] == "low"


def test_scan_nats_dynamic_kept_when_no_resolved_alternative():
    """`<dynamic>` is suppressed only inside wrapper bodies.

    With no wrapper at all and only a dynamic publish, the marker must
    survive — losing the call site entirely would silently drop publish-
    detection coverage.
    """
    report = _run(FIXTURES / "nats_only_dynamic")
    pub_topics = [t["topic"] for t in report["events_published"]]
    assert pub_topics == ["<dynamic>"]
    assert report["events_published"][0]["confidence"] == "low"


def test_scan_nats_dynamic_kept_outside_wrapper_body():
    """Independent dynamic call alongside a literal publish in the same file.

    Bucket 5.6: the file-wide suppression that earlier shipped in v0.6.0 was
    too broad — it dropped the dynamic finding here because the file also
    held a resolved literal. Refined logic only suppresses ``<dynamic>``
    when its source line falls inside a wrapper body, so this fixture must
    return BOTH the literal and the dynamic call site.

    Bucket 5.8: pin the source lines so a future regression where the
    scanner starts matching publish-syntax inside Go comments would surface
    immediately (the source would point to a comment line instead of the
    real call).
    """
    report = _run(FIXTURES / "nats_dynamic_outside_wrapper")
    pub_topics = sorted(t["topic"] for t in report["events_published"])
    assert pub_topics == ["<dynamic>", "foo.created"]
    by_topic = {t["topic"]: t for t in report["events_published"]}
    assert by_topic["foo.created"]["confidence"] == "medium"
    assert by_topic["foo.created"]["source"] == "main.go:17"
    assert by_topic["<dynamic>"]["confidence"] == "low"
    assert by_topic["<dynamic>"]["source"] == "main.go:21"


def test_scan_nats_short_wrapper_does_not_swallow_dynamic_below():
    """Short wrapper body must not absorb dynamic publishes that follow it.

    Bucket 5.6 (refined): the previous range was a fixed 30-line lookahead
    from the wrapper signature, which would extend past the function's real
    closing `}` and silently suppress unrelated publishes a few lines later.
    Real brace-balanced ranges stop at the wrapper's `}` exactly.

    Bucket 5.8: assert source lines so a phantom finding from a comment
    that happens to contain Publish-call syntax would be caught — the
    fixture comment is deliberately written to avoid such false positives.
    """
    report = _run(FIXTURES / "nats_short_wrapper_outside_dynamic")
    pub_topics = sorted(t["topic"] for t in report["events_published"])
    assert pub_topics == ["<dynamic>", "foo.created"]
    by_topic = {t["topic"]: t for t in report["events_published"]}
    assert by_topic["foo.created"]["confidence"] == "medium"
    assert by_topic["foo.created"]["source"] == "main.go:22"
    assert by_topic["<dynamic>"]["confidence"] == "low"
    assert by_topic["<dynamic>"]["source"] == "main.go:30"


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


def test_scan_grpc_finds_proto_contract_in_sibling_directory():
    # Layout: <root>/svc/main.go + <root>/proto/geo/v1/geo.proto.
    report = _run(FIXTURES / "grpc_with_proto" / "svc")
    geo = next(e for e in report["endpoints"] if e["protocol"] == "gRPC")
    assert geo["name"] == "GeoServiceServer"
    assert geo["contract_hint"].endswith("proto/geo/v1/geo.proto")


def test_scan_grpc_without_proto_omits_contract_hint():
    # The plain grpc_server fixture has no proto/ tree → no contract_hint key.
    report = _run(FIXTURES / "grpc_server")
    for ep in report["endpoints"]:
        if ep["protocol"] == "gRPC":
            assert "contract_hint" not in ep


def test_scan_grpc_server_finds_registered_services():
    report = _run(FIXTURES / "grpc_server")
    grpc = sorted(
        e["name"] for e in report["endpoints"] if e["protocol"] == "gRPC"
    )
    # Without proto/ tree, scanner falls back to one summary entry per server.
    assert grpc == ["GeoServiceServer", "TaskServiceServer"]
    for ep in report["endpoints"]:
        if ep["protocol"] == "gRPC":
            assert ep["source"].startswith("main.go:")
            assert ep["confidence"] == "high"


def test_scan_grpc_enumerates_rpc_methods_from_proto():
    """When proto/<domain>/v1/*.proto exists, emit one endpoint per RPC method.

    Reproduces fix for freelance-marketplace finding #6 — config-service /
    worker-profile / portfolio-service had their RPC methods undercounted.
    """
    report = _run(FIXTURES / "grpc_with_rpc" / "svc")
    grpc = [e for e in report["endpoints"] if e["protocol"] == "gRPC"]
    names = sorted(e["name"] for e in grpc)
    assert names == ["CancelOrder", "CreateOrder", "GetOrder"]
    for ep in grpc:
        assert ep["path"].startswith("OrderServiceServer/")
        assert ep["confidence"] == "high"
        assert ep["contract_hint"].endswith("order.proto")


def test_scan_http_finds_openapi_contract():
    """When ``api/schema.yaml`` exists alongside Go HTTP routes, attach it as contract_hint."""
    report = _run(FIXTURES / "http_with_openapi")
    http_eps = [e for e in report["endpoints"] if e["protocol"] == "HTTP"]
    assert http_eps, "expected HTTP endpoints"
    for ep in http_eps:
        assert ep["contract_hint"] == "api/schema.yaml"


def test_scan_http_no_openapi_omits_contract_hint():
    """Plain HTTP fixture without openapi files — no contract_hint produced."""
    report = _run(FIXTURES / "http_routes")
    for ep in report["endpoints"]:
        if ep["protocol"] == "HTTP":
            assert "contract_hint" not in ep


def test_scan_grpc_multi_service_isolates_rpc_to_matching_block():
    """When a proto declares multiple service blocks, the scanner must only
    enumerate RPCs from the block matching the registered server.

    Reproduces a bleed bug where `_parse_proto_rpc_methods` walked the entire
    file: `RegisterBillingServiceServer` would have picked up admin RPCs.

    Bucket 5.7: the secondary `RegisterBillingAdminServiceServer` register
    call domain-derives to `billing-admin`, which has no matching proto
    tree. The fallback must probe protos already located for siblings in
    the same Go file (here: `proto/billing/v1/billing.proto`) and match
    the `service BillingAdminService { ... }` block, yielding Refund /
    Reconcile rather than a single summary entry.
    """
    report = _run(FIXTURES / "grpc_multi_service" / "svc")
    grpc = sorted(
        e["name"] for e in report["endpoints"] if e["protocol"] == "gRPC"
    )
    assert grpc == ["Charge", "Quote", "Reconcile", "Refund"]
    by_name = {e["name"]: e for e in report["endpoints"] if e["protocol"] == "gRPC"}
    assert by_name["Charge"]["path"].startswith("BillingServiceServer/")
    assert by_name["Refund"]["path"].startswith("BillingAdminServiceServer/")
    for ep in report["endpoints"]:
        if ep["protocol"] == "gRPC":
            assert ep["contract_hint"].endswith("billing.proto")


def test_scan_grpc_falls_back_when_proto_has_no_rpc():
    """When proto exists but is empty, fall back to single Register*Server entry."""
    report = _run(FIXTURES / "grpc_with_proto" / "svc")
    grpc = [e for e in report["endpoints"] if e["protocol"] == "gRPC"]
    assert len(grpc) == 1
    assert grpc[0]["name"] == "GeoServiceServer"


def _run_reverse(repo_root: Path, target: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCAN), "--reverse-scan", str(repo_root), "--target", target],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert r.returncode == 0, f"reverse scan failed: {r.stderr}"
    return json.loads(r.stdout)


def test_reverse_scan_finds_consumer_services():
    report = _run_reverse(FIXTURES / "reverse_scan", "geo-service")
    names = sorted(c["name"] for c in report["consumers"])
    assert names == ["api-gateway", "matching-service"]


def test_reverse_scan_extracts_method_names():
    report = _run_reverse(FIXTURES / "reverse_scan", "geo-service")
    by_name = {c["name"]: c for c in report["consumers"]}
    assert by_name["api-gateway"]["endpoints_used"] == ["GetCity", "GetDistance"]
    assert by_name["matching-service"]["endpoints_used"] == ["GetDistance"]
    for c in report["consumers"]:
        assert c["protocol"] == "gRPC"
        assert c["confidence"] == "high"
        assert c["discovered_via"] == "monorepo-scan"
        assert c["source"].endswith(".go:6")


def test_reverse_scan_excludes_target_service_itself():
    report = _run_reverse(FIXTURES / "reverse_scan", "geo-service")
    names = {c["name"] for c in report["consumers"]}
    assert "geo-service" not in names


def test_reverse_scan_returns_empty_for_unused_target():
    report = _run_reverse(FIXTURES / "reverse_scan", "billing-service")
    assert report["consumers"] == []
    assert report["target"] == "billing-service"


def test_reverse_scan_requires_target_argument():
    r = subprocess.run(
        [sys.executable, str(SCAN), "--reverse-scan", str(FIXTURES / "reverse_scan")],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert r.returncode == 2
    assert "--target" in r.stderr


def test_reverse_scan_rejects_missing_repo_dir():
    r = subprocess.run(
        [sys.executable, str(SCAN), "--reverse-scan", str(FIXTURES / "does-not-exist"),
         "--target", "geo-service"],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    assert r.returncode == 2
    assert "not a directory" in r.stderr.lower()


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
