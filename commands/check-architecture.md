---
description: Audit a monorepo of SERVICE_MAP.yaml files against each other and (optionally) a top-level architecture spec. Reports graph mismatches, orphan events, TODO leaks, write_path/events inconsistencies. Read-only.
---

# /archspec:check-architecture

Run the `architecture-sync` skill's **Check architecture** procedure to audit
all `**/SERVICE_MAP.yaml` files in the current repository.

Open `skills/architecture-sync/SKILL.md` and follow the **Check architecture
(used by /archspec:check-architecture)** section verbatim.

Read-only: never modifies any file.
