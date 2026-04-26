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
