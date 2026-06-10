from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS = ROOT / "commands"

EXPECTED = [
    "init.md",
    "sync.md",
    "validate.md",
    "investigate.md",
    "implement.md",
    "check-architecture.md",
]


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


def test_validate_supports_monorepo():
    """task_3 ran in a monorepo (12 services, each with its own
    docs/SERVICE_MAP.yaml, none at the repo root) and /archspec:validate could
    not run at all. validate must discover every service map and lint each
    service, not assume a single root contract.
    """
    text = (COMMANDS / "validate.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "find" in low and "docs/service_map.yaml" in low, (
        "validate must discover */docs/SERVICE_MAP.yaml files instead of assuming the root"
    )
    assert "monorepo" in low, "validate must name its monorepo mode"
    assert "--service-map" in text and "--code" in text, (
        "the per-service loop passes --service-map/--code per service directory"
    )
    assert "per service" in low or "each service" in low, (
        "the report aggregates findings grouped per service"
    )


def test_plugin_paths_resolve_via_plugin_root():
    """When archspec runs as an installed plugin, ${CLAUDE_PROJECT_DIR} points
    at the *consumer* repo which has no hooks/ linters/ bin/. Every plugin-asset
    path must resolve via CLAUDE_PLUGIN_ROOT (with a project-dir fallback for
    developing archspec itself).
    """
    import re

    for rel in ("validate.md", "check-architecture.md"):
        text = (COMMANDS / rel).read_text(encoding="utf-8")
        assert "CLAUDE_PLUGIN_ROOT" in text, f"{rel}: must resolve assets via CLAUDE_PLUGIN_ROOT"
        assert not re.search(r"\$\{CLAUDE_PROJECT_DIR\}/(bin|hooks|linters|skills)", text), (
            f"{rel}: plugin assets must not be addressed via CLAUDE_PROJECT_DIR"
        )
    sync_skill = ROOT / "skills" / "architecture-sync" / "SKILL.md"
    text = sync_skill.read_text(encoding="utf-8")
    assert "CLAUDE_PLUGIN_ROOT" in text
    assert not re.search(r"\$\{CLAUDE_PROJECT_DIR\}/(bin|hooks|linters|skills)", text), (
        "architecture-sync SKILL.md: plugin assets must not be addressed via CLAUDE_PROJECT_DIR"
    )
