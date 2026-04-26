import hashlib
from pathlib import Path

import yaml
from generate_mermaid import generate_container, generate_context, generate_sequence
from render_architecture_md import render_architecture_md

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "tests" / "fixtures" / "yaml" / "valid" / "full.yaml"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_generators_are_byte_for_byte_stable_over_20_runs():
    doc = yaml.safe_load(FULL.read_text(encoding="utf-8"))
    fns = {
        "context": generate_context,
        "container": generate_container,
        "sequence": generate_sequence,
        "architecture_md": render_architecture_md,
    }
    hashes = {name: set() for name in fns}
    for _ in range(20):
        for name, fn in fns.items():
            hashes[name].add(_sha(fn(doc)))
    for name, h in hashes.items():
        assert len(h) == 1, f"{name} produced {len(h)} distinct outputs across 20 runs"


def test_no_environment_dependence(tmp_path, monkeypatch):
    """Output must not depend on TZ, LANG, PYTHONHASHSEED, or random state."""
    doc = yaml.safe_load(FULL.read_text(encoding="utf-8"))
    baseline = generate_context(doc)
    monkeypatch.setenv("TZ", "Pacific/Auckland")
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    monkeypatch.setenv("PYTHONHASHSEED", "12345")
    assert generate_context(doc) == baseline


def test_output_uses_lf_line_endings_and_trailing_newline(tmp_path):
    out_dir = tmp_path / "out"
    from generate_mermaid import main as gen_main
    gen_main([str(FULL), str(out_dir)])
    for f in out_dir.glob("*.mmd"):
        data = f.read_bytes()
        assert b"\r" not in data, f"{f} contains CR"
        assert data.endswith(b"\n"), f"{f} missing trailing newline"


def test_generators_do_not_import_forbidden_modules():
    forbidden = ["datetime", "random", "uuid", "time", "secrets"]
    scripts_dir = ROOT / "skills" / "architecture-sync" / "scripts"
    for py in scripts_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for mod in forbidden:
            assert f"import {mod}" not in text, f"{py.name} imports {mod}"
            assert f"from {mod}" not in text, f"{py.name} imports from {mod}"
