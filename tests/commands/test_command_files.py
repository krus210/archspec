from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS = ROOT / "commands"

EXPECTED = ["init.md", "sync.md", "validate.md", "investigate.md"]


def _read_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    out = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_all_commands_present():
    for name in EXPECTED:
        assert (COMMANDS / name).is_file(), f"missing {name}"


def test_each_command_has_frontmatter_with_name_and_description():
    for name in EXPECTED:
        text = (COMMANDS / name).read_text(encoding="utf-8")
        fm = _read_frontmatter(text)
        assert fm.get("description"), f"{name}: missing description"
        # Slash-command name must match the file name.
        slash = name.removesuffix(".md")
        assert slash in text, f"{name}: body should reference its own slash command"


def test_each_command_delegates_to_a_skill():
    for name in EXPECTED:
        text = (COMMANDS / name).read_text(encoding="utf-8")
        # Init/sync/investigate delegate to a skill; validate runs scripts directly + skill ref.
        assert "skills/architecture-" in text, f"{name}: must reference its skill"
