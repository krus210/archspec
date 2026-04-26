from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS = ROOT / "skills"

EXPECTED = ["architecture-sync", "architecture-investigate"]


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    out = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_each_skill_has_skill_md_with_frontmatter():
    for name in EXPECTED:
        path = SKILLS / name / "SKILL.md"
        assert path.is_file(), f"missing SKILL.md for {name}"
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        assert fm.get("name") == name, f"{name}: frontmatter name mismatch"
        assert fm.get("description"), f"{name}: missing description"
        # description should mention the trigger phrases or the slash command
        desc = fm["description"].lower()
        assert any(s in desc for s in ("/archspec:", "use when", "regenerates", "read-only"))


def test_architecture_sync_skill_references_all_scripts():
    text = (SKILLS / "architecture-sync" / "SKILL.md").read_text(encoding="utf-8")
    for script in ("validate_servicemap.py", "sync.py", "validate_mermaid.py"):
        assert script in text, f"architecture-sync SKILL.md does not reference {script}"


def test_architecture_investigate_skill_is_read_only():
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "read-only" in text or "do not" in text
    # Belt-and-braces: the skill must NOT mention sync.py / git add — those would be writes.
    assert "git add" not in text
    assert "sync.py" not in text
