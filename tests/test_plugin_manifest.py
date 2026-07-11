import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_plugin_manifest_loads_and_has_required_fields():
    manifest_path = ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["name"] == "archspec"
    assert data["version"] == "0.12.0"
    assert "description" in data


def test_commands_directory_has_all_expected_files():
    cmd_dir = ROOT / "commands"
    expected = {
        "init.md",
        "sync.md",
        "validate.md",
        "investigate.md",
        "check-architecture.md",
        "implement.md",
    }
    assert {p.name for p in cmd_dir.glob("*.md")} == expected


def test_skills_directory_layout():
    skills = ROOT / "skills"
    assert (skills / "architecture-sync" / "SKILL.md").is_file()
    assert (skills / "architecture-investigate" / "SKILL.md").is_file()
    # Architecture-sync also ships scripts and templates and schema.
    assert (skills / "architecture-sync" / "scripts").is_dir()
    assert (skills / "architecture-sync" / "templates").is_dir()
    assert (skills / "architecture-sync" / "schema" / "servicemap.schema.json").is_file()
