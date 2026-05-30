---
name: architecture-sync
description: Use when the user edits SERVICE_MAP.yaml, asks to "regenerate diagrams", "update mermaid", "service map drift", or runs /archspec:sync. Regenerates docs/diagrams/*.mmd and the managed region of docs/ARCHITECTURE.md.
---

# architecture-sync

Regenerates Mermaid diagrams and `docs/ARCHITECTURE.md` from `docs/SERVICE_MAP.yaml`. Deterministic — same input ⇒ same output bytes.

## What this skill produces

### Existing service map (`/archspec:sync`)

- Validates `docs/SERVICE_MAP.yaml` against `.servicemap/schema.json`.
- Rewrites `docs/diagrams/context.mmd`, `docs/diagrams/container.mmd`, and `docs/diagrams/sequence.mmd`.
- Rewrites only the managed region of `docs/ARCHITECTURE.md`.
- Stages `docs/diagrams/` and `docs/ARCHITECTURE.md`.
- Ends with `archspec sync: <N> diagrams + ARCHITECTURE.md regenerated.`

### New service (`/archspec:init`)

- Creates `docs/SERVICE_MAP.yaml` from the template.
- Creates `docs/diagrams/{context,container,sequence}.mmd` and `docs/ARCHITECTURE.md`.
- Creates `.servicemap/schema.json` and `docs/adr/`.
- Installs the archspec git hooks.
- Appends the managed archspec block to `CLAUDE.md`.
- Leaves truthful debt markers (`not-documented`, `not-measured`, `not-implemented`) when the scanner or user cannot prove a field.

Reference init output lives in `examples/task-service-init-output/docs/diagrams/`.

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

2a. **Top-level architecture spec ingest (opt-in).** Ask the user via `AskUserQuestion`:

   > "Path to a top-level architecture spec for this monorepo (e.g. `docs/project/architecture.md`, `docs/architecture.md`)? If none — answer `skip` and we'll proceed without cross-checking."

   - **Path provided** — Read the file with the `Read` tool and keep its contents as **conversation context only** (do not parse). Then, before each subsequent confirm prompt, briefly recite what the spec says about *this* service (e.g. "top-level spec lists `matching-service → geo-service` for distance computation; confirm?"). Print one reminder to the user once at the start: "Top-level spec may be stale — if anything contradicts the actual code, answer based on code, not spec." The spec is a hint, never an override.
   - **`skip` / no path** — proceed with no cross-check; per-service init runs as before.

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

   gRPC servers with a matching `proto/<domain>/v1/*.proto` produce one finding **per RPC method** (`name: CreateOrder`, `path: OrderServiceServer/CreateOrder`). Confirm each method individually so idempotency/SLA can be set per-method. When the proto cannot be located, the scanner falls back to a single summary entry — ask the user to enumerate methods manually.

   For each accepted endpoint, ask a follow-up batch (single `AskUserQuestion` call with multiple questions):

   - `idempotency.required` — boolean (`Yes` / `No`). **Propose** a default based on the endpoint name:
     - If the name starts with one of the read prefixes (`Get`, `List`, `Find`, `Read`, `Search`, `Has`, `Is`, `Count`, `Lookup`, `Query`, `Fetch`) → default `No` (idempotency is implicit).
     - Otherwise (writes like `Create*`, `Update*`, `Delete*`, `Send*`, `Verify*`, `Assign*`, `Submit*`, `Process*`, `Schedule*`, `Confirm*`, `Reject*`, `Cancel*`, `Set*`, `Add*`, `Remove*`) → default `Yes`. The shared list lives in `_common.READ_PREFIXES`.
     - On `No` for a write endpoint, just record `required: false` — no nag, no BLOCK.
   - If `required: Yes`: `key_source` (default `"header: X-Idempotency-Key"` for HTTP, `"metadata: x-idempotency-key"` for gRPC); `storage` — **truthful default driven by accepted `dependencies.storage[]` findings**:
     - Redis present → `"redis: idemp:{key}"`.
     - Postgres present → `"postgres: idemp_keys table"`.
     - No durable storage (empty or only `in-memory`) → `"not-implemented"` and remind the user: «Idempotency declared but no durable store wired. Recommend an ADR `docs/adr/<service>-idempotency.md` documenting the gap». Do **not** silently substitute Redis — that ships a YAML lie.
     The user may override with free text (e.g. `"postgres: tx + outbox"`, `"in-memory dedup store"`).
   - `sla.p99_latency` — default `"not-measured"`. Optional alternative: `"100ms"`/`"500ms"` (read/write rough estimates) only when the user explicitly opts in. **Do not blindly fill aspirational numbers** — a `not-measured` marker is more honest than a fictional `99.9%`.
   - `sla.availability` — default `"not-measured"`; same opt-in for `"99.9%"` if user has SLO data.
   - `contract` — derive from the scanner's `contract_hint`:
     - gRPC with proto found → `contract_hint` (e.g. `"proto/geo/v1/geo.proto"`).
     - HTTP with `api/schema.yaml` / `api/openapi.yaml` / `docs/openapi.yaml` / `openapi.yaml` / `openapi/openapi.yaml` found → `contract_hint`.
     - Nothing found → default `"not-documented"` (visible debt) — **not** `"TODO"` (which means «I plan to write it»). Use `"TODO"` only when the user explicitly says «I'll add the schema this week».

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

3b-rev. **Discover upstream consumers** (who calls this service).

   Ask the user in a single `AskUserQuestion`:

   > "Is this service part of a monorepo I can scan to discover upstream consumers? If yes, paste the absolute path to the monorepo root (the directory containing `services/`, `cmd/`, or `apps/`). If no, answer `none` and I'll ask you to list consumers manually."

   - **Path provided** — run the reverse scanner:

     ```bash
     ${CLAUDE_PROJECT_DIR}/bin/archspec-python \
       ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/scan_go.py \
       --reverse-scan <monorepo-root> --target <service.name> > /tmp/archspec-reverse.json
     ```

     Read `/tmp/archspec-reverse.json`. Schema:

     ```
     { repo_root, target, files_scanned,
       consumers: [{name, protocol, endpoints_used: [...], source, confidence,
                    discovered_via: "monorepo-scan"}, ...] }
     ```

     The scanner detects gRPC consumers by matching imports of `<...>/<domain>/v1` and method-request literals like `<alias>.<Method>Request{`. HTTP-only consumers are NOT auto-detected and must be added manually.

     **Apply the findings deterministically — do NOT rely on the LLM to remember to write each entry.** Use the merge script:

     ```bash
     ${CLAUDE_PROJECT_DIR}/bin/archspec-python \
       ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/apply_upstream.py \
       docs/SERVICE_MAP.yaml --reverse-scan-json /tmp/archspec-reverse.json
     ```

     Without `--write`, the script prints a unified diff. Show the diff to the user via one `AskUserQuestion`:

     - `Apply N upstream entries discovered via monorepo-scan?` — options:
       - `Yes — apply all` → re-run with `--write`.
       - `Yes, but edit some` → fall back to the per-consumer confirmation loop below.
       - `Skip — none of these` → no changes.

     The script preserves existing manual entries (those with `discovered_via: manual`), upgrades bare-string `- foo` entries into structured form, and unions `endpoints_used` with scan results.

     For the «edit some» branch (rare): for each consumer, ask `AskUserQuestion` to confirm/skip and edit the YAML by hand.

   - **`none` (not a monorepo, or repo not on disk)** — fall back to a manual `AskUserQuestion`:

     > "Which other services call this one? List them comma-separated, e.g. `api-gateway, matching-service`. If you don't know yet, answer `unknown` and I'll write a TODO."

     For each name, write `{name, discovered_via: "manual"}` to `dependencies.upstream[]`. If the user answered `unknown`, write a single placeholder `{name: "TODO-list-consumers", discovered_via: "k8s-todo"}` so a future iteration can replace it (planned: derive consumers from k8s `Service` + `NetworkPolicy` resources or service-mesh telemetry).

3b-agg. **Confirm detected aggregates** (Go scanner only). After the JSON report is read, iterate over `aggregates` and ask the user one `AskUserQuestion` per finding:

   > "Detected aggregate '<name>' (write_strategy=<optimistic|pessimistic>) at <file:line>. Confirm / rename / skip"

   Write each accepted entry to `concurrency.aggregates[]` as `{name, write_strategy}`. Skip entries are silently dropped. If the scanner found no aggregates **and** any mutating endpoint was confirmed in 3b, ask one trailing question: "What is the main aggregate of this service (free text, or `skip` to leave empty)?". Otherwise (read-only service) leave `aggregates: []`.

3c0. **Decide `consistency.write_path.pattern`** based on findings:

   - "Mutating endpoint" = name does NOT start with `Get`, `List`, `Find`, `Read`, `Search`, `Has`, `Is`, `Count`, `Lookup`, `Query`, or `Fetch`.

   Decision matrix (recommend, then confirm):

   | confirmed `events.published` | confirmed mutating endpoint | confirmed durable storage (postgres/redis/mongo/sql/etc., excludes read-only `in-memory`) | recommend |
   | --- | --- | --- | --- |
   | none | none | any | `direct` (read-only service) |
   | none | yes | none | `direct` (stateless gateway / forwarder — outbox needs durable storage; recommending `outbox` here ships a structural lie) |
   | none | yes | yes | `direct` (writes go straight to DB, no async fan-out) |
   | any | any | yes | `outbox` (durable outbox table backs the publish) |
   | any | any | none | flag as inconsistency: "publishes events but has no durable storage". Confirm with the user: either add storage entry, or change pattern to `direct` knowing events are best-effort. |

   In every non-trivial case, confirm with one `AskUserQuestion`: "Choose the write-path pattern: `outbox` (recommended for services that publish events from a durable store), `direct` (synchronous writes, no event publishing — also correct for stateless gateways), `saga` (multi-step distributed transactions)." Pre-select the recommendation as the first option.

3c. **Write the confirmed findings to `docs/SERVICE_MAP.yaml`** using the `Edit` tool. Build each YAML block from the confirmed answers; do not write rejected items. Schema fields and defaults:

   - `api.endpoints[]`:
     ```yaml
     - name: <user-provided or scanner-derived>
       protocol: HTTP|gRPC
       idempotency:
         required: <bool>
         # if required is true: key_source and storage are required by schema
         key_source: <user-provided>
         storage: <user-provided or "not-implemented">   # see § Truthful state values
       contract: <user-provided or "not-documented">     # use "TODO" only if user said "I'll write the schema"
       sla:
         p99_latency: <user-provided or "not-measured">
         availability: <user-provided or "not-measured">
     ```
   - `dependencies.upstream[]` (structured form, preferred — produced by step 3b-rev):
     ```yaml
     - name: <consumer-service>
       protocol: gRPC|HTTP    # optional, set when known
       endpoints_used:        # optional, set by reverse-scan
         - <method-name>
       discovered_via: monorepo-scan|manual|k8s-todo
     ```
     A bare string entry (`- api-gateway`) is still accepted for backwards compatibility but provides no information for circular-dependency analysis.

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
       contract: <user or "not-documented">
       version: <user or 1>
     ```
   - `events.consumed[]`:
     ```yaml
     - topic: <scanner>
       contract: <user or "not-documented">
       expected_version: <user or 1>
     ```

   After writing, run the validator to confirm the YAML still parses cleanly:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/validate_servicemap.py docs/SERVICE_MAP.yaml
   ```

   Exit 0 = continue. Exit 0 with `WARN DET-006` lines on stderr = TODO placeholders survive in optional fields; that's fine for a draft. Exit 1 = schema error or strict-mode TODO violation — surface the diagnostic and ask the user to amend.

3d. **Cross-service invariants prompt (skippable).** Only when the service has confirmed `events.published`, `events.consumed`, or `consistency.write_path.pattern` in `{outbox, saga}`. Ask one `AskUserQuestion`:

   > "List 1–3 cross-service invariants (one per line), or type `skip` to leave empty. Examples: 'every <event-A> eventually triggers exactly one <event-B> or <event-C>'; 'duplicate <event-A> processing is prevented via CAS on <key>'; 'consumer must be idempotent on <field>'."

   Skip / empty answer → write `cross_service_invariants: []` and print one info line: "left empty — fill in later when invariants stabilise". No retry, no BLOCK. Otherwise split lines and write to `consistency.cross_service_invariants[]`.

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

## Truthful state values

archspec records **what is**, not **what is wished for**. When a field cannot be filled with a real value, prefer one of these explicit markers over inventing one:

| Marker | Meaning | When to use | Diagnostics |
| --- | --- | --- | --- |
| `TODO` | I plan to fill this in soon | Stub on a fresh draft, expected to disappear within a week | DET-006 |
| `not-implemented` | The feature is not in the code at all | `idempotency.storage` when no durable store is wired; published-event `contract` when no schema exists | IDEMP-001, DOC-002 |
| `not-documented` | Implementation exists but the schema/contract is not written | `api.endpoints[].contract` when no proto/openapi found | DOC-001 |
| `not-measured` | Metric not collected | `sla.p99_latency`, `sla.availability` without SLO/observability data | SLA-001 (under `metadata.archspec_strict: true`) |

Rule of thumb: if you would have to guess, write the marker that names the gap. A `TODO` says «I owe a value»; `not-implemented` says «the work owes a feature». Different action items.

The most important diagnostic is **IDEMP-002** — `check_architecture.py` reports it when `idempotency.storage` mentions a technology (e.g. `redis: idemp:{key}`) that does not appear in `dependencies.storage[].type`. This is the YAML-lies signal: declared infrastructure that is not actually wired.

## Check architecture (used by /archspec:check-architecture)

Read-only audit of an entire monorepo. Walks every `**/SERVICE_MAP.yaml` reachable from the repo root and reports cross-spec mismatches.

1. Confirm `repo_root`. Default = current working directory.

2. Run the audit script:

   ```bash
   ${CLAUDE_PROJECT_DIR}/bin/archspec-python \
     ${CLAUDE_PROJECT_DIR}/skills/architecture-sync/scripts/check_architecture.py \
     <repo-root> [--issues-only|--full]
   ```

   Flags:
   - `--issues-only` — silent output when no issues; exit 0.
   - `--full` — include the per-service summary table (downstream / declared upstream / computed upstream / pubs / subs).
   - `--apply-upstream-fixes` — for every DEP-002 finding, run `reverse_scan` against the callee, merge the discovered consumers into the callee's `dependencies.upstream[]`, and **report planned edits as a dry-run** (does NOT touch files). Re-run with `--write` to actually rewrite YAML. Use this two-step flow after a monorepo-wide bootstrap to clear all DEP-002 in one pass: read the dry-run summary, get user confirmation via `AskUserQuestion`, then run with `--write`.

3. Surface the markdown report verbatim. The report flags:
   - **DET-006** — `TODO` literals in required-concrete fields.
   - **DEP-001** — write_path × events inconsistency (outbox without events, or direct with events).
   - **DEP-001b** — `outbox` declared but `dependencies.storage[]` is empty (outbox needs durable storage).
   - **DEP-002** — service A calls B but B does not list A as upstream.
   - **DEP-003** — published topic with no consumer in the monorepo.
   - **DEP-004** — declared upstream not reflected in the claimed caller's spec.
   - **DEP-005** — mutating endpoint has no caller listed in `upstream[].endpoints_used` (orphan write — dead code or undocumented external client). WARN-level: HTTP gateways with external clients legitimately have no monorepo callers.
   - **IDEMP-001** — `idempotency.required=true` with `storage="not-implemented"` (visible debt).
   - **IDEMP-002** — `idempotency.storage` references a technology missing from `dependencies.storage[]` (YAML lies — most common on services that copy `"redis: idemp:{key}"` from defaults without wiring Redis).
   - **DOC-001** — endpoint `contract: not-documented`.
   - **DOC-002** — published event `contract: not-documented` or `not-implemented`.
   - **SLA-001** — SLA field set to `not-measured` while `metadata.archspec_strict: true`.

4. Suggest follow-ups based on the report. Do **not** rewrite any SERVICE_MAP.yaml automatically without user permission — `--apply-upstream-fixes` is the only mutating mode and only fixes DEP-002.
