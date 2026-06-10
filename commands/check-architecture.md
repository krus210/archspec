---
description: Audit a monorepo of SERVICE_MAP.yaml files against each other and (optionally) a top-level architecture spec. Reports graph mismatches, orphan events, TODO leaks, write_path/events inconsistencies. Read-only.
---

# /archspec:check-architecture

Run the `architecture-sync` skill's **Check architecture** procedure to audit
all `**/SERVICE_MAP.yaml` files in the current repository.

Open `skills/architecture-sync/SKILL.md` and follow the **Check architecture
(used by /archspec:check-architecture)** section verbatim.

Resolve plugin assets via `ARCHSPEC_ROOT="${CLAUDE_PLUGIN_ROOT:-$CLAUDE_PROJECT_DIR}"` —
when archspec runs as an installed plugin, the consumer repo has no `skills/` or `bin/`.
Run it from the **monorepo root**: the audit itself walks every `**/SERVICE_MAP.yaml`.

Read-only: never modifies any file.
