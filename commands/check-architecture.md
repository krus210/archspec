---
description: Audit a monorepo of SERVICE_MAP.yaml files against each other and (optionally) a top-level architecture spec. Reports graph mismatches, orphan events, TODO leaks, write_path/events inconsistencies. Read-only.
---

# /archspec:check-architecture

Run the `architecture-sync` skill's **Check architecture** procedure to audit
all `**/SERVICE_MAP.yaml` files in the current repository.

Open `skills/architecture-sync/SKILL.md` and follow the **Check architecture
(used by /archspec:check-architecture)** section verbatim.

Resolve the skill's bundled assets relative to its own directory:

```bash
# archspec resolves its bundled assets relative to THIS skill's own directory, so it
# works as a Claude Code plugin, a Codex/opencode skill, or an `npx skills` install.
# Claude Code sets CLAUDE_PLUGIN_ROOT; under Codex/opencode/npx-skills your host tells
# you this skill's absolute path — export ARCHSPEC_SKILL_DIR to it once per session.
SKILL_DIR="${ARCHSPEC_SKILL_DIR:-${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/architecture-sync}}"
: "${SKILL_DIR:?set ARCHSPEC_SKILL_DIR to this skill's own directory (its absolute path)}"
```

Call bundled python scripts through the launcher:

```bash
bash "$SKILL_DIR/scripts/_py.sh" "$SKILL_DIR/scripts/<name>.py" <args...>
```

Run it from the **monorepo root**: the audit itself walks every `**/SERVICE_MAP.yaml`.

Read-only: never modifies any file.
