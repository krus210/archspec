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


def test_investigate_has_clarify_gate():
    """investigate must force clarifying questions on ambiguous requirements.

    Regression guard for the failure mode where the skill jumped straight to
    proposing YAML edits without interrogating ownership / idempotency / limits.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "clarif" in text or "ambiguit" in text, "investigate must have a clarify/ambiguity gate"
    assert "askuserquestion" in text, "the clarify gate should use AskUserQuestion to ask the user"
    for dimension in ("ownership", "idempotency", "write-path"):
        assert dimension in text, f"clarify checklist should cover the '{dimension}' dimension"


def test_investigate_covers_async_ordering_and_fanout():
    """investigate must interrogate async/causal ordering and trace every

    changed event/key across all consumers. Regression guard for the failure
    modes where the skill modeled only the prompt's happy path and missed: a
    trigger that races an async write, a dedup key fixed in only one consumer,
    and a dead-end branch with no terminal state.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "ordering" in text, "clarify checklist should cover async state & event ordering"
    assert "producers" in text and "consumers" in text, (
        "investigate should trace every changed event/key across all producers and consumers"
    )
    assert "dead-end" in text, "investigate should force a terminal path for every dead-end branch"


def test_investigate_has_self_review_loop():
    """investigate must re-run its checklist against its own drafted design, not

    just the prompt. Regression guard for architectural details that survive the
    clarify gate but live in the proposal itself (one event serving two semantic
    purposes, a silently degrading fallback, an async race).
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "self-review" in text, "investigate should run a self-review loop on its own draft"
    assert "anti-pattern" in text, "the self-review loop should hunt named anti-patterns"


def test_investigate_points_to_validation_gate():
    """investigate must wire the post-implementation validation gate into its
    closing next step so the behavioural linters actually run."""
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "/archspec:validate" in text, (
        "investigate should point to /archspec:validate after implementing"
    )
    assert "/archspec:check-architecture" in text, (
        "investigate should point to /archspec:check-architecture for cross-service changes"
    )
