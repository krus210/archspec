from pathlib import Path

import yaml
from generate_mermaid import generate_container, generate_context, generate_sequence

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "diagrams"
FULL_YAML = ROOT / "tests" / "fixtures" / "yaml" / "valid" / "full.yaml"


def test_context_diagram_matches_golden():
    doc = yaml.safe_load(FULL_YAML.read_text(encoding="utf-8"))
    actual = generate_context(doc)
    expected = (GOLDEN / "context.mmd").read_text(encoding="utf-8")
    assert actual == expected


def test_container_diagram_matches_golden():
    doc = yaml.safe_load(FULL_YAML.read_text(encoding="utf-8"))
    actual = generate_container(doc)
    expected = (GOLDEN / "container.mmd").read_text(encoding="utf-8")
    assert actual == expected


def test_sequence_diagram_matches_golden():
    doc = yaml.safe_load(FULL_YAML.read_text(encoding="utf-8"))
    actual = generate_sequence(doc)
    expected = (GOLDEN / "sequence.mmd").read_text(encoding="utf-8")
    assert actual == expected


def _doc_with_endpoints(endpoint_names: list[str]) -> dict:
    return {
        "service": {"name": "demo"},
        "api": {
            "endpoints": [
                {
                    "name": n,
                    "protocol": "gRPC",
                    "idempotency": {"required": False},
                    "contract": "TODO",
                    "sla": {"p99_latency": "TODO", "availability": "TODO"},
                }
                for n in endpoint_names
            ],
        },
        "dependencies": {
            "upstream": [],
            "downstream": {"sync": [], "async": []},
            "storage": [{"type": "in-memory", "name": "store", "owned_by": "this service"}],
        },
        "events": {"published": [], "consumed": []},
    }


def test_sequence_marks_get_endpoints_as_read():
    doc = _doc_with_endpoints(["GetCity", "ListUsers", "FindOrder", "SearchAds"])
    out = generate_sequence(doc)
    # All four are read-prefixed → no `write` should appear in the storage edges.
    assert "svc->>store: write" not in out
    # Read should appear at least once for each endpoint (4 storage edges).
    assert out.count("svc->>store: read") == 4


def test_sequence_marks_mutating_endpoints_as_write():
    doc = _doc_with_endpoints(["CreateTask", "UpdateProfile", "DeleteAccount"])
    out = generate_sequence(doc)
    assert "svc->>store: read" not in out
    assert out.count("svc->>store: write") == 3


def test_sequence_handles_mixed_endpoints():
    doc = _doc_with_endpoints(["GetCity", "CreateCity"])
    out = generate_sequence(doc)
    assert out.count("svc->>store: read") == 1
    assert out.count("svc->>store: write") == 1


def _doc_with_upstream(upstream: list) -> dict:
    return {
        "service": {"name": "geo-service"},
        "api": {"endpoints": []},
        "dependencies": {
            "upstream": upstream,
            "downstream": {"sync": [], "async": []},
            "storage": [],
        },
        "events": {"published": [], "consumed": []},
    }


def test_container_renders_legacy_string_upstream():
    out = generate_container(_doc_with_upstream(["api-gateway"]))
    assert "up_api-gateway[api-gateway] --> svc" in out


def test_container_renders_structured_upstream_with_method_labels():
    upstream = [{
        "name": "matching-service",
        "protocol": "gRPC",
        "endpoints_used": ["GetDistance", "GetCity"],
        "discovered_via": "monorepo-scan",
    }]
    out = generate_container(_doc_with_upstream(upstream))
    assert (
        "up_matching-service[matching-service] -->|GetDistance, GetCity| svc"
        in out
    )


def test_sequence_does_not_smoosh_storage_and_response_lines():
    """Regression test for v0.4.0: trim_blocks ate the newline after `{% endif %}`,
    causing `svc->>store: write` and `svc-->>client: response` to render on the same line.
    """
    doc = _doc_with_endpoints(["CreateTask", "GetTask"])
    out = generate_sequence(doc)
    assert "svc->>store: write  svc-->>client" not in out
    assert "svc->>store: read  svc-->>client" not in out
    assert "svc->>store: write\n  svc-->>client: response" in out
    assert "svc->>store: read\n  svc-->>client: response" in out


def _doc_with_published(endpoint_names: list[str], published: list[dict]) -> dict:
    return {
        "service": {"name": "task-service"},
        "api": {
            "endpoints": [
                {
                    "name": n,
                    "protocol": "gRPC",
                    "idempotency": {"required": False},
                    "contract": "TODO",
                    "sla": {"p99_latency": "TODO", "availability": "TODO"},
                }
                for n in endpoint_names
            ],
        },
        "dependencies": {
            "upstream": [],
            "downstream": {"sync": [], "async": []},
            "storage": [{"type": "in-memory", "name": "store", "owned_by": "this service"}],
        },
        "events": {"published": published, "consumed": []},
    }


def test_sequence_emits_publish_edge_for_write_endpoints():
    doc = _doc_with_published(
        ["CreateTask", "GetTask"],
        [{"topic": "task.created", "contract": "TODO", "version": 1}],
    )
    out = generate_sequence(doc)
    # Participant must be declared once.
    assert out.count("participant events as message-bus") == 1
    # Publish line must appear under CreateTask (write) but NOT under GetTask (read).
    assert "svc->>events: publish task.created (v1)" in out
    assert out.count("svc->>events: publish") == 1


def test_sequence_omits_message_bus_when_no_published_events():
    doc = _doc_with_published(["CreateTask"], [])
    out = generate_sequence(doc)
    assert "message-bus" not in out
    assert "publish" not in out


def test_container_omits_endpoint_boxes():
    """Endpoints (gRPC GetCity etc.) must not appear as boxes anymore."""
    doc = _doc_with_endpoints(["GetCity", "CreateTask"])
    out = generate_container(doc)
    assert "gRPC GetCity" not in out
    assert "ep_getcity" not in out
