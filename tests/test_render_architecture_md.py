from pathlib import Path

import yaml
from render_architecture_md import render_architecture_md

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "ARCHITECTURE.md"
FULL = ROOT / "tests" / "fixtures" / "yaml" / "valid" / "full.yaml"


def test_architecture_md_matches_golden():
    doc = yaml.safe_load(FULL.read_text(encoding="utf-8"))
    actual = render_architecture_md(doc)
    expected = GOLDEN.read_text(encoding="utf-8")
    assert actual == expected
