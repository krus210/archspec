---
description: Run the AI audit of code vs SERVICE_MAP.yaml. Monorepo-aware — discovers every service's contract and lints each service. Produces a markdown report of BLOCK/WARN/INFO findings. Read-only.
---

# /archspec:validate

AI-layer audit. Complements the deterministic pre-commit (`hooks/pre-commit/run_all_checks.py`) by checking the contextual rules AI-001..010 from `docs/VALIDATION_RULES.md`.

This command does **not** modify any file. It produces a report.

All plugin assets (scripts, linters) resolve via the skill's own directory, never the
consumer repo:

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

## Procedure

1. **Discover the service maps** — single-service and monorepo layouts both work:

   ```bash
   find . \( -name node_modules -o -name .venv -o -name vendor -o -name .git \) -prune \
     -o -type f -path '*/docs/SERVICE_MAP.yaml' -print | sort | tee /tmp/archspec-maps.txt
   ```

   - **0 results** → suggest `/archspec:init` and stop.
   - **1 result at `./docs/SERVICE_MAP.yaml`** → single-service mode: the loop below has
     one iteration with the service dir = repo root.
   - **multiple results** → monorepo mode: one loop iteration per service, with the
     service dir = the directory containing `docs/` (e.g. `services/task-service`).
     Never assume a root `docs/SERVICE_MAP.yaml` exists in a monorepo — in the typical
     layout it does not.

2. Run the deterministic layer once at the repo root to catch low-cost failures cheaply:

   ```bash
   git diff --name-only --cached --diff-filter=ACMR > /tmp/archspec-changed.txt
   ARCHSPEC_REPO_ROOT="${CLAUDE_PLUGIN_ROOT:-$SKILL_DIR/../..}"
   bash "$SKILL_DIR/scripts/_py.sh" "$ARCHSPEC_REPO_ROOT/hooks/pre-commit/run_all_checks.py" || true
   ```

   Surface every BLOCK at the top of the report.

3. **Per-service linter loop.** For each discovered `SERVICE_MAP.yaml`, identify the
   language and run every linter that language's dispatcher advertises, passing the
   service's own contract and code directory:

   ```bash
   for MAP in $(cat /tmp/archspec-maps.txt); do
     SVC_DIR=$(dirname "$(dirname "$MAP")")
     lang=$(bash "$SKILL_DIR/scripts/_py.sh" -c "import yaml; print(yaml.safe_load(open('$MAP'))['service']['language'])")
     LINTER="$ARCHSPEC_REPO_ROOT/linters/$lang/lint.sh"
     if [[ ! -x "$LINTER" ]]; then
       echo "INFO: no linters available for language=$lang ($SVC_DIR)"
       continue
     fi
     for sub in $("$LINTER" --list); do
       "$LINTER" "$sub" --service-map "$MAP" --code "$SVC_DIR"
     done > "/tmp/archspec-findings-$(basename "$SVC_DIR").json"
   done
   ```

   The dispatcher contract is unchanged:

   - `lint.sh --list` — print supported subcommand names, one per line, exit 0.
   - `lint.sh <subcommand> --service-map PATH --code DIR` — run that linter and
     emit findings as a JSON array on stdout (spec §4.5 shape).

   Each finding has shape `{rule, severity, file, line, contract_ref, message, suggested_fix}`.

4. **Suppression resolution**. Filter findings against `exceptions[]` in the owning
   service's `SERVICE_MAP.yaml` (matching `rule` and `scope`) and inline
   `archspec:ignore` pragmas in the cited file/line. Keep suppressed findings in a
   `Suppressed` section of the report.

5. **Format the report** following spec §6.3 — in monorepo mode grouped **per service**,
   with one combined summary line at the end:

   ```markdown
   ## archspec validate — N BLOCK, N WARN, N INFO, N SUPPRESSED (across M services)

   ### services/task-service — N BLOCK, N WARN
   #### BLOCK · AI-XXX · <category>
   **Where**: <file>:<line>
   **Contract**: services/task-service/docs/SERVICE_MAP.yaml:<line> — <field path>
   **Issue**: <message>
   **Fix**: <suggested_fix>

   ### Suppressed (N)
   - AI-XXX at <file>:<line> — exception in <service>/docs/SERVICE_MAP.yaml:<line> (expires YYYY-MM-DD)
   - …

   ### ⚠ <N> exception(s) expire within 30 days
   - AI-XXX expires YYYY-MM-DD (<N> days from today). Plan replacement.
   ```

   For the "expires within 30 days" section, ask the user for today's date — do not read the system clock.

6. **Exit semantics**:
   - Any BLOCK in any service → tell the user the PR is not mergeable.
   - WARN-only → mergeable, but list each WARN.
   - INFO-only → mergeable.
   - All findings suppressed → mergeable; explicitly list suppressions so reviewers see them.

7. End with one-line summary: `archspec validate: N BLOCK, N WARN, N INFO, N suppressed across M services.`

## Do not dismiss findings

- A passing `go build` / `go test` does **not** clear a linter or LSP finding. The tests were usually written alongside the code under review and cover the same happy path, so green tests prove nothing about declared invariants (idempotency, outbox, ownership).
- Resolve each finding, or record an explicit `exceptions[]` entry in the owning service's `docs/SERVICE_MAP.yaml` (or an inline `archspec:ignore` pragma) with a reason. Never wave a finding away as "stale" without re-running the linter to confirm.

## Reference

See `skills/architecture-sync/SKILL.md` for severity definitions and the determinism contract that backs the deterministic prefix of this report.
