# SERVICE_MAP.yaml — schema reference

`SERVICE_MAP.yaml` is the single source of truth for a microservice's
architecture contract. It is read by every archspec workflow:
`/archspec:sync` (diagram + `ARCHITECTURE.md` generation), the pre-commit
hook (`DET-001..015`), `/archspec:validate` (`AI-001..010`), and
`/archspec:investigate` (read-side feature workflow).

This document is the user-facing reference. The authoritative schema lives
at `skills/architecture-sync/schema/servicemap.schema.json` (JSON Schema
Draft-07).

---

## Top-level shape

```yaml
metadata:       { ... }   # required
service:        { ... }   # required
api:            { ... }   # required
dependencies:   { ... }   # required
events:         { ... }   # required
consistency:    { ... }   # required
concurrency:    { ... }   # required

edge_cases:     [ ... ]   # optional
scenarios:      [ ... ]   # optional
failure_modes:  [ ... ]   # optional
architecture_rules: { ... }   # optional
exceptions:     [ ... ]   # optional

go_extensions:      { ... }   # optional, language-scoped
python_extensions:  { ... }   # optional, language-scoped
node_extensions:    { ... }   # optional, language-scoped
```

The seven required core sections are validated with
`additionalProperties: false`; any unknown key inside them is a `DET-001`
error. Anything matching the pattern `*_extensions` is open
(`additionalProperties: true`) so language plug-ins under `linters/<lang>/`
can extend the contract without a schema PR.

## Quick reference

Every property in the schema, top to bottom. `R` = required, `O` = optional.

| Path | Type | R/O | Notes |
| --- | --- | --- | --- |
| `metadata` | object | R | Provenance and review cadence. |
| `metadata.schema_version` | string `^\d+\.\d+$` | R | Bump on schema breaks; see `metadata.schema_version` migration policy. |
| `metadata.source_of_truth` | enum `local`, `external` | R | `external` if generated from another system. |
| `metadata.drift_check_in_ci` | boolean | R | Toggles the pre-push drift gate. |
| `metadata.last_reviewed` | string `YYYY-MM-DD` | R | Date of last human review; surfaced by `/archspec:investigate`. |
| `service` | object | R | Identity and ownership. |
| `service.name` | string (min length 1) | R | Stable slug; used for diagram node ids. |
| `service.team` | string (min length 1) | R | Free-form team handle. |
| `service.language` | string (min length 1) | R | Activates `linters/<language>/` (`go`, `python`, `node`, ...). |
| `service.repo` | string (min length 1) | R | Repository URL or path. |
| `service.domain` | string (min length 1) | R | Bounded context label. |
| `service.ownership` | object | R | Two-field record. |
| `service.ownership.primary` | string | R | Primary maintainer (`@handle` or email). |
| `service.ownership.oncall` | string | R | Oncall rotation handle. |
| `service.responsibilities` | array of string | R | What the service owns; bullet list. |
| `service.invariants` | array of string | R | Properties that must always hold. |
| `api` | object | R | Public surface. |
| `api.version` | integer (min 1) | R | Major API version. |
| `api.endpoints` | array of [endpoint](#endpoint) | R | Empty array allowed. |
| `api.changelog` | array | R | Append-only; required by `DET-008` on api edits. |
| `dependencies` | object | R | Outgoing relationships. |
| `dependencies.upstream` | array | R | Services that call us. |
| `dependencies.downstream` | object | R | Services we call. |
| `dependencies.downstream.sync` | array of object | R | Synchronous calls. |
| `dependencies.downstream.sync[].service` | string | R | Target service name. |
| `dependencies.downstream.sync[].timeout` | string | R | Duration (e.g. `300ms`). |
| `dependencies.downstream.sync[].retries` | integer (min 0) | R | Retry budget. |
| `dependencies.downstream.sync[].fallback` | string | R | What replaces the call on failure. |
| `dependencies.downstream.sync[].on_failure` | string | R | Policy: `degrade`, `fail`, etc. |
| `dependencies.downstream.async` | array of object | R | Asynchronous calls. |
| `dependencies.downstream.async[].topic` | string | R | Broker topic name. |
| `dependencies.downstream.async[].contract` | string | R | Path to schema doc. |
| `dependencies.downstream.async[].qos` | string | R | `at-least-once`, `exactly-once`, etc. |
| `dependencies.storage` | array of object | R | Owned datastores. |
| `dependencies.storage[].type` | string | R | `postgres`, `redis`, ... |
| `dependencies.storage[].name` | string | R | Logical name. |
| `dependencies.storage[].owned_by` | string | R | Service that owns the schema. |
| `events` | object | R | Pub/sub surface. |
| `events.published` | array of object | R | Topics this service emits. |
| `events.published[].topic` | string | R | Topic name. |
| `events.published[].contract` | string | R | Path to schema doc. |
| `events.published[].version` | integer | R | Contract version. |
| `events.consumed` | array of object | R | Topics this service consumes. |
| `events.consumed[].topic` | string | R | Topic name. |
| `events.consumed[].contract` | string | R | Path to schema doc. |
| `events.consumed[].expected_version` | integer | R | Minimum supported producer version. |
| `consistency` | object | R | Write/read semantics. |
| `consistency.model` | enum `eventual`, `strong` | R | Service-wide default. |
| `consistency.bounded_aggregate` | string | R | Aggregate root name. |
| `consistency.write_path` | object | R | How writes propagate. |
| `consistency.write_path.pattern` | enum `outbox`, `direct`, `saga` | R | Drives `AI-002` (outbox vs direct publish). |
| `consistency.read_path` | object | R | Read guarantees. |
| `consistency.read_path.consistency` | enum `read-your-writes`, `eventual` | R | What clients must expect. |
| `consistency.cross_service_invariants` | array of string | R | Cross-boundary constraints. |
| `concurrency` | object | R | Conflict semantics. |
| `concurrency.aggregates` | array of object | R | Per-aggregate write strategy. |
| `concurrency.aggregates[].name` | string | R | Aggregate label. |
| `concurrency.aggregates[].write_strategy` | enum `optimistic`, `pessimistic` | R | Drives `AI-003` (locking checks). |
| `concurrency.hot_keys` | array of string | R | Known hot partitions. |
| `concurrency.shared_state` | array of string | R | Caches, locks, queues shared between instances. |
| `edge_cases` | array of object | O | Documented edge cases. |
| `edge_cases[].id` | string `^EC-\d+$` | R | Stable identifier. |
| `edge_cases[].description` | string | R | What edge case this is. |
| `edge_cases[].test` | string | R | Path to the covering test. |
| `scenarios` | array of object | O | End-to-end scenarios. |
| `scenarios[].id` | string `^S-\d+$` | R | Stable identifier. |
| `scenarios[].description` | string | R | One-line summary. |
| `scenarios[].test` | string | R | Path to the e2e test. |
| `scenarios[].monitor` | string | O | Synthetic monitor name. |
| `failure_modes` | array of object | O | Known failure modes. |
| `failure_modes[].when` | string | R | Trigger condition. |
| `failure_modes[].user_sees` | string | R | Observable behavior. |
| `failure_modes[].detection` | string | R | How an operator notices. |
| `architecture_rules` | object | O | Free-form policy block (e.g. `facade_only`, `forbidden_imports`, `required_layers`). |
| `exceptions` | array of object | O | Suppressions; see [`EXCEPTIONS.md`](./EXCEPTIONS.md). |
| `exceptions[].rule` | string `^(DET\|AI)-\d{3}$` | R | Rule being suppressed. |
| `exceptions[].scope` | object | R | What the suppression applies to (free-form keys). |
| `exceptions[].reason` | string (min length 1) | R | Why; enforced by `DET-010`. |
| `exceptions[].approved_by` | string (min length 1) | R | Approver handle; enforced by `DET-010`. |
| `exceptions[].adr` | string (min length 1) | R | ADR path; enforced by `DET-011`. |
| `exceptions[].expires` | string `YYYY-MM-DD` | O | If absent and `reason` matches `migration\|temporary\|legacy`, `DET-014` warns. |
| `<lang>_extensions` | object | O | Open container; values are language-specific. |
| `go_extensions.optimistic_locking_field` | string | O | Column name used by `AI-003` (default `row_version`). |
| `go_extensions.outbox_table` | string | O | Table name surfaced in `AI-002` fix hints. |

### endpoint

| Path | Type | R/O | Notes |
| --- | --- | --- | --- |
| `name` | string | R | Must match the handler function (used by `AI-001`). |
| `protocol` | enum `HTTP`, `gRPC` | R | Transport. |
| `idempotency` | [idempotency](#idempotency) | R | Always present, even when `required: false`. |
| `contract` | string | R | OpenAPI/Proto path; checked by `DET-003`. |
| `sla` | object | R | Two-field record. |
| `sla.p99_latency` | string | R | E.g. `200ms`. |
| `sla.availability` | string | R | E.g. `99.95%`. |

### idempotency

| Path | Type | R/O | Notes |
| --- | --- | --- | --- |
| `required` | boolean | R | When `true`, `key_source` and `storage` are required (conditional rule). |
| `key_source` | string | C | Required when `required: true`. Use `header: X-Header-Name` form. |
| `key_ttl` | string | O | Duration (e.g. `24h`). |
| `storage` | string | C | Required when `required: true`. E.g. `redis: idemp:{key}`. |
| `on_duplicate` | string | O | Policy text (e.g. `return cached response`). |

`C` = conditionally required by the JSON Schema `if`/`then` clause.

---

## Required core sections

### `metadata`

Provenance for the file itself. `last_reviewed` is the only field that is
allowed to read the wall clock during validation (via `DET-012`). Everything
else is static.

```yaml
metadata:
  schema_version: "1.0"
  source_of_truth: local
  drift_check_in_ci: true
  last_reviewed: "2026-04-25"
```

### `service`

Identity, ownership, and the two narrative fields (`responsibilities`,
`invariants`) that drive the generated `ARCHITECTURE.md`. `service.language`
is load-bearing: it selects the linter directory under `linters/`. See
[`EXTENDING.md`](./EXTENDING.md).

### `api`

A versioned list of endpoints plus an append-only `changelog`. `DET-008`
blocks any structural change to `api` that does not bump `changelog`.

### `dependencies`

Outgoing relationships in three buckets: `upstream` (for documentation),
`downstream.sync` (timeout/retry/fallback policy required), `downstream.async`
(topic/contract/qos). `storage` lists owned datastores.

### `events`

Pub/sub surface. Every published topic must declare a contract path and a
version. Every consumed topic must declare an `expected_version` so a
producer bump is detectable.

### `consistency`

The semantic backbone. `consistency.write_path.pattern` activates the
outbox AI rule (`AI-002`); `consistency.read_path.consistency` documents
what clients must expect; `cross_service_invariants` is free-form prose
asserted by `/archspec:validate`.

### `concurrency`

Aggregate-level write strategy. `optimistic` activates `AI-003`
(version-column predicate on `UPDATE`). `hot_keys` and `shared_state` are
narrative only on day one but reserved for future rules.

---

## Optional sections

### `edge_cases` and `scenarios`

Both are arrays of `{id, description, test}` records. The `id` patterns
(`^EC-\d+$`, `^S-\d+$`) are required so that removed entries can be
detected by `DET-007` (a removal without an ADR is a block). `scenarios`
may carry an extra `monitor` string for synthetic observability.

### `failure_modes`

Operator-facing documentation. No automation reads it on day one, but
the generator includes it in `ARCHITECTURE.md`.

### `architecture_rules`

Free-form policy block. The schema declares it as `type: object` with no
inner constraints so teams can experiment. The reserved sub-keys
(`facade_only`, `forbidden_imports`, `required_layers`) are read by
`AI-004` once it is implemented.

### `exceptions`

The declarative suppression channel. Each entry must reference a real
rule (`DET-*` or `AI-*`), include `reason`, `approved_by`, and a path to
an `adr` file (enforced by `DET-010`/`DET-011`). See
[`EXCEPTIONS.md`](./EXCEPTIONS.md) for the full lifecycle.

### `<lang>_extensions`

Pattern key matching `*_extensions$`. Values are arbitrary objects. By
convention the prefix is the same string as `service.language` (`go`,
`python`, `node`, ...). Used by per-language linters; documented in
[`EXTENDING.md`](./EXTENDING.md).

---

## JSON Schema rules

- **Draft**: JSON Schema Draft-07 (`$schema:
  http://json-schema.org/draft-07/schema#`).
- **Closed core**: every required top-level section uses
  `additionalProperties: false`. Unknown keys inside `metadata`,
  `service`, `api`, `dependencies`, `events`, `consistency`, or
  `concurrency` are `DET-001` errors.
- **Open extensions**: `patternProperties: { "_extensions$": { type: object } }`
  permits arbitrary `<lang>_extensions` blocks at the top level.
- **Conditional idempotency**: when `endpoint.idempotency.required: true`,
  the schema requires both `key_source` and `storage` via an `if`/`then`
  clause.
- **Pattern identifiers**: `metadata.schema_version` must match
  `^\d+\.\d+$`; dates use `^\d{4}-\d{2}-\d{2}$`; `edge_cases[].id` matches
  `^EC-\d+$`; `scenarios[].id` matches `^S-\d+$`; `exceptions[].rule`
  matches `^(DET|AI)-\d{3}$`.
- **Cross-file conditional**: every `exceptions[].rule` must reference a
  rule documented in [`VALIDATION_RULES.md`](./VALIDATION_RULES.md).
  Rule-id existence is enforced by the schema regex; rule semantics
  remain documentation.

---

## Minimal example

Smallest file that passes `DET-001` (lifted from
`benchmarks/determinism/inputs/01_minimal.yaml`):

```yaml
metadata:
  schema_version: "1.0"
  source_of_truth: local
  drift_check_in_ci: true
  last_reviewed: "2026-04-25"
service:
  name: minimal-service
  team: platform
  language: go
  repo: github.com/example/minimal-service
  domain: example
  ownership:
    primary: "@alice"
    oncall: "@oncall"
  responsibilities:
    - "expose REST API"
  invariants:
    - "all writes go through the outbox"
api:
  version: 1
  endpoints: []
  changelog: []
dependencies:
  upstream: []
  downstream:
    sync: []
    async: []
  storage: []
events:
  published: []
  consumed: []
consistency:
  model: eventual
  bounded_aggregate: example
  write_path:
    pattern: outbox
  read_path:
    consistency: eventual
  cross_service_invariants: []
concurrency:
  aggregates: []
  hot_keys: []
  shared_state: []
```

## Full example

Realistic file exercising every optional section (lifted from
`benchmarks/determinism/inputs/02_full.yaml`):

```yaml
metadata:
  schema_version: "1.0"
  source_of_truth: local
  drift_check_in_ci: true
  last_reviewed: "2026-04-25"
service:
  name: listings-service
  team: marketplace
  language: go
  repo: github.com/example/listings-service
  domain: listings
  ownership:
    primary: "@alice"
    oncall: "@listings-oncall"
  responsibilities:
    - "expose REST API for listings"
    - "publish ListingCreated events"
  invariants:
    - "all writes go through the outbox"
    - "listing IDs are monotonic"
api:
  version: 2
  endpoints:
    - name: CreateListing
      protocol: HTTP
      idempotency:
        required: true
        key_source: header:Idempotency-Key
        key_ttl: "24h"
        storage: redis
        on_duplicate: return_original
      contract: openapi/listings.yaml#/paths/~1listings/post
      sla:
        p99_latency: "200ms"
        availability: "99.9%"
    - name: GetListing
      protocol: HTTP
      idempotency:
        required: false
      contract: openapi/listings.yaml#/paths/~1listings~1{id}/get
      sla:
        p99_latency: "100ms"
        availability: "99.95%"
  changelog: []
dependencies:
  upstream:
    - api-gateway
  downstream:
    sync:
      - service: pricing-service
        timeout: "300ms"
        retries: 2
        fallback: "cache"
        on_failure: "degrade"
    async:
      - topic: "listings.created"
        contract: "schemas/listing_created.json"
        qos: at-least-once
  storage:
    - type: postgres
      name: listings_db
      owned_by: listings-service
    - type: redis
      name: idempotency_cache
      owned_by: listings-service
events:
  published:
    - topic: "listings.created"
      contract: "schemas/listing_created.json"
      version: 1
  consumed:
    - topic: "users.deleted"
      contract: "schemas/user_deleted.json"
      expected_version: 1
consistency:
  model: eventual
  bounded_aggregate: listing
  write_path:
    pattern: outbox
  read_path:
    consistency: read-your-writes
  cross_service_invariants:
    - "a listing always has a valid owner_id"
concurrency:
  aggregates:
    - name: listing
      write_strategy: optimistic
  hot_keys:
    - "listing:popular"
  shared_state:
    - "idempotency_cache"
edge_cases:
  - id: EC-001
    description: "duplicate listing creation"
    test: "internal/handler/listing_test.go::TestEC001"
scenarios:
  - id: S-001
    description: "happy path create listing"
    test: "tests/e2e/scenario_001_test.go"
    monitor: "synthetic-ms-listings-create"
failure_modes:
  - when: "kafka unavailable"
    user_sees: "create succeeds, indexer eventually catches up"
    detection: "lag metric > 30s"
exceptions:
  - rule: AI-001
    scope:
      endpoint: "GET /admin/health"
    reason: "internal admin endpoint, no client retries"
    approved_by: "@alice"
    adr: "docs/adr/0042-skip-idempotency-on-admin.md"
    expires: "2026-12-31"
```

---

## See also

- [`VALIDATION_RULES.md`](./VALIDATION_RULES.md) — every `DET-*` and `AI-*`
  rule that reads this file.
- [`EXCEPTIONS.md`](./EXCEPTIONS.md) — declarative and inline suppression.
- [`EXTENDING.md`](./EXTENDING.md) — adding a new language linter and
  `<lang>_extensions` block.
- `skills/architecture-sync/schema/servicemap.schema.json` — authoritative
  JSON Schema (the source of this reference).
