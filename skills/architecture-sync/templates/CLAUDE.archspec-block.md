<!-- archspec:claude-block:start -->

## archspec

This service uses the `archspec` plugin. Architecture is captured in
`docs/SERVICE_MAP.yaml`. Diagrams and `docs/ARCHITECTURE.md` are generated.

When editing code or planning a change:

1. Read `docs/SERVICE_MAP.yaml` first.
2. Run the architecture-investigate skill (Claude Code: `/archspec:investigate`) before non-trivial work.
3. After editing `docs/SERVICE_MAP.yaml`, run the architecture-sync skill (Claude Code: `/archspec:sync`).
4. Before merging, run the architecture-sync skill's validate procedure (Claude Code: `/archspec:validate`) and address every BLOCK.
5. Never hand-edit `docs/diagrams/*.mmd` or the managed region of `docs/ARCHITECTURE.md`.

<!-- archspec:claude-block:end -->
