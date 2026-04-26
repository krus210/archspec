---
name: architecture-sync
description: Use when the user edits SERVICE_MAP.yaml, asks to "regenerate diagrams", "update mermaid", "service map drift", or runs /archspec:sync. Regenerates docs/diagrams/*.mmd and the managed region of docs/ARCHITECTURE.md.
---

# architecture-sync

Regenerates Mermaid diagrams and `docs/ARCHITECTURE.md` from `docs/SERVICE_MAP.yaml`. Deterministic — same input ⇒ same output bytes.

## When to run

- User edited `docs/SERVICE_MAP.yaml`.
- Pre-commit reported `DET-004` (diagrams out of sync).
- User typed `/archspec:sync`.

## Procedure

1. Verify `docs/SERVICE_MAP.yaml` exists. If not, suggest `/archspec:init` and stop.

2. Validate the YAML against the schema:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/validate_servicemap.py docs/SERVICE_MAP.yaml
   ```

   Exit 0 = continue. Exit 1 = surface the schema error verbatim and stop. Exit 2 = file missing, suggest `/archspec:init`.

3. Run the sync entry point:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/sync.py docs/SERVICE_MAP.yaml docs
   ```

4. Sanity-check the generated `.mmd`:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/validate_mermaid.py docs/diagrams/*.mmd
   ```

5. Stage the regenerated artifacts:

   ```bash
   git add docs/diagrams docs/ARCHITECTURE.md
   ```

6. Print a one-line summary: `archspec sync: <N> diagrams + ARCHITECTURE.md regenerated.`

## Determinism guarantees

- Output bytes depend only on the input YAML — never on `$TZ`, `$LANG`, system clock, or random state.
- LF line endings, UTF-8 no BOM, single trailing newline.
- 20 consecutive runs of the same input produce identical SHA-256 hashes.

## Failure modes

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `validate_servicemap.py` exits 1 | YAML doesn't match the schema | Surface the diagnostic, do **not** silently fix; ask the user |
| Generated `.mmd` differs from staged copy after `git add` | A second editor wrote in parallel | Re-run; warn user about the race |
| `validate_mermaid.py` exits 1 | Template bug — unbalanced subgraph or unknown header | Open an issue against archspec; do not commit |

## Do not

- Edit `docs/diagrams/*.mmd` or the managed region of `docs/ARCHITECTURE.md` by hand. The pre-commit hook (DET-005) will block it.
- Read or set `datetime`/`random`/`uuid` anywhere in this workflow.

## Bootstrap (used by /archspec:init)

Run when the repo has no `docs/SERVICE_MAP.yaml`.

1. Refuse if any of these files already exist *and* contain non-archspec content:
   - `docs/SERVICE_MAP.yaml` — never overwrite.
   - `docs/ARCHITECTURE.md` outside the `<!-- archspec:managed-region:start -->` markers.
   - `CLAUDE.md` outside the `<!-- archspec:claude-block:start -->` markers.

2. Copy the seed:

   ```bash
   mkdir -p docs/adr docs/diagrams .servicemap
   cp ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/templates/SERVICE_MAP.template.yaml docs/SERVICE_MAP.yaml
   cp ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/schema/servicemap.schema.json .servicemap/schema.json
   ```

3. Replace placeholders. Ask the user for: service name, team, language, repo URL, domain. Replace `REPLACE-WITH-DATE` with today's ISO date (asked from the user — do **not** read the system clock).

4. Render diagrams + ARCHITECTURE.md (delegate to the main "Procedure" section, steps 2–5).

5. Append the CLAUDE block:

   ```bash
   if ! grep -q "archspec:claude-block:start" CLAUDE.md 2>/dev/null; then
     cat ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/templates/CLAUDE.archspec-block.md >> CLAUDE.md
   fi
   ```

6. Install the pre-commit hook:

   ```bash
   bash ${CLAUDE_PROJECT_DIR}/hooks/pre-commit/install_hooks.sh
   ```

7. Print:

   ```
   archspec init complete.
     docs/SERVICE_MAP.yaml          (edit this)
     docs/ARCHITECTURE.md           (generated, do not hand-edit the managed region)
     docs/diagrams/{context,container,sequence}.mmd
     .git/hooks/pre-commit          (chained runner)
   Next: edit SERVICE_MAP.yaml, then run /archspec:sync.
   ```

### Re-init idempotency

If `/archspec:init` is invoked again, skip every step that would modify a file with archspec markers. Refresh only the managed regions and the schema copy. Never overwrite user-authored content.
