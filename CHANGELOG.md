# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] - 2026-06-01

Closes a class of failure observed end-to-end: investigate designed a cross-service
state transition (offer rejection) but never selected the **system-of-record** service
that owns the state — an orchestrator (`matching-service`) absorbed a transition owned
by `task-service` via a synchronous RPC, bypassing its outbox and its reassignment
counter. Theme: **make ownership a forced, reviewable decision, and ship the behavioural
linters that catch the code-side residue.**

### Added
- **State-ownership (system-of-record) lens in `architecture-investigate`.** A new
  clarify dimension forces enumerating every piece of persistent state the change
  touches and naming its system-of-record service; the write must originate in that
  service's own write path, never a sync RPC reaching into a foreign aggregate. A new
  forcing **State-ownership map** artifact (step 8b) makes the decision visible the way
  the fan-out trace makes event subscribers visible. A foreign-aggregate sync mutation
  is a named deviation, and ownership findings are first-class `edge_cases[]` entries.
- **Topology preference: owner-applies-async-command over foreign-aggregate sync RPC**,
  surfaced both in the clarify gate and the self-review loop.
- **Self-review anti-patterns:** foreign-state mutation via a sync RPC; idempotency
  asserted but not traced under replay; N+1 where a batch endpoint exists.
- **AI-007 `swallowed-errors` (WARN)** — flags a downstream call whose return is
  discarded via blank `_` (`_ = svc.Call(...)` or `resp, _ := svc.Call(...)`) when
  `on_failure` is declared. WARN, not BLOCK: AST-only, cannot prove the receiver is
  the declared downstream client.
- **AI-008 `redundant-call` (WARN)** — flags a singular method called inside a loop
  when a `*Batch` sibling exists in code (the `GetDistance`/`GetDistancesBatch` N+1). Pure
  code-pattern heuristic — not tied to declared downstream.
- **AI-009 `undeclared-event` (WARN, v1 = NATS topics)** — flags NATS Publish/Subscribe to
  a topic (literal or package-level const) absent from `events.published`/`events.consumed`.
  WARN, not BLOCK: AST-only (method-name + subject-shape), no receiver-type proof.

### Changed
- `ServiceMap` (Go linters) now parses `dependencies.downstream.sync[]` and
  `events.{published,consumed}[]`.
- AI-008 severity raised from the reserved `INFO` to `WARN` (conservative matcher).

## [0.9.0] - 2026-05-31

Hardens `architecture-investigate` against a class of failures observed end-to-end:
the skill already *found* several cross-service bugs (a `city_id` vs free-text join
key that "silently collapses the distance tie-breaker", a missing dedup key) — but
the findings died as chat prose and the implementation shipped them anyway, and the
post-implementation validation loop was never run. The theme of this release is
**carry every finding into code, and don't call it done on a green build.**

### Added
- **Risk → `edge_cases[]` bridge (`architecture-investigate` step 8a).** Every gap,
  deviation, `# UNCONFIRMED`, and join-key risk the skill surfaces must now be
  restated as a concrete `edge_cases[]` entry inside the YAML patch (`id` +
  given/when/then `description` + a `test:` path). This is the bridge that carries a
  finding into code: an `edge_cases[]` entry **persists in the contract**, renders
  into `ARCHITECTURE.md` (so the plan-writer and implementation subagents see it
  without the chat), is **enforced by DET-003** (the commit is blocked until the
  `test:` file exists), and is protected by DET-007 (no silent removal without an
  ADR). Closes the failure mode where a verbatim finding ("join on `city_id`, not
  `city_name`") never reached the code.
- **Reference / golden architecture spec ingest (step 2a).** investigate now offers
  to read a reference spec (design doc, RFC, target-state diagram, naming
  convention) and cross-checks the proposed event names, RPC names, dedup keys, and
  invariants against it — naming a divergence rather than silently inventing
  `task.offer_rejected` for a canonical `offer.declined`, or dropping an
  out-of-prompt invariant like "reassignment reuses the initial match snapshot". The
  spec is a hint, never an override: code reality wins on conflict.
- **Definition-of-done checklist (step 10).** investigate now closes with a literal
  checklist — every `edge_cases[]` entry has a real test, `/archspec:validate` is
  green, `/archspec:check-architecture` is green for cross-service work, every
  `# UNCONFIRMED` is resolved — and states that a green `go build` / `go test`
  clears **none** of these boxes. Closes the failure mode where the run ended on
  green unit tests in a separate `finishing-a-development-branch` pass and the
  archspec validation loop was never invoked.
- **Six new self-review anti-patterns (step 9).** The loop now also hunts, in the
  skill's *own* draft: recompute-instead-of-reuse in a retry loop (a snapshot that
  should be reused, not recomputed every attempt); attempt/version identity
  reconstructed from consumer memory instead of carried in the event payload; two
  events from one handler appended outside a single outbox transaction; a terminal
  notification fired despite a failed/swallowed state transition; a terminal guard
  narrower than the entity's real input states; and a finding still sitting in prose
  with no `edge_cases[]` entry.

### Changed
- **`Trusted identity & actor` is now a first-class clarify dimension**, split out of
  `Entry point & ownership`, with an explicit rule that **every sub-question inside a
  dimension is its own checkbox**. Closes the failure mode where the model answered
  the entry-point half ("enters via api-gateway") and silently skipped "where does
  `worker_id` come from?", leaving client-supplied identity trusted.
- **`architecture-investigate` output contract** gains three sections: *Reference
  cross-check*, *Risk register (`edge_cases`)*, and *Definition of done*.

### Notes / known backlog
- The deeper safety net for two of these bugs is a **behavioural linter**, not just a
  skill prompt: `AI-008` (redundant-call / re-analysing the same input across retries)
  and a new **join-key-consistency** linter (catching `city_name` passed where a
  `city_id` is expected) would catch the `city_id` and recompute regressions
  automatically in code. Both remain specified-but-unimplemented (`AI-008` in
  `docs/VALIDATION_RULES.md`); this release strengthens the skill-level guards and the
  `edge_cases[]` bridge that forces a test, and leaves the Go linters as tracked work.

## [0.8.0] - 2026-05-31

### Added
- **Async-state & event-ordering dimension in the `architecture-investigate` clarify
  gate.** The checklist now forces the question: does the trigger read or mutate state
  that a *different* async path writes, and can the two reorder (trigger before the
  write lands; a stale/replayed event after the trigger)? Closes the failure mode where
  a reject path depends on `assigned_worker` set by a separate `match.found` consumer
  and silently no-ops or resurrects cleared state.
- **Event/key fan-out trace (step 7).** For every new or changed event and every
  changed dedup/idempotency/join key, the skill now scans the *full* `SERVICE_MAP.yaml`
  set (not just the slice from step 2) for `events.published` / `events.consumed` / topic
  names / dedup keys, enumerating *all* producers and consumers — catching a dedup key
  fixed in one consumer but left stale in another, and dead-end branches that log-and-return
  without a terminal state. Undetermined fan-out is marked `# UNCONFIRMED` rather than
  assumed complete. A single event carrying **two semantic roles** (matching trigger *and*
  premature client notification) is now **prohibited**: the skill must split it into
  separate events or block the YAML patch with an open question.
- **Self-review loop (step 9).** After drafting the diagram and YAML, the skill re-runs
  the checklist plus a named anti-pattern list against *its own proposal* (not just the
  prompt), looping until a clean pass and emitting a note in the fixed shape
  `Self-review: <N> pass(es), <findings or "no findings">`.

### Changed
- `architecture-investigate` clarify checklist sharpened: the **Entry point & ownership**
  dimension now requires wiring the full reference flow (client → public edge → owner)
  for external triggers and never trusting a client-supplied identity; **Identity & join
  keys** now asks what happens when a lookup fails to resolve and whether that failure is
  silent; **Failure & terminal paths** now demands a terminal for *every* dead-end branch,
  not just the happy-path failure.

## [0.7.1] - 2026-05-30

### Added
- **Clear output contracts for skills and commands.** README now spells out what each
  `/archspec:*` flow produces, and both autopilot skills document their expected
  end state so users can see the concrete artifacts before running them.
- **Reference init-output diagrams.** Added `examples/task-service-init-output/`
  with real `context.mmd`, `container.mmd`, and `sequence.mmd` output from a
  `task-service` bootstrap. README embeds the sequence diagram as a quick preview
  of the Mermaid produced by `/archspec:init`.

## [0.7.0] - 2026-05-30

### Added
- **Clarify-ambiguities gate in `architecture-investigate`**: before proposing any
  YAML edits, the skill now walks a fixed checklist of cross-service ambiguity
  dimensions (entry point & ownership, delivery semantics & idempotency, numeric
  limits/boundaries, identity & join keys, failure/terminal paths, write-path
  conformance) and asks the user via `AskUserQuestion` for every dimension the
  prompt and the contract do not already settle. Closes the failure mode where the
  skill jumped straight to a change plan and silently baked guessed answers
  (ownership boundary, dedup key, off-by-one limit) into the contract.
- **Deviation guard in `architecture-investigate`**: proposed edits that change who
  owns an action, sidestep `consistency.write_path.pattern`, or relax a declared
  invariant must be flagged and explicitly confirmed — a generated contract line no
  longer silently ratifies an unaffirmed design.

### Changed
- `architecture-investigate` now ends with the **full loop** (sync → implement →
  `/archspec:validate` → `/archspec:check-architecture`) instead of stopping at
  `/archspec:sync`, so the behavioural linters (outbox, idempotency,
  optimistic-locking) are actually invoked after implementation.
- `/archspec:validate` gains a **"Do not dismiss findings"** note: a passing
  `go build`/`go test` does not clear a linter or LSP finding; resolve it or record
  an explicit exception with a reason.

## [0.6.0] - 2026-05-02

### Added
- **`apply_upstream.py`** — deterministic merge of reverse-scan consumers into `dependencies.upstream[]`. Replaces the LLM-driven loop where each consumer had to be Edit'd by hand (which an init-time agent skipped on 7/12 freelance-marketplace services). Preserves manual provenance, upgrades bare-string entries, unions `endpoints_used`. Surgical text edit — does not reformat unrelated YAML.
- **`check_architecture.py --apply-upstream-fixes`** — one-pass auto-fix mode that runs `reverse_scan` for every DEP-002 finding and reports planned edits. **Dry-run by default** — pass `--write` to actually mutate YAML files. Two-step flow: review summary, confirm, then commit.
- **gRPC RPC method enumeration in `scan_go.py`** — when a `proto/<domain>/v1/*.proto` is found alongside `Register<X>Server`, the scanner now emits one endpoint finding **per RPC method** (`name: CreateOrder`, `path: OrderServiceServer/CreateOrder`) instead of a single summary entry. RPC enumeration is scoped to the matching `service <X> { ... }` block so multi-service proto files don't bleed admin/public RPCs into each other. When a server's domain-derived proto path doesn't exist (e.g. `BillingAdminServiceServer` → `proto/billing-admin/v1/*` not found), the scanner probes protos already located for siblings in the same Go file — so admin/public service splits sharing one `.proto` package still enumerate cleanly. Falls back to the old single-entry behaviour when no proto matches at all. Reproduces fix for freelance-marketplace findings #6 (config-service, worker-profile, portfolio-service had their RPC methods undercounted).
- **NATS dynamic-subject + outbox-wrapper detection.** `nc.Publish(<dynamic-arg>, ...)` produces a low-confidence `topic: "<dynamic>"` finding when the call site has no resolved alternative. Methods like `func (o *Outbox) PublishMatchFound(...)` trigger an outbox-wrapper heuristic — the scanner reads the body for either an inline topic literal (medium confidence) or a NATS publish call (low confidence, topic guessed from the method name in dotted form, e.g. `MatchFound` → `match.found`). `_scan_events` collapses duplicates by `(backend, topic)` retaining the highest-confidence record, and suppresses `<dynamic>` markers **only when their source line falls inside a wrapper body** — independent dynamic publishes alongside literal ones (different call sites) survive collapse, since nothing else explains them.
- **HTTP openapi auto-discovery.** `_find_openapi_contract` searches `api/schema.yaml`, `api/openapi.yaml`, `docs/openapi.yaml`, `openapi.yaml`, `openapi/openapi.yaml` within the service directory and attaches the path as `contract_hint` on each HTTP-endpoint finding. Default for unfound HTTP contracts becomes `not-documented`, not `TODO`.
- **DEP-001b — outbox without storage.** `consistency.write_path.pattern: outbox` with empty `dependencies.storage[]` is now flagged. Reproduces the freelance-marketplace `api-gateway` case (HTTP→gRPC translator marked outbox by the old heuristic).
- **DEP-005 — orphan write endpoint.** Mutating endpoint not listed in any `upstream[].endpoints_used` is reported as orphan (dead code or undocumented external client). WARN-level — gateway services with external traffic legitimately have no monorepo callers. `is_read_endpoint` recognises both gRPC camelCase (`Get*`, `List*`) and HTTP-verb-prefixed names (`GET /...`, `HEAD /...`, `OPTIONS /...`) so HTTP gateways don't false-positive on every endpoint.
- **IDEMP-001 / IDEMP-002 — idempotency truthfulness.** IDEMP-001 flags `idempotency.required: true` with `storage: not-implemented` (visible debt). IDEMP-002 flags `storage: "redis: idemp:{key}"` when no Redis entry exists in `dependencies.storage[].type` — i.e. archspec catches the YAML lying about infrastructure.
- **DOC-001 / DOC-002 — contract-documentation gaps.** Endpoint `contract: not-documented` and published-event `contract` ∈ `{not-documented, not-implemented}` are surfaced as visible debt.
- **SLA-001 — `not-measured` SLA fields under strict mode.** When `metadata.archspec_strict: true`, SLA fields set to `not-measured` are reported (default `archspec_strict: false` keeps the noise off existing repos).
- **Truthful state vocabulary.** New SKILL.md section documents `TODO`, `not-implemented`, `not-documented`, `not-measured` and when to use each. The bootstrap procedure now uses these markers as defaults instead of inventing infrastructure: idempotency-storage proposes `not-implemented` when no durable store is wired (was: silently substitute Redis); HTTP contract proposes `not-documented` when no openapi.yaml is found (was: `TODO`); SLA fields propose `not-measured` (was: `99.9%` / `100ms`).

### Changed
- **Seed `consistency.write_path.pattern`** in the SERVICE_MAP template is now `direct`, not `outbox`. Outbox is now earned via storage + events evidence (see step 3c0 decision matrix) — a stateless gateway no longer falls into outbox by default.
- **Bootstrap step 3b-rev** rewrites upstream entries via `apply_upstream.py` instead of asking the LLM to call `Edit` for each consumer. One `AskUserQuestion` (apply-all / edit-some / skip) replaces the per-consumer loop.
- **Bootstrap step 3c0** uses an explicit decision matrix (events × mutating endpoint × durable storage) that recommends `direct` for stateless gateways and `outbox` only when both events and storage are confirmed.

### Compatibility
- Existing `SERVICE_MAP.yaml` files remain valid. Old `TODO` literal continues to be flagged as DET-006. New markers (`not-implemented`, `not-documented`, `not-measured`) are additive — a one-time hand-migration is recommended for clearer semantics but not required.

## [0.5.0] - 2026-04-28

### Added
- **`metadata.archspec_strict` flag** — opt-in switch in `SERVICE_MAP.yaml` that promotes the new diagnostic checks (DET-006 / DEP-001) from WARN to BLOCK at commit time. Default false; existing YAML files remain valid without the flag.
- **DET-006 — TODO catcher.** New pre-commit check `check_todos.py` and validator post-pass that flag literal `"TODO"` left in required-concrete fields: `dependencies.downstream.sync[].timeout`, `dependencies.storage[].name`, `events.{published,consumed}[].contract`, `api.endpoints[].contract`, `api.endpoints[].sla.{p99_latency,availability}`. WARN by default; BLOCK with `archspec_strict: true`. The CLI prints `WARN DET-006 …` on stderr and still exits 0 in default mode.
- **DEP-001 — write-path × events consistency.** New pre-commit check `check_write_path_events.py`. WARN if `consistency.write_path.pattern == "outbox"` and `events.published == []` (incomplete spec); WARN if `events.published != []` and pattern is `direct` (no atomicity guarantee between state mutation and event emission). Promoted to BLOCK with `archspec_strict: true`.
- **DEP-002 / DEP-003 / DEP-004 — multi-service graph consistency.** New pre-commit check `check_graph_consistency.py`. Activates when ≥2 `**/SERVICE_MAP.yaml` exist in the repo. Always WARN (never BLOCK, even in strict mode) because false-positives are unavoidable on partial monorepos. DEP-002: caller A names B in `downstream.sync` but B does not list A as upstream. DEP-003: published topic with no consumer in the monorepo. DEP-004: A.upstream lists B, but B does not call A and shares no event with it. Reproduces the freelance-marketplace `geo-service.upstream=api-gateway` mistake.
- **`/archspec:check-architecture`** — new slash command. Reads every `SERVICE_MAP.yaml` under a repo root and prints a markdown audit (issues + optional `--full` summary table). Surfaces DET-006/DEP-001/DEP-002/DEP-003/DEP-004 in one place. Read-only.
- **Aggregate auto-detection in `scan_go.py`.** New `aggregates: []` key in the JSON report. Heuristics: methods with name suffix `WithEvent` / `IfAbsent` / `CAS` → `optimistic`; `sync.Mutex` / `sync.RWMutex` inside `repository/` / `repo/` / `domain/` / `infra/` → `pessimistic`. Mutex outside scope (`usecase/`, `handler/`, `cmd/`) is ignored. Bootstrap step `3b-agg` proposes each finding via `AskUserQuestion`.
- **Top-level architecture spec ingest (opt-in)** in `/archspec:init`. Step 2a asks for the path to a top-level architecture document (e.g. `docs/project/architecture.md`) and uses its contents as conversation context for subsequent confirm-prompts. Spec is a hint, never an override; the user is told once that stale specs should be ignored in favour of code reality.
- **idempotency-by-name heuristic** in bootstrap step 3b. Endpoints whose name starts with a read prefix (`Get`, `List`, `Find`, `Read`, `Search`, `Has`, `Is`, `Count`, `Lookup`, `Query`, `Fetch`) default to `idempotency.required: false`; everything else (writes) defaults to `true`. The user always confirms — `No` on a write endpoint is recorded without any sermon.
- **Cross-service invariants prompt** in bootstrap step 3d. When a service has confirmed `events.published`, `events.consumed`, or an `outbox` / `saga` write path, the skill asks for 1–3 `consistency.cross_service_invariants[]` lines (skippable; empty answer leaves `[]`).

### Changed
- `READ_PREFIXES` and `is_read_endpoint()` moved from `generate_mermaid.py` to `_common.py` so the bootstrap and the Go scanner can share the same list. No behavioural change for the generator.

### Compatibility
- Existing `SERVICE_MAP.yaml` files remain valid without changes — `archspec_strict` is optional. New WARN-only checks do not break existing pre-commit pipelines.

## [0.4.3] - 2026-04-27

### Fixed
- **`/plugin update` now actually copies files into the install path.** Switched `marketplace.json` `source` from the github-object form (`{"source": "github", "repo": "krus210/archspec", "ref": "main"}`) to the relative-path form (`"./"`), matching the convention used by other single-repo plugins like [obra/superpowers](https://github.com/obra/superpowers). With the github-object form, Claude Code's installer was hitting a code path where it would update `installed_plugins.json` with the new version but skip the actual clone-and-copy step — users had to manually `cp -R ~/.claude/plugins/marketplaces/archspec ~/.claude/plugins/cache/archspec/archspec/<version>/`. With the relative path the installer copies directly from the marketplace clone into the install path with no second GitHub fetch. The `"."` form (without trailing slash) was tried in v0.1.1 and rejected by schema validation; `"./"` is accepted.

### Changed
- `plugin.json` now matches the convention of established Claude Code plugins: added `author`, `homepage`, and `keywords` fields. Functionally equivalent — discoverability only.
- `CONTRIBUTING.md`: dropped the `ref: main` note (it was a workaround that did not help) and the `cp -R` workaround instructions (they should not be needed once the relative-path source takes effect).

## [0.4.2] - 2026-04-27

### Fixed
- Pin marketplace `source.ref` to `main` so Claude Code's `/plugin update` reliably re-clones the repository on every release. Previously, without an explicit `ref`, the installer wrote a new version into `installed_plugins.json` but skipped the actual file fetch, leaving the install path empty and forcing users to copy files manually from `~/.claude/plugins/marketplaces/archspec/` to `~/.claude/plugins/cache/archspec/archspec/<version>/`.

## [0.4.1] - 2026-04-27

### Fixed
- **Sequence diagram line collision** (regression introduced in v0.3.0): the inline `{% if ep.is_read %}read{% else %}write{% endif %}` in `sequence.mmd.j2` interacted with Jinja's `trim_blocks=True` and ate the newline after `{% endif %}`, causing `svc->>store: write` and `svc-->>client: response` to render on the same line. Fix: read/write decision is now precomputed in `_enrich()` as a `storage_op` field; the template uses a plain variable. Regression test added.

### Added
- **Sequence diagram now visualises NATS publish for outbox-pattern services**: write endpoints (anything not prefixed with the read-verb list) now emit `svc->>events: publish <topic> (v<N>)` for each entry in `events.published`, after the storage write. A `participant events as message-bus` is declared when `published` is non-empty. This makes it visible *why* a service is marked `consistency.write_path: outbox` and which event is emitted in the same transaction.

## [0.4.0] - 2026-04-26

### Added
- **Reverse scan** mode in `scan_go.py`: `--reverse-scan <repo-root> --target <service-name>` walks a monorepo, finds Go files importing `<...>/<domain>/v1`, and emits a JSON list of consumer services with the gRPC method names they call (extracted from `<alias>.<Method>Request{` literals). Enables auto-population of `dependencies.upstream[]` and is the foundation for future circular-dependency checks.
- Bootstrap step 3b-rev in `architecture-sync` skill: prompts the user for a monorepo path, runs the reverse scanner, and writes confirmed consumers to `dependencies.upstream[]`. Falls back to `AskUserQuestion` (manual list) when the path is not provided; records a `k8s-todo` placeholder so future versions can derive consumers from k8s/service-mesh telemetry.
- Structured form for `dependencies.upstream[]` items: `{name, protocol, endpoints_used, discovered_via}`. Schema accepts both the legacy bare-string form (`- api-gateway`) and the new object form for backwards compatibility.

### Changed
- **Container diagram (`container.mmd`)** no longer renders endpoints as separate boxes inside the service container — that was a misuse of the C4 container level. Instead, upstream consumers (when present) are rendered as boxes outside the service with arrows pointing in; the methods they call appear as edge labels (e.g. `api-gateway -->|GetCity, GetDistance| svc`).
- Container diagram now uses `flowchart LR` (was `TB`), matching the context diagram.

## [0.3.0] - 2026-04-26

### Added
- `/archspec:init` Bootstrap questionnaire now explicitly asks the user for `service.responsibilities` and `service.invariants` before the auto-discovery pass. Previously these were left as `TODO` placeholders, making the generated `ARCHITECTURE.md` essentially empty.
- Auto-detection of gRPC `contract` paths: when the scanner sees `pb.RegisterXxxServer`, it searches up to 5 parent directories for a matching `proto/<domain>/v1/*.proto` file and returns it as `contract_hint` in the discovery report. The questionnaire proposes that path as the default `endpoints[].contract` value instead of `"TODO"`.
- Read-only-service heuristic for `consistency.write_path.pattern`: if the user accepts zero published events and zero mutating endpoints (anything not prefixed with `Get`, `List`, `Find`, `Read`, `Search`, `Has`, `Is`, `Count`, `Lookup`, `Query`, `Fetch`), default to `direct` instead of `outbox`.

### Changed
- Sequence diagram now distinguishes reads from writes: endpoints whose name begins with one of the read-prefix verbs above render `svc->>storage: read`; everything else renders `write`. Previously every endpoint was labelled `write`, which was wrong for read-only services like a geo lookup.
- `sequence.mmd` header dropped the misleading "(write path)" suffix.

### Fixed
- `DET-005` (manual edit of generated diagram) no longer triggers on `tests/golden/` or `examples/` paths — those are archspec-maintained golden references, not user-facing artefacts.

## [0.2.0] - 2026-04-26

### Added
- `/archspec:init` now auto-discovers HTTP/gRPC endpoints, downstream gRPC dependencies, storage clients (postgres/redis/mongodb/sql/in-memory), and messaging events (Kafka via `segmentio/kafka-go` and `IBM/sarama`; NATS core publish/subscribe and JetStream publish via `nats-io/nats.go`) by scanning the service's Go source code. After the scan, an interactive questionnaire (`AskUserQuestion`) fills in fields the scanner cannot extract (SLA, idempotency, timeouts, fallback strategy). The new scanner is `skills/architecture-sync/scripts/scan_go.py` — a pure-stdlib regex-based, read-only CLI that emits a JSON discovery report. Backends the scanner does not know (RabbitMQ, GCP Pub/Sub, in-house queues) cause **no failure** — they simply yield empty event arrays, and the questionnaire prompts the user to enumerate those events manually.

## [0.1.3] - 2026-04-26

### Fixed
- `.claude-plugin/plugin.json` no longer declares `commands`, `skills` or `hooks` as directory paths. Claude Code discovers `commands/` and `skills/` automatically by convention, and the `hooks` field is reserved for Claude Code event hook configuration (`PostToolUse` etc.), not for git hooks. The previous values failed manifest validation on `/plugin install`.

## [0.1.2] - 2026-04-26

### Fixed
- `.claude-plugin/marketplace.json` now uses the supported object form for `plugins[].source` (`{"source": "github", "repo": "krus210/archspec"}`). The previous `"."` string value failed Claude Code's marketplace schema validation and prevented `/plugin marketplace add krus210/archspec` from succeeding.

## [0.1.1] - 2026-04-26

### Fixed
- Installation instructions in `README.md` now use the supported `/plugin marketplace add` + `/plugin install` flow instead of the non-existent `/plugin install <github-url>` shortcut.

### Added
- `.claude-plugin/marketplace.json` so the repository can be added directly as a single-plugin Claude Code marketplace.

## [0.1.0] - 2026-04-26

Initial public release.

### Added
- JSON Schema for `SERVICE_MAP.yaml` and a `validate_servicemap` CLI.
- Deterministic Mermaid diagram generator (context, container, sequence) and `ARCHITECTURE.md` renderer with managed-region merge.
- `archspec-sync` entry point.
- Slash commands `/archspec:init`, `/archspec:sync`, `/archspec:validate`, `/archspec:investigate` and two autopilot skills.
- Pre-commit hooks for schema, dependency cycles, reference paths, diagram drift, breaking changes and exception discipline.
- Pre-push hooks for diagram drift and contract changes against the base branch.
- Go linters for handler idempotency, outbox pattern and optimistic locking, with a shared `lint.sh` dispatcher.
- Benchmarks for schema, determinism and violation detection, with a CI workflow.
- Reference documentation and a Go microservice example fixture.
