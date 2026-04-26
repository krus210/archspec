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

3. Replace placeholders. Ask the user via `AskUserQuestion` (single batch) for: service name, team, language, repo URL, domain, primary owner handle (e.g. `@alice`), oncall handle. Replace `REPLACE-WITH-DATE` with today's ISO date (asked from the user — do **not** read the system clock).

3a0. **Service-level questionnaire** — fill `service.responsibilities` and `service.invariants` BEFORE running the auto-discovery scanner. These are the two most important free-form fields in the contract; leaving them as `TODO` makes the generated `ARCHITECTURE.md` near-useless.

   Use `AskUserQuestion` with two free-text questions, both required:

   - `responsibilities` — "List 3–5 things this service is responsible for, one per line. Each line should start with a verb (e.g. 'serve geo lookup queries', 'cache postal-code data')."
   - `invariants` — "List 1–5 invariants this service must uphold, one per line. Examples: 'every write goes through the outbox', 'all endpoints are idempotent', 'no PII leaves this service'."

   Split each answer on newlines and write the resulting list into the YAML. If the user explicitly says "skip" or returns empty input, leave the existing `TODO` placeholder and tell them: "I left these as TODO — please fill them in before running `/archspec:sync`."

   Also ask in the same batch (or a follow-up if the AskUserQuestion plugin caps at N questions): `bounded_aggregate` (default = service name), and the `consistency.model` (`eventual` or `strong`, default `eventual`).

3a. **Auto-discover from code** (Go services only — skip if `service.language != go`).

   Run the scanner against the service directory (the directory that contains `main.go` or `go.mod`):

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/scan_go.py . > /tmp/archspec-scan.json
   ```

   Read `/tmp/archspec-scan.json`. The schema is:

   ```
   { service_dir, files_scanned,
     endpoints:        [{kind, protocol, method, path|name, source, confidence, contract_hint?}, ...],
     downstream_sync:  [{kind, protocol, service, address_arg, source, confidence}, ...],
     storage:          [{kind, type, source, confidence}, ...],
     events_published: [{kind, backend, topic, source, confidence}, ...],
     events_consumed:  [{kind, backend, topic, source, confidence}, ...] }
   ```

   `contract_hint` is set on gRPC endpoints when the scanner finds a matching `proto/<domain>/v1/*.proto` file in the service directory or any parent up to 5 levels — use it as the default `contract` value in the questionnaire.

   `backend` is `"kafka"` or `"nats"` today. Other messaging stacks (RabbitMQ, GCP Pub/Sub, etc.) yield no events — fall back to asking the user explicitly in step 3b.

   If `files_scanned == 0` or every category is empty, tell the user "scanner found no Go artefacts — falling back to manual questionnaire" and skip to step 3b with no findings to confirm.

3b. **Interactive questionnaire** — confirm findings and fill in fields the scanner cannot supply.

   For each `endpoint` finding, use `AskUserQuestion` (one batch per category for fewer round-trips):

   ```
   Question: "Confirm endpoint <METHOD> <path> (found in <source>, confidence <X>)?"
   Options:
     - "Yes — record it"
     - "Yes, but rename"
     - "Skip — false positive"
   ```

   For each accepted endpoint, ask a follow-up batch (single `AskUserQuestion` call with multiple questions):

   - `idempotency.required` — boolean (`Yes` / `No`).
   - If `required: true`: `key_source` (free text, default `"header: X-Idempotency-Key"`), `storage` (default `"redis: idemp:{key}"`).
   - `sla.p99_latency` (default `"100ms"` for in-memory reads, `"500ms"` otherwise — propose, don't blindly fill).
   - `sla.availability` (default `"99.9%"` — propose).
   - `contract` (free text). If the scan finding includes `contract_hint`, **propose that path as the default** — e.g. for a gRPC server `RegisterGeoServiceServer` in a monorepo with `proto/geo/v1/geo.proto`, the scanner returns `contract_hint: "proto/geo/v1/geo.proto"`. Otherwise default to `"TODO"`.

   For each `downstream_sync` finding, ask in one `AskUserQuestion` batch:

   - Confirm/skip.
   - `timeout` (default `"TODO"`).
   - `retries` (integer, default `0`).
   - `fallback` (default `"none"`).
   - `on_failure` (one of: `propagate`, `fail-open`, `fail-closed`, default `propagate`).

   For each `storage` finding, ask:

   - Confirm/skip.
   - `name` (free text — e.g. `tasks-db`; required by schema).
   - `owned_by` (default `"this service"`).

   For each `events_published` and `events_consumed` finding, ask:

   - Confirm/skip.
   - `contract` (default `"TODO"`).
   - For published: `version` (integer, default `1`).
   - For consumed: `expected_version` (integer, default `1`).

   The `backend` field on each finding is informational only — the schema does not store it. Use it when phrasing the confirmation question (e.g. "Confirm NATS subject `task.created` (publish, found in usecase/task.go:53)?") so the user knows which transport the topic belongs to.

   After all categories, ask one trailing `AskUserQuestion` — and explicitly mention messaging because the scanner only knows Kafka and NATS:

   > "Are there architectural artefacts the scanner missed? In particular: (a) additional storage, (b) undetected endpoints, (c) async events using a backend other than Kafka or NATS (e.g. RabbitMQ, Pub/Sub, in-house queue), (d) events that use runtime-resolved subjects the scanner cannot follow."

   If yes, prompt the user to enumerate them and add each manually with the same field set as above.

3c0. **Decide `consistency.write_path.pattern`** based on findings (read-only-service heuristic):

   - If the user accepted **zero** `events_published`, accepted **zero** mutating endpoints, and the only confirmed storage entries are read-only (e.g. `in-memory`, replicated cache), default `consistency.write_path.pattern` to `direct` (the service is read-only — outbox is meaningless).
   - "Mutating endpoint" = name does NOT start with `Get`, `List`, `Find`, `Read`, `Search`, `Has`, `Is`, `Count`, `Lookup`, `Query`, or `Fetch`.
   - Otherwise (any mutating endpoint OR any published event), keep the seed default `outbox` BUT confirm with the user via a single `AskUserQuestion`: "Choose the write-path pattern: `outbox` (recommended for services that publish events), `direct` (synchronous writes, no event publishing), `saga` (multi-step distributed transactions)."

3c. **Write the confirmed findings to `docs/SERVICE_MAP.yaml`** using the `Edit` tool. Build each YAML block from the confirmed answers; do not write rejected items. Schema fields and defaults:

   - `api.endpoints[]`:
     ```yaml
     - name: <user-provided or scanner-derived>
       protocol: HTTP|gRPC
       idempotency:
         required: <bool>
         # if required is true: key_source and storage are required by schema
         key_source: <user-provided>
         storage: <user-provided>
       contract: <user-provided or "TODO">
       sla:
         p99_latency: <user-provided or "TODO">
         availability: <user-provided or "TODO">
     ```
   - `dependencies.downstream.sync[]`:
     ```yaml
     - service: <scanner-derived>
       timeout: <user or "TODO">
       retries: <user or 0>
       fallback: <user or "none">
       on_failure: <user or "propagate">
     ```
   - `dependencies.storage[]`:
     ```yaml
     - type: <scanner-derived: postgres|redis|mongodb|sql|in-memory>
       name: <user-provided>
       owned_by: <user or "this service">
     ```
   - `events.published[]`:
     ```yaml
     - topic: <scanner>
       contract: <user or "TODO">
       version: <user or 1>
     ```
   - `events.consumed[]`:
     ```yaml
     - topic: <scanner>
       contract: <user or "TODO">
       expected_version: <user or 1>
     ```

   After writing, run the validator to confirm the YAML still parses cleanly:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/validate_servicemap.py docs/SERVICE_MAP.yaml
   ```

   Exit 0 = continue to step 4. Non-zero = surface the diagnostic and ask the user to amend.

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
