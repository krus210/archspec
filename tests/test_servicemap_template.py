"""Sanity checks on the seed SERVICE_MAP.yaml template."""

from __future__ import annotations

from pathlib import Path

import yaml

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "architecture-sync"
    / "templates"
    / "SERVICE_MAP.template.yaml"
)


def test_template_loads_as_yaml():
    doc = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert "service" in doc
    assert "dependencies" in doc


def test_seed_write_path_is_direct():
    """Seed default should be `direct`; outbox must be earned via storage + events.

    Rationale: outbox without durable storage (e.g. on a stateless gateway) is a
    structural lie. `direct` is the safe default that the bootstrap flow can
    upgrade to outbox/saga based on observed code.
    """
    doc = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert doc["consistency"]["write_path"]["pattern"] == "direct"
