---
description: Implement a change from an .archplan.md artifact — apply contract edits, sync docs, write a conformant coding plan, implement with TDD, then prove plan↔code conformance with validate/check-architecture. Commits, never pushes.
---

# /archspec:implement

Run the `architecture-implement` skill.

Open `skills/architecture-implement/SKILL.md` and follow the phases verbatim.

Argument: path to the `docs/plans/<date>-<slug>.archplan.md` artifact produced by
`/archspec:investigate`. Without one, the skill refuses and points to
`/archspec:investigate` first.
