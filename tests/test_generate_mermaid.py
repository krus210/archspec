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
