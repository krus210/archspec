---
description: Run the AI audit of code vs SERVICE_MAP.yaml. Produces a markdown report of BLOCK/WARN/INFO findings. Read-only.
---

# /archspec:validate

AI-layer audit. Complements the deterministic pre-commit (`hooks/pre-commit/run_all_checks.py`) by checking the contextual rules AI-001..010 from `docs/VALIDATION_RULES.md`.

This command does **not** modify any file. It produces a report.

## Procedure

1. Verify `docs/SERVICE_MAP.yaml` exists. If not, suggest `/archspec:init` and stop.

2. Run the deterministic layer first to catch low-cost failures cheaply:

   ```bash
   git diff --name-only --cached --diff-filter=ACMR > /tmp/archspec-changed.txt
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/hooks/pre-commit/run_all_checks.py || true
   ```

   Surface every BLOCK at the top of the report.

3. Identify the linter set for the service language:

   ```bash
   lang=$(${CLAUDE_PROJECT_DIR}/bin/archspec-python -c "import yaml,sys; print(yaml.safe_load(open('docs/SERVICE_MAP.yaml'))['service']['language'])")
   echo "language: $lang"
   ```

   Each language ships its linters behind a single dispatcher script at
   `${CLAUDE_PROJECT_DIR}/linters/<lang>/lint.sh`. The dispatcher contract is:

   - `lint.sh --list` — print supported subcommand names, one per line, exit 0.
   - `lint.sh <subcommand> --service-map PATH --code DIR` — run that linter and
     emit findings as a JSON array on stdout (spec §4.5 shape).

4. Run every linter advertised by the dispatcher, with the JSON contract from spec §4.5:

   ```bash
   LINTER="${CLAUDE_PROJECT_DIR}/linters/$lang/lint.sh"
   if [[ ! -x "$LINTER" ]]; then
     echo "INFO: no linters available for language=$lang"
   else
     for sub in $("$LINTER" --list); do
       "$LINTER" "$sub" --service-map docs/SERVICE_MAP.yaml --code .
     done > /tmp/archspec-findings.json
   fi
   ```

   Each finding has shape `{rule, severity, file, line, contract_ref, message, suggested_fix}`.

5. **Suppression resolution**. Filter findings against `exceptions[]` in `docs/SERVICE_MAP.yaml` (matching `rule` and `scope`) and inline `archspec:ignore` pragmas in the cited file/line. Keep suppressed findings in a `Suppressed` section of the report.

6. **Format the report** following spec §6.3:

   ```markdown
   ## archspec validate — N BLOCK, N WARN, N INFO, N SUPPRESSED

   ### BLOCK · AI-XXX · <category>
   **Where**: <file>:<line>
   **Contract**: SERVICE_MAP.yaml:<line> — <field path>
   **Issue**: <message>
   **Fix**: <suggested_fix>

   ### Suppressed (N)
   - AI-XXX at <file>:<line> — exception in SERVICE_MAP.yaml:<line> (expires YYYY-MM-DD)
   - …

   ### ⚠ <N> exception(s) expire within 30 days
   - AI-XXX expires YYYY-MM-DD (<N> days from today). Plan replacement.
   ```

   For the "expires within 30 days" section, ask the user for today's date — do not read the system clock.

7. **Exit semantics**:
   - Any BLOCK → tell the user the PR is not mergeable.
   - WARN-only → mergeable, but list each WARN.
   - INFO-only → mergeable.
   - All findings suppressed → mergeable; explicitly list suppressions so reviewers see them.

8. End with one-line summary: `archspec validate: N BLOCK, N WARN, N INFO, N suppressed.`

## Do not dismiss findings

- A passing `go build` / `go test` does **not** clear a linter or LSP finding. The tests were usually written alongside the code under review and cover the same happy path, so green tests prove nothing about declared invariants (idempotency, outbox, ownership).
- Resolve each finding, or record an explicit `exceptions[]` entry in `docs/SERVICE_MAP.yaml` (or an inline `archspec:ignore` pragma) with a reason. Never wave a finding away as "stale" without re-running the linter to confirm.

## Reference

See `skills/architecture-sync/SKILL.md` for severity definitions and the determinism contract that backs the deterministic prefix of this report.
