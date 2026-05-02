"""Tests for apply_upstream.py — deterministic merge of reverse-scan consumers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "architecture-sync" / "scripts" / "apply_upstream.py"

sys.path.insert(0, str(SCRIPT.parent))

# noqa: E402 — sys.path mutation precedes the import on purpose so that the
# script-under-test can be loaded without packaging.
from apply_upstream import (  # noqa: E402, I001
    merge_upstream,
    render_upstream_block,
    replace_upstream_block,
)


_BASE_YAML = """\
metadata:
  schema_version: "1.0"
  source_of_truth: local
  drift_check_in_ci: true
  last_reviewed: "2026-05-02"

service:
  name: task-service
  team: x
  language: go
  repo: https://github.com/x/y
  domain: tasks
  ownership:
    primary: "@x"
    oncall: "@x"
  responsibilities:
    - "manage tasks"
  invariants:
    - "id is unique"

api:
  version: 1
  endpoints: []
  changelog: []

dependencies:
  upstream: []
  downstream:
    sync: []
    async: []
  storage: []

events:
  published: []
  consumed: []

consistency:
  model: eventual
  bounded_aggregate: tasks
  write_path:
    pattern: outbox
  read_path:
    consistency: eventual
  cross_service_invariants: []

concurrency:
  aggregates: []
  hot_keys: []
  shared_state: []
"""


def _scan_payload(consumers: list[dict]) -> dict:
    return {
        "repo_root": "/tmp/repo",
        "target": "task-service",
        "files_scanned": 5,
        "consumers": consumers,
    }


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )


def test_merge_empty_existing_adds_scan_consumers():
    consumers = [
        {
            "name": "api-gateway",
            "protocol": "gRPC",
            "endpoints_used": ["CreateTask", "GetTask"],
            "discovered_via": "monorepo-scan",
        }
    ]
    merged = merge_upstream([], consumers)
    assert len(merged) == 1
    assert merged[0]["name"] == "api-gateway"
    assert merged[0]["protocol"] == "gRPC"
    assert merged[0]["endpoints_used"] == ["CreateTask", "GetTask"]
    assert merged[0]["discovered_via"] == "monorepo-scan"


def test_merge_upgrades_bare_string_to_dict():
    existing = ["api-gateway"]
    consumers = [
        {
            "name": "api-gateway",
            "protocol": "gRPC",
            "endpoints_used": ["GetTask"],
            "discovered_via": "monorepo-scan",
        }
    ]
    merged = merge_upstream(existing, consumers)
    assert len(merged) == 1
    assert merged[0]["name"] == "api-gateway"
    assert merged[0]["protocol"] == "gRPC"
    assert merged[0]["endpoints_used"] == ["GetTask"]
    assert merged[0]["discovered_via"] == "monorepo-scan"


def test_merge_preserves_manual_provenance():
    existing = [
        {
            "name": "api-gateway",
            "protocol": "HTTP",
            "endpoints_used": ["LegacyEndpoint"],
            "discovered_via": "manual",
        }
    ]
    consumers = [
        {
            "name": "api-gateway",
            "protocol": "gRPC",
            "endpoints_used": ["GetTask", "CreateTask"],
            "discovered_via": "monorepo-scan",
        }
    ]
    merged = merge_upstream(existing, consumers)
    assert len(merged) == 1
    assert merged[0]["discovered_via"] == "manual"
    assert merged[0]["protocol"] == "HTTP"  # manual not overwritten
    assert merged[0]["endpoints_used"] == sorted({"LegacyEndpoint", "GetTask", "CreateTask"})


def test_merge_unions_endpoints_for_non_manual_existing():
    existing = [
        {
            "name": "api-gateway",
            "protocol": "gRPC",
            "endpoints_used": ["GetTask"],
            "discovered_via": "monorepo-scan",
        }
    ]
    consumers = [
        {
            "name": "api-gateway",
            "protocol": "gRPC",
            "endpoints_used": ["CreateTask", "GetTask"],
            "discovered_via": "monorepo-scan",
        }
    ]
    merged = merge_upstream(existing, consumers)
    assert merged[0]["endpoints_used"] == ["CreateTask", "GetTask"]


def test_render_empty_upstream_uses_inline_array():
    assert render_upstream_block([]) == "  upstream: []\n"


def test_render_structured_entry():
    rendered = render_upstream_block(
        [
            {
                "name": "api-gateway",
                "protocol": "gRPC",
                "endpoints_used": ["CreateTask", "GetTask"],
                "discovered_via": "monorepo-scan",
            }
        ]
    )
    assert rendered == (
        "  upstream:\n"
        "    - name: api-gateway\n"
        "      protocol: gRPC\n"
        "      endpoints_used:\n"
        "        - CreateTask\n"
        "        - GetTask\n"
        "      discovered_via: monorepo-scan\n"
    )


def test_replace_block_preserves_other_sections():
    new_block = render_upstream_block(
        [{"name": "foo", "protocol": "gRPC", "discovered_via": "monorepo-scan"}]
    )
    new_text = replace_upstream_block(_BASE_YAML, new_block)
    assert "metadata:" in new_text
    assert "concurrency:" in new_text
    assert "  upstream:\n    - name: foo" in new_text
    assert "  upstream: []" not in new_text


def test_replace_block_handles_existing_list_form():
    yaml_with_list = _BASE_YAML.replace(
        "  upstream: []",
        "  upstream:\n    - name: old\n      protocol: gRPC\n      discovered_via: manual",
    )
    new_block = render_upstream_block(
        [{"name": "new", "protocol": "gRPC", "discovered_via": "monorepo-scan"}]
    )
    new_text = replace_upstream_block(yaml_with_list, new_block)
    assert "name: old" not in new_text
    assert "name: new" in new_text
    assert "  downstream:" in new_text


def test_replace_block_raises_when_dependencies_missing():
    with pytest.raises(ValueError, match="dependencies"):
        replace_upstream_block("service:\n  name: x\n", "  upstream: []\n")


def test_cli_diff_output(tmp_path: Path):
    yaml_path = tmp_path / "SERVICE_MAP.yaml"
    yaml_path.write_text(_BASE_YAML, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(
        json.dumps(
            _scan_payload(
                [
                    {
                        "name": "api-gateway",
                        "protocol": "gRPC",
                        "endpoints_used": ["CreateTask"],
                        "discovered_via": "monorepo-scan",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    r = _run(str(yaml_path), "--reverse-scan-json", str(scan_path))
    assert r.returncode == 0
    assert "+    - name: api-gateway" in r.stdout
    assert yaml_path.read_text(encoding="utf-8") == _BASE_YAML  # not written


def test_cli_write_modifies_file(tmp_path: Path):
    yaml_path = tmp_path / "SERVICE_MAP.yaml"
    yaml_path.write_text(_BASE_YAML, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(
        json.dumps(
            _scan_payload(
                [
                    {
                        "name": "api-gateway",
                        "protocol": "gRPC",
                        "endpoints_used": ["CreateTask", "GetTask"],
                        "discovered_via": "monorepo-scan",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    r = _run(str(yaml_path), "--reverse-scan-json", str(scan_path), "--write")
    assert r.returncode == 0
    new_text = yaml_path.read_text(encoding="utf-8")
    assert "    - name: api-gateway" in new_text
    assert "      endpoints_used:" in new_text


def test_cli_write_idempotent(tmp_path: Path):
    """Running --write twice produces identical bytes."""
    yaml_path = tmp_path / "SERVICE_MAP.yaml"
    yaml_path.write_text(_BASE_YAML, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(
        json.dumps(
            _scan_payload(
                [
                    {
                        "name": "api-gateway",
                        "protocol": "gRPC",
                        "endpoints_used": ["GetTask"],
                        "discovered_via": "monorepo-scan",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    _run(str(yaml_path), "--reverse-scan-json", str(scan_path), "--write")
    first = yaml_path.read_bytes()
    _run(str(yaml_path), "--reverse-scan-json", str(scan_path), "--write")
    assert yaml_path.read_bytes() == first
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(yaml_path.read_bytes()).hexdigest()


def test_cli_protocol_filter(tmp_path: Path):
    yaml_path = tmp_path / "SERVICE_MAP.yaml"
    yaml_path.write_text(_BASE_YAML, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(
        json.dumps(
            _scan_payload(
                [
                    {
                        "name": "grpc-caller",
                        "protocol": "gRPC",
                        "endpoints_used": ["X"],
                        "discovered_via": "monorepo-scan",
                    },
                    {
                        "name": "http-caller",
                        "protocol": "HTTP",
                        "endpoints_used": ["Y"],
                        "discovered_via": "monorepo-scan",
                    },
                ]
            )
        ),
        encoding="utf-8",
    )
    r = _run(
        str(yaml_path),
        "--reverse-scan-json",
        str(scan_path),
        "--write",
        "--protocol-filter",
        "gRPC",
    )
    assert r.returncode == 0
    new_text = yaml_path.read_text(encoding="utf-8")
    assert "name: grpc-caller" in new_text
    assert "name: http-caller" not in new_text


def test_cli_no_changes_message(tmp_path: Path):
    yaml_path = tmp_path / "SERVICE_MAP.yaml"
    yaml_path.write_text(_BASE_YAML, encoding="utf-8")
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload([])), encoding="utf-8")
    r = _run(str(yaml_path), "--reverse-scan-json", str(scan_path))
    assert r.returncode == 0
    assert "no changes" in r.stdout


def test_cli_missing_yaml_returns_2(tmp_path: Path):
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(_scan_payload([])), encoding="utf-8")
    r = _run(str(tmp_path / "missing.yaml"), "--reverse-scan-json", str(scan_path))
    assert r.returncode == 2
