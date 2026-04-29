import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))

from checks.check_graph_consistency import run as check_graph  # noqa: E402


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


def _write(repo: Path, service_name: str, doc: dict) -> str:
    rel = f"services/{service_name}/docs/SERVICE_MAP.yaml"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return rel


def test_single_service_silent(stage_file, fixture_yaml_text, git_repo):
    text = fixture_yaml_text("valid/minimal.yaml")
    stage_file("docs/SERVICE_MAP.yaml", text)
    assert check_graph(["docs/SERVICE_MAP.yaml"], cwd=git_repo) == []


def test_pair_aligned_passes(git_repo):
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
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert findings == []


def test_dep002_caller_not_listed_as_upstream(git_repo):
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
    b = _base("b")  # b.upstream is empty
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert any(f.rule == "DEP-002" and f.severity == "WARN" for f in findings)
    assert any(
        "'a' calls 'b' but 'b' does not list it as upstream" in f.message for f in findings
    )


def test_dep003_orphan_published_event(git_repo):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [{"topic": "x.created", "contract": "x.proto", "version": 1}]
    b = _base("b")  # nobody consumes x.created
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert any(f.rule == "DEP-003" and "x.created" in f.message for f in findings)


def test_dep003_consumer_present_silent(git_repo):
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [{"topic": "x.created", "contract": "x.proto", "version": 1}]
    b = _base("b")
    b["events"]["consumed"] = [
        {"topic": "x.created", "contract": "x.proto", "expected_version": 1}
    ]
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert all(f.rule != "DEP-003" for f in findings)


def test_dep004_upstream_not_reflected(git_repo):
    """Reproduces freelance-marketplace geo-service.upstream=api-gateway bug."""
    geo = _base("geo")
    geo["dependencies"]["upstream"] = [
        {"name": "gw", "protocol": "gRPC", "discovered_via": "manual"}
    ]
    gw = _base("gw")  # gw.downstream is empty + no shared event
    rel_geo = _write(git_repo, "geo", geo)
    _write(git_repo, "gw", gw)
    findings = check_graph([rel_geo], cwd=git_repo)
    assert any(f.rule == "DEP-004" and "geo" in f.message and "gw" in f.message for f in findings)


def test_dep004_silent_when_event_link_exists(git_repo):
    """If A.upstream lists B, and B consumes A's published event, counts as link."""
    a = _base("a")
    a["consistency"]["write_path"]["pattern"] = "outbox"
    a["events"]["published"] = [{"topic": "x.created", "contract": "x.proto", "version": 1}]
    a["dependencies"]["upstream"] = [
        {"name": "b", "protocol": "gRPC", "discovered_via": "manual"}
    ]
    b = _base("b")
    b["events"]["consumed"] = [
        {"topic": "x.created", "contract": "x.proto", "expected_version": 1}
    ]
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert all(f.rule != "DEP-004" for f in findings)


def test_dep002_silent_when_callee_has_no_servicemap(git_repo):
    """Calling a sibling without SERVICE_MAP must not WARN — partial monorepo."""
    a = _base("a")
    a["dependencies"]["downstream"]["sync"] = [
        {
            "service": "external",  # no SERVICE_MAP for 'external'
            "timeout": "1s",
            "retries": 0,
            "fallback": "none",
            "on_failure": "propagate",
        }
    ]
    rel_a = _write(git_repo, "a", a)
    # write a sibling so we cross the >= 2 threshold for the lint to engage
    _write(git_repo, "b", _base("b"))
    findings = check_graph([rel_a], cwd=git_repo)
    assert all(f.rule != "DEP-002" for f in findings)


def test_strict_mode_does_not_promote_to_block(git_repo):
    """DEP-002/003/004 must remain WARN even with archspec_strict."""
    a = _base("a")
    a["metadata"]["archspec_strict"] = True
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
    rel_a = _write(git_repo, "a", a)
    _write(git_repo, "b", b)
    findings = check_graph([rel_a], cwd=git_repo)
    assert findings  # we expect DEP-002
    assert all(f.severity == "WARN" for f in findings)
