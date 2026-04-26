# Validation rules

Two layers, one catalog. Every rule has a stable id, a single owning
implementation, and a fixed severity.

| Layer | IDs | Where it runs | Latency budget |
| --- | --- | --- | --- |
| Deterministic | `DET-001`..`DET-015` | `hooks/pre-commit/run_all_checks.py` and `hooks/pre-push/` | < 1s, zero false positives |
| AI / static | `AI-001`..`AI-010` | `/archspec:validate` via `linters/<lang>/` | seconds, contextual |

Severity vocabulary:

- `BLOCK` — fails the commit (or `/archspec:validate` exit code).
- `WARN` — non-blocking warning surfaced in the report.
- `AUTO-FIX` — the hook can repair the issue automatically and re-stage.
- `INFO` — informational, used to draw reviewer attention.

Every rule supports two suppression channels — declarative entries in
`SERVICE_MAP.yaml` `exceptions[]` and inline `// archspec:ignore <ID> --
<reason>` pragmas. See [`EXCEPTIONS.md`](./EXCEPTIONS.md) for the policy.

---

## Deterministic layer (`DET-*`)

### DET-001 · Schema validation · BLOCK

Validates the staged `SERVICE_MAP.yaml` against
`skills/architecture-sync/schema/servicemap.schema.json` (JSON Schema
Draft-07). Implemented in `hooks/pre-commit/checks/check_schema.py`.
Every error reports the failing JSON pointer and the schema message.

The most common failures are: missing required keys (e.g. `metadata`,
`service.ownership.primary`), wrong type (e.g. an integer where a string
is expected), unknown property inside a closed core section
(`additionalProperties: false`), or pattern mismatches such as
`metadata.last_reviewed: 2026-4-25` (must be `YYYY-MM-DD`).

To fix, follow the JSON pointer in the error to the offending field.
Cross-reference [`SERVICE_MAP_SPEC.md`](./SERVICE_MAP_SPEC.md). Suppression
is intentionally not supported for `DET-001`: a malformed file cannot be
suppressed because no other rule can read it. Do not add it to
`exceptions[]`.

### DET-002 · Cycle and self-loop in sync dependencies · BLOCK

Implemented in `hooks/pre-commit/checks/check_cycles.py`. Walks
`dependencies.downstream.sync[]` for the staged file and reports two
shapes of error: the service depending on itself
(`service.name == sync[].service`) and the same downstream listed twice.

Common failure: copy-pasting a downstream entry while iterating on
timeouts and forgetting to rename the second copy. Less common but
critical: a refactor that splits a service in half and accidentally
references the original name.

Fix: remove the duplicate entry or correct the typo. Cross-service cycle
detection across multiple `SERVICE_MAP.yaml` files lives in the pre-push
hook (`hooks/pre-push/check_drift.py`), not here. To suppress (e.g. an
intentional self-call through a public API), add an `exceptions[]` entry
with `rule: DET-002`, an ADR, and an approver — though in practice you
should rename the entry instead.

### DET-003 · Test and contract path existence · BLOCK

Implemented in `hooks/pre-commit/checks/check_references.py`. Every
`api.endpoints[].contract` path, every `edge_cases[].test` path, and
every `scenarios[].test` path is resolved against the repo root and the
service root (the YAML's grandparent directory) so that fixtures nested
under `examples/<svc>/docs/SERVICE_MAP.yaml` remain portable.

Common failures: the file was deleted, renamed, or moved without
updating the YAML; the path uses the wrong separator
(`internal\\handler\\foo_test.go` on Windows); the `test:` field still
references the `::TestName` suffix but the underlying file was moved.

Fix: update the path or restore the file. Suppress with an
`exceptions[]` entry only when the contract is intentionally external
(e.g. an OpenAPI doc hosted in a sibling repo) — and even then, prefer
to vendor a copy. Inline `// archspec:ignore DET-003 -- <reason>` is not
supported; this is a YAML-level rule.

### DET-004 · Diagrams out of sync · AUTO-FIX

Implemented in `hooks/pre-commit/checks/check_diagrams.py`. When
`SERVICE_MAP.yaml` is staged, the hook re-runs the deterministic
generator (`skills/architecture-sync/scripts/sync.py`) into a temp
directory and compares the bytes against `docs/diagrams/*.mmd` and
`docs/ARCHITECTURE.md`. Any difference is flagged.

Common cause: editing `SERVICE_MAP.yaml` without running
`/archspec:sync`. Because the generator is fully deterministic
(alphabetical sort, pure `slugify`, no datetime/random/uuid, LF line
endings), any drift is reproducible.

Fix: run `/archspec:sync` and stage the regenerated files. The rule is
classified `AUTO-FIX` because the hook prints the exact command needed
and the generator is idempotent. Suppression is not supported and not
useful — diagrams that disagree with the contract have no value.

### DET-005 · Diagram edited without YAML · BLOCK

Same file, opposite direction. If a `*.mmd` diagram (`context.mmd`,
`container.mmd`, `sequence.mmd`) is staged but `SERVICE_MAP.yaml` is
not, the hook blocks the commit with the message "manual edit of
generated diagram".

The generated artifacts are write-only outputs of `/archspec:sync`.
Hand-editing them produces drift on the next sync run, when the
generator overwrites the manual changes. Most often this happens when a
contributor opens a `.mmd` file in their editor to tweak a label.

Fix: edit `SERVICE_MAP.yaml` and rerun `/archspec:sync`. Suppression is
not supported. If the generator output is genuinely insufficient, the
fix is to extend the templates under
`skills/architecture-sync/templates/`, not to bypass `DET-005`.

### DET-006 · Idempotency downgrade without ADR · BLOCK

Implemented in `hooks/pre-commit/checks/check_breaking_changes.py`.
Compares the staged YAML against `HEAD`. When an existing endpoint
flips `idempotency.required: true → false`, the hook requires a staged
file under `docs/adr/*.md` in the same commit.

This is one of the most consequential breaking changes a service can
make: clients that previously relied on automatic deduplication may
issue duplicate writes. The rule forces an ADR so the decision is
recorded and reviewable.

Fix: write `docs/adr/NNNN-relax-idempotency-on-<endpoint>.md`, stage
both files, and re-commit. Suppression via `exceptions[]` requires the
same ADR — there is no shortcut. Inline pragmas are not honored: this
is a YAML-level rule.

### DET-007 · Removed edge case or scenario without ADR · BLOCK

Same check file as `DET-006`. Compares the set of
`edge_cases[].id` and `scenarios[].id` between `HEAD` and the staged
file. Any removal that lacks a staged ADR is blocked.

Edge cases and scenarios are the contract's safety net. Removing
`EC-014` ("creation under partial network failure") without a written
rationale is exactly the kind of silent regression archspec exists to
prevent. Renaming an id (e.g. EC-014 → EC-200) counts as a removal +
addition; both must be justified.

Fix: write `docs/adr/NNNN-retire-EC014.md` explaining the rationale,
stage it alongside the YAML edit. Use `exceptions[]` only in
exceptional cases (e.g. a one-time data correction); ADR is still
required. No inline pragma support.

### DET-008 · API change without changelog entry · BLOCK

Same check file. Diffs the `api` block (excluding `changelog`) between
`HEAD` and the staged YAML. Any structural change without at least one
new entry in `api.changelog` is blocked.

Common failures: adding an endpoint and forgetting the changelog entry;
tightening a SLA without recording why; changing an `idempotency`
configuration. The rule treats `api.changelog` as append-only — a
missing or shorter list after the diff is also a failure.

Fix: append a free-form entry (string, object, anything) to
`api.changelog` describing the change. Suppression via `exceptions[]`
is allowed for trivial reformatting (whitespace), but the recommended
fix is always to append a `{date, change}` record.

### DET-009 · Consistency model change · WARN

Same check file. When `consistency.model` changes between `eventual`
and `strong`, the hook emits a warning. It does not block; flipping the
model has wide-reaching effects (read-your-writes guarantees, replica
configuration, contract negotiations with consumers) and warrants an
ADR but not a hard stop.

Common cause: experimenting with a stronger guarantee during a refactor
and committing the change before drafting the ADR. The warning is the
nudge to slow down.

Fix: write an ADR covering the new semantic. Suppression is rarely
appropriate — leave the warning visible until the ADR exists.

### DET-010 · Exceptions discipline · BLOCK

Implemented in `hooks/pre-commit/checks/check_exceptions.py`. Every
entry in `SERVICE_MAP.yaml exceptions[]` must have a non-empty `reason`
and `approved_by`. Both are required by the schema as well; this rule
catches the case where the schema accepts the field (string, length ≥ 1)
but the content is meaningless.

Common failure: stub entries left over from a refactor (`reason: TODO`,
`approved_by: TBD`). The check accepts any non-empty string; humans
review the actual content during PR review.

Fix: fill in real values. Suppression is not supported — `DET-010`
exists precisely to prevent suppressions from rotting.

### DET-011 · Exception ADR link · BLOCK

Same check file. Every `exceptions[].adr` field must point to an
existing file in the repository. Missing field, empty string, or path
that does not resolve all produce blocks.

Common failures: ADR file was renamed or moved; ADR was committed in a
different branch and was not merged before the exception PR; the path
uses a leading slash (`/docs/adr/...`) instead of a repo-relative one.

Fix: create the ADR or correct the path. The pre-commit hook resolves
paths relative to the repository root, not the YAML file's directory.

### DET-012 · Expired exceptions · WARN

Same check file. Every `exceptions[].expires` date is compared to the
current ISO date. Past dates produce a warning, not a block, so an
expired exception does not freeze CI — but it is visible on every
commit until cleaned up.

This is the one place archspec is allowed to read the wall clock.
Tests inject `today=` explicitly. The intent is to make stale
suppressions noisy enough to drive removal.

Fix: either remove the entry (preferred) or extend `expires` with a
new ADR. Suppression is intentionally not supported — `DET-012` is
itself a warning, and warnings must remain visible.

### DET-013 · Exception change visibility · INFO

Implemented as a summary line in `run_all_checks.py`. When the
`exceptions[]` block changes between `HEAD` and the staged YAML, the
hook surfaces an `INFO` notice on the run summary.

This is documentation, not enforcement. The goal is to make it harder
for an exception change to slip into a large PR diff unnoticed by
reviewers.

There is nothing to fix and nothing to suppress. To reduce noise, batch
exception changes into dedicated PRs labeled `archspec/exception`.

### DET-014 · Temporary exception without expires · WARN

Same check file as `DET-010`. Scans every `exceptions[].reason` for the
words `migration`, `temporary`, or `legacy` (case-insensitive). If the
reason matches and the entry has no `expires` date, the hook warns.

The pattern catches the most common rationale for a "should be
short-lived" suppression. Treating it as `WARN` (not `BLOCK`) is a
deliberate trade-off — sometimes a legacy adapter genuinely has no
removal date — but the warning serves as a prompt to add one.

Fix: add an `expires: YYYY-MM-DD` field. Suppression is not supported
and not appropriate.

### DET-015 · Pragma format discipline · BLOCK

Implemented in `hooks/pre-commit/checks/check_pragmas.py`. Scans every
staged source file (`.go`, `.py`, `.js`, `.ts`, `.java`, `.kt`, `.rs`)
for `archspec:ignore` and `archspec:ignore-block` pragmas. Every pragma
must include a `--` reason comment; otherwise the commit is blocked.

Common failure: copy-pasting a pragma from a snippet and forgetting the
trailing reason (`// archspec:ignore AI-002` instead of
`// archspec:ignore AI-002 -- migration script, single-use`). The rule
treats the missing reason as a hard error because unreasoned
suppressions are the failure mode that makes the entire suppression
mechanism untrustworthy.

Fix: append `-- <reason>` to the pragma. Suppression is not supported
(the rule itself is what makes other suppressions auditable). If you
cannot articulate the reason in a single line, the suppression should
move to `SERVICE_MAP.yaml exceptions[]` where the full ADR + approver
context lives.

---

## AI layer (`AI-*`)

### AI-001 · Idempotency declared but not implemented · BLOCK

Implemented in `linters/go/handler_idempotency.go`. For every endpoint
where `idempotency.required: true`, the linter looks up the matching
Go handler function (matched by `Endpoint.Name`), then walks its body
for `r.Header.Get("<KeySource>")` calls. Two failure shapes are
reported: no matching handler at all, and a handler that does not read
the declared header.

Common failures: the handler was renamed but the YAML still references
the old name; the header constant lives in a sibling package and the
linter cannot see the literal string; the handler reads the header but
does not pass it to the dedup store.

Fix: name the handler exactly `Endpoint.Name` and read the header
explicitly. To suppress on a documented exception (e.g. an internal
admin endpoint with no client-side retries), add an `exceptions[]`
entry scoped to the endpoint. Inline `// archspec:ignore AI-001 --
<reason>` is supported when the suppression applies to a single
function.

### AI-002 · Outbox pattern violation · BLOCK

Implemented in `linters/go/outbox_pattern.go`. When
`consistency.write_path.pattern: outbox`, the linter walks every
function body and flags the sequence `<repo>.Save(...)` followed by
`<publisher>.Publish(...)`. The expected pattern is `Save(...)` plus
an outbox-table append in the same transaction.

Common failures: inherited "save then publish" code from before the
service adopted the outbox pattern; a refactor that introduced the
outbox table for one entity but missed another; a helper that calls
`Publish` indirectly through a wrapper the linter does not match.

Fix: append the event to `go_extensions.outbox_table` (default surfaced
in the suggested-fix string) inside the same database transaction that
performed the save. Suppress one-off migration scripts with
`// archspec:ignore AI-002 -- migration: backfill outbox`. Persistent
exceptions belong in `exceptions[]` with an ADR.

### AI-003 · Optimistic locking missing version predicate · BLOCK

Implemented in `linters/go/optimistic_locking.go`. When at least one
`concurrency.aggregates[].write_strategy: optimistic` is declared, the
linter scans every Go string literal for SQL `UPDATE` statements and
asserts that the configured version column (default `row_version`,
overridden by `go_extensions.optimistic_locking_field`) appears at
least twice — once in `SET` and once in `WHERE`.

Common failures: hand-written SQL that omits `AND row_version = ?`; an
ORM-generated query that uses a column name (`version`) different from
the declared field; an UPDATE without a `WHERE` clause at all (the
linter skips this because it is a separate bug).

Fix: append `AND <field> = ?` to the WHERE clause and bump the column
in `SET`. Suppress one-off admin scripts with an inline pragma; durable
exceptions (e.g. an aggregate that intentionally uses application-level
serialization) belong in `exceptions[]`.

### AI-004 · Architecture rules — facade only · BLOCK

Specified in the design but **not yet implemented in `linters/go/`**.
Once shipped, the rule will read
`architecture_rules.facade_only.[serviceX]` and report any code that
imports `serviceX/internal/...` directly instead of going through the
declared facade.

Until the implementation lands, declaring the rule has documentation
value only. The pre-commit and `/archspec:validate` runs will neither
report nor block on it. Track the implementation status in
`linters/go/README.md`.

To prepare for the rule, declare the facade in `architecture_rules` now
and review imports manually. When the linter ships, the existing
declaration will activate it without a YAML change.

### AI-005 · Edge case coverage · WARN

Specified in the design but **not yet implemented in `linters/go/`**.
The intended behavior: for every `edge_cases[]` entry, locate the test
referenced by `test:` and assert that it actually exercises the case.
Severity is `WARN` because heuristic test inspection is inherently
fuzzy.

Today only `DET-003` checks that the test file exists. `AI-005` will
extend the check to function-level matching (e.g. `TestEC001` exists
inside the file) and ideally to behavior-level matching (the test
mentions the documented condition).

Until shipped, treat `edge_cases[]` as a peer-review checklist. Add the
test reference and rely on PR review until the linter takes over.

### AI-006 · Scenario coverage · WARN

Specified in the design but **not yet implemented in `linters/go/`**.
Mirrors `AI-005` for the `scenarios[]` array. The intended behavior:
locate the e2e test (and, when present, the synthetic monitor) and
assert that both are alive.

Today the only check is `DET-003` (file existence). The future linter
will additionally probe the monitor name through a stub registry and
validate the test signature.

Until shipped, treat scenario coverage as a release-checklist item.

### AI-007 · Swallowed downstream errors · BLOCK

Specified in the design but **not yet implemented in `linters/go/`**.
The intended behavior: for every entry in
`dependencies.downstream.sync[]` with `on_failure` set, scan the
calling code for the pattern `_ = svc.Call(...)` (or its idiomatic
equivalents) and block when the error is dropped.

Today the policy is documented but unenforced. PR reviewers should
flag dropped errors manually.

When the rule ships, fix by handling the error explicitly per the
declared `on_failure` policy (`degrade`, `fail`, `retry`). Suppress
with an inline pragma when the error is intentionally non-fatal (e.g.
fire-and-forget logging).

### AI-008 · Redundant call detection · INFO

Specified in the design but **not yet implemented in `linters/go/`**.
Intended behavior: detect N+1 patterns where a batch method exists, or
the same entity fetched twice in one flow. Severity is `INFO` because
the rule is heuristic and the cost-benefit varies.

Today there is no enforcement. The rule is documented so that future
contributors can reserve the id and so users can plan
`<lang>_extensions` configuration around it.

### AI-009 · Undeclared dependency · BLOCK

Specified in the design but **not yet implemented in `linters/go/`**.
The intended behavior: scan code for calls to services, topics, or
databases not present in the YAML's `dependencies` or `events` blocks.

Today, undeclared dependencies are caught by reviewers reading the
generated `ARCHITECTURE.md` (which lists exactly what the YAML
declares; missing entries are visible by absence). When the linter
ships it will provide line-level evidence.

To prepare, keep `dependencies` and `events` exhaustive. The pre-push
drift check (`hooks/pre-push/check_drift.py`) already enforces
consistency between the YAML and the generated diagrams; adding a code
scan closes the remaining gap.

### AI-010 · Undeclared endpoint · BLOCK

Specified in the design but **not yet implemented in `linters/go/`**.
Intended behavior: detect new HTTP/gRPC handlers registered in code
that are missing from `api.endpoints[]`.

Today the easiest way to catch undeclared endpoints is to grep for the
service's router setup and reconcile against `api.endpoints` during
review. When the linter ships it will run during `/archspec:validate`.

When implementing, keep the matcher conservative — false positives on
this rule erode trust quickly.

---

## See also

- [`SERVICE_MAP_SPEC.md`](./SERVICE_MAP_SPEC.md) — every key these rules
  read.
- [`EXCEPTIONS.md`](./EXCEPTIONS.md) — declarative and inline
  suppression for any rule that supports it.
- [`EXTENDING.md`](./EXTENDING.md) — adding new linters under
  `linters/<lang>/` and reserving new `AI-*` ids.
- `linters/go/README.md` — currently shipped subcommands.
- `hooks/pre-commit/checks/` — `DET-*` implementations.
