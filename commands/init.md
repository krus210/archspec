---
description: Bootstrap a service for archspec — auto-discover endpoints/dependencies/storage/topics from Go code, ask the user for SLA/idempotency/timeout fields, then create SERVICE_MAP.yaml, ARCHITECTURE.md, ADR dir, install pre-commit hook, append archspec block to AGENTS.md (canonical cross-tool file) and CLAUDE.md.
---

# /archspec:init

Run the `architecture-sync` skill's **Bootstrap** section.

Expected output:

- `docs/SERVICE_MAP.yaml`
- `docs/diagrams/context.mmd`
- `docs/diagrams/container.mmd`
- `docs/diagrams/sequence.mmd`
- `docs/ARCHITECTURE.md`
- `.servicemap/schema.json`
- `docs/adr/`
- archspec git hooks
- managed archspec block in `AGENTS.md` (canonical) and `CLAUDE.md`

Open `skills/architecture-sync/SKILL.md` and follow "Bootstrap (used by /archspec:init)" verbatim.
