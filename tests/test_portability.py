"""Portability invariants that keep the skills working across Claude Code, Codex,
opencode, and `npx skills` installs. See PORT_SPEC.md for the rationale."""

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL_MD_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))


def test_skill_frontmatter_parses_as_strict_yaml():
    """Codex, opencode and `npx skills` parse the SKILL.md frontmatter as real YAML.

    A ``: `` (colon-space) inside an unquoted ``description`` silently breaks skill
    discovery on those hosts even though a naive line splitter accepts it — which is
    exactly how ``architecture-investigate`` was invisible to ``npx skills``. Guard
    the whole frontmatter with the same strict parser the real hosts use.
    """
    for skill_md in SKILL_MD_FILES:
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{skill_md}: missing frontmatter block"
        end = text.find("\n---\n", 4)
        assert end != -1, f"{skill_md}: unterminated frontmatter block"
        fm = yaml.safe_load(text[4:end])
        assert isinstance(fm, dict), f"{skill_md}: frontmatter is not a YAML mapping"
        assert fm.get("name") == skill_md.parent.name, (
            f"{skill_md}: frontmatter name must equal the skill directory name"
        )
        assert isinstance(fm.get("description"), str) and fm["description"], (
            f"{skill_md}: description must be a non-empty string — a ': ' in an "
            "unquoted value breaks the strict YAML parsers Codex/opencode/npx skills use"
        )


def test_py_launcher_exists_and_is_executable():
    launcher = ROOT / "skills" / "architecture-sync" / "scripts" / "_py.sh"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)


def test_no_skill_md_uses_the_brittle_plugin_root_resolver():
    brittle = "${CLAUDE_PLUGIN_ROOT:-$CLAUDE_PROJECT_DIR}"
    for skill_md in SKILL_MD_FILES:
        text = skill_md.read_text(encoding="utf-8")
        assert brittle not in text, f"{skill_md} still uses the old resolver"


def test_no_skill_md_references_bin_archspec_python():
    for skill_md in SKILL_MD_FILES:
        text = skill_md.read_text(encoding="utf-8")
        assert "bin/archspec-python" not in text, f"{skill_md} bypasses _py.sh"


def test_no_skill_md_cross_references_sync_scripts_via_archspec_root():
    literal = "$ARCHSPEC_ROOT/skills/architecture-sync/scripts"
    for skill_md in SKILL_MD_FILES:
        text = skill_md.read_text(encoding="utf-8")
        assert literal not in text, f"{skill_md} cross-references sync scripts by path"


def test_every_skill_md_mentions_archspec_skill_dir():
    for skill_md in SKILL_MD_FILES:
        text = skill_md.read_text(encoding="utf-8")
        assert "ARCHSPEC_SKILL_DIR" in text, f"{skill_md} is missing the portable resolver"


def test_claude_block_template_keeps_its_marker():
    template = ROOT / "skills" / "architecture-sync" / "templates" / "CLAUDE.archspec-block.md"
    text = template.read_text(encoding="utf-8")
    assert "archspec:claude-block:start" in text
