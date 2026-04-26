# Exceptions

Some violations are intentional. archspec supports two suppression
channels, both auditable, both subject to the discipline rules
`DET-010`..`DET-015` (see [`VALIDATION_RULES.md`](./VALIDATION_RULES.md)).

| Channel | Where | When to use |
| --- | --- | --- |
| Declarative | `SERVICE_MAP.yaml exceptions[]` | Long-lived, scoped to an endpoint or aggregate, requires an ADR. |
| Inline pragma | `// archspec:ignore <ID> -- <reason>` in code | One-off, scoped to a single statement or function. |

Both channels must justify themselves: a `reason`, an approver, and (for
declarative entries) a link to an ADR. Unjustified suppressions are
treated as bugs by the deterministic layer.

---

## 1. Declarative exceptions (preferred)

The `exceptions[]` array in `SERVICE_MAP.yaml` is the canonical place
for suppressions. The schema enforces structure
(`SERVICE_MAP_SPEC.md`); the deterministic checks enforce content
(`DET-010`..`DET-014`).

```yaml
exceptions:
  - rule: AI-001
    scope:
      endpoint: "GET /admin/health"
    reason: "internal admin endpoint, no client retries possible"
    approved_by: "@alice"
    adr: "docs/adr/0042-skip-idempotency-on-admin.md"
    expires: "2026-12-31"
  - rule: AI-002
    scope:
      function: "internal/migrations/backfill.go::runBackfill"
    reason: "migration job, single-use, runs once during cutover"
    approved_by: "@bob"
    adr: "docs/adr/0043-backfill-outbox-bypass.md"
    expires: "2026-06-30"
```

### Required fields

- `rule` — must match `^(DET|AI)-\d{3}$` and reference a documented
  rule. Suppressing an undefined rule is a `DET-001` schema error.
- `scope` — free-form object describing what the suppression applies
  to. Common shapes: `{endpoint: "..."}`, `{function: "..."}`,
  `{aggregate: "..."}`, `{path: "internal/legacy/**"}`. The schema
  does not enforce keys; use what makes the scope unambiguous to the
  reviewer.
- `reason` — non-empty string. `DET-010` blocks empty or stub values.
- `approved_by` — non-empty string. By convention `@handle`, but any
  identifier works.
- `adr` — non-empty string pointing to a real file. `DET-011` blocks
  if the file does not exist in the repository.

### Optional fields

- `expires` — `YYYY-MM-DD` date. Past dates produce `DET-012` warnings
  on every commit. Reasons matching `migration`, `temporary`, or
  `legacy` without an `expires` produce `DET-014` warnings.

### Why declarative is preferred

- Lives next to the architecture contract; reviewers see the
  exception when reviewing the service.
- The ADR link forces a written rationale that survives the original
  commit message.
- Scope is structured, so a future tool can audit "all `AI-001`
  suppressions across the org" mechanically.
- Auto-expires through `DET-012`, prompting periodic review.

---

## 2. Inline pragmas

For one-off suppressions where the surrounding context is necessary,
use an inline pragma directly in the source file:

```go
// archspec:ignore AI-002 -- migration script, single-use
repo.Save(ctx, item)
publisher.Publish(ctx, event)
```

Block-scoped variant suppresses multiple rules over a function or
region:

```go
// archspec:ignore-block AI-001 AI-007 -- legacy adapter, removal scheduled Q3
func legacyHandler(ctx context.Context, r *http.Request) error {
    // ... pre-existing code ...
}
```

Pragma format (enforced by `DET-015`):

```
// archspec:ignore <ID> [<ID>...] -- <reason>
// archspec:ignore-block <ID> [<ID>...] -- <reason>
```

Rules:

- The `--` delimiter is mandatory. A pragma without `-- <reason>` is a
  `DET-015` block.
- The reason must be a single line. If it does not fit, move to the
  declarative channel.
- The pragma matches the comment style of the surrounding language:
  `//` for Go/JS/TS/Java/Kotlin/Rust, `#` for Python. The check looks
  for the literal `archspec:ignore` substring; the comment marker is
  language-defined.
- Block scope (`archspec:ignore-block`) applies until the closing brace
  of the enclosing function or block. Linters interpret this per
  language; the Go reference linter scopes by AST function.

### Languages currently scanned by `DET-015`

`.go`, `.py`, `.js`, `.ts`, `.java`, `.kt`, `.rs`. Source files in
other languages are not scanned for pragmas; use declarative
exceptions for those services.

---

## 3. Discipline rules summary

`DET-010`..`DET-015` exist to keep the suppression mechanism trustworthy.
Full text in [`VALIDATION_RULES.md`](./VALIDATION_RULES.md); the table
below is a quick reference.

| Rule | Severity | What it enforces |
| --- | --- | --- |
| `DET-010` | BLOCK | Every `exceptions[]` entry has `reason` and `approved_by`. |
| `DET-011` | BLOCK | Every `exceptions[]` entry has an `adr` link to an existing file. |
| `DET-012` | WARN | `exceptions[].expires` in the past surfaces a warning. |
| `DET-013` | INFO | Any change to `exceptions[]` is highlighted on the PR run summary. |
| `DET-014` | WARN | Reason mentions `migration\|temporary\|legacy` but no `expires` is set. |
| `DET-015` | BLOCK | Inline pragma without `-- <reason>` fails the commit. |

These run on every commit; an exception that violates them is a defect
in the suppression itself, not in the code.

---

## 4. Worked examples

### 4.1 Declarative — admin endpoint without idempotency

A health endpoint accessed only by Kubernetes liveness probes does not
benefit from idempotency. Add the exception:

```yaml
api:
  endpoints:
    - name: GetAdminHealth
      protocol: HTTP
      idempotency:
        required: false
      contract: "openapi/admin.yaml#/paths/~1admin~1health/get"
      sla: { p99_latency: "50ms", availability: "99.99%" }

exceptions:
  - rule: AI-001
    scope:
      endpoint: "GET /admin/health"
    reason: "internal admin endpoint, no client retries possible"
    approved_by: "@alice"
    adr: "docs/adr/0042-skip-idempotency-on-admin.md"
    expires: "2026-12-31"
```

The ADR (`docs/adr/0042-skip-idempotency-on-admin.md`) records the
context: who relies on the endpoint, why retries are not a concern, when
to revisit the decision.

### 4.2 Inline — backfill script bypasses the outbox

A one-time migration job needs to publish events without going through
the outbox table. Inline pragma is appropriate because the suppression
is single-use and the function will be deleted after the migration:

```go
// archspec:ignore-block AI-002 -- backfill: events emitted post-write
// during the cutover from direct-publish to outbox.
func runBackfillFor(ctx context.Context, ids []string) error {
    for _, id := range ids {
        item, err := repo.Load(ctx, id)
        if err != nil {
            return err
        }
        if err := repo.Save(ctx, item); err != nil {
            return err
        }
        if err := publisher.Publish(ctx, item.toEvent()); err != nil {
            return err
        }
    }
    return nil
}
```

When the migration ships, delete the function. The pragma goes with it.

### 4.3 Inline — single-statement allowance

For a single statement (not a whole function), use the line-scoped
form:

```go
key := r.Header.Get("X-Idempotency-Key")
if key == "" {
    // archspec:ignore AI-001 -- legacy clients without the header are
    // allowed to retry; we hash the body instead.
    key = hashBody(r.Body)
}
```

---

## 5. Inline → declarative migration policy

Inline pragmas are for one-off cases. Once a file accumulates
**more than two** pragmas of the same rule, the suppression has become
a pattern and belongs in `SERVICE_MAP.yaml exceptions[]` so reviewers
can see it in one place.

The threshold is intentional: one or two pragmas in a file are easy to
spot during review; a dozen scattered through a 400-line file are not.

### Trigger

`> 2` pragmas of the same rule in a single file. Detected by reading
`internal/<file>.go` and grepping for `archspec:ignore` — there is no
automated enforcement on day one, so apply the policy during PR review.

### Migration recipe

1. Identify the rule and the smallest scope that covers all the
   pragmas (a directory, a package, a service component).
2. Write or amend the ADR.
3. Add a single declarative exception with that scope.
4. Remove the inline pragmas in the same commit.

### Before

`internal/legacy/handler.go` (5 pragmas, all `AI-002`):

```go
package legacy

func ProcessOrderV1(ctx context.Context, o Order) error {
    // archspec:ignore AI-002 -- legacy v1 path, removed when v2 is GA
    repo.Save(ctx, o)
    publisher.Publish(ctx, OrderProcessedV1{ID: o.ID})
    return nil
}

func ProcessRefundV1(ctx context.Context, r Refund) error {
    // archspec:ignore AI-002 -- legacy v1 path, removed when v2 is GA
    repo.Save(ctx, r)
    publisher.Publish(ctx, RefundProcessedV1{ID: r.ID})
    return nil
}

func CancelOrderV1(ctx context.Context, id string) error {
    o, err := repo.Load(ctx, id)
    if err != nil {
        return err
    }
    o.Status = "cancelled"
    // archspec:ignore AI-002 -- legacy v1 path, removed when v2 is GA
    repo.Save(ctx, o)
    publisher.Publish(ctx, OrderCancelledV1{ID: id})
    return nil
}

func RetryShipmentV1(ctx context.Context, id string) error {
    s, err := repo.Load(ctx, id)
    if err != nil {
        return err
    }
    // archspec:ignore AI-002 -- legacy v1 path, removed when v2 is GA
    repo.Save(ctx, s)
    publisher.Publish(ctx, ShipmentRetriedV1{ID: id})
    return nil
}

func ArchiveOrderV1(ctx context.Context, id string) error {
    // archspec:ignore AI-002 -- legacy v1 path, removed when v2 is GA
    repo.Save(ctx, Order{ID: id, Archived: true})
    publisher.Publish(ctx, OrderArchivedV1{ID: id})
    return nil
}
```

`SERVICE_MAP.yaml` (no exceptions yet):

```yaml
exceptions: []
```

### After

`internal/legacy/handler.go` (no pragmas — all five removed):

```go
package legacy

func ProcessOrderV1(ctx context.Context, o Order) error {
    repo.Save(ctx, o)
    publisher.Publish(ctx, OrderProcessedV1{ID: o.ID})
    return nil
}

func ProcessRefundV1(ctx context.Context, r Refund) error {
    repo.Save(ctx, r)
    publisher.Publish(ctx, RefundProcessedV1{ID: r.ID})
    return nil
}

func CancelOrderV1(ctx context.Context, id string) error {
    o, err := repo.Load(ctx, id)
    if err != nil {
        return err
    }
    o.Status = "cancelled"
    repo.Save(ctx, o)
    publisher.Publish(ctx, OrderCancelledV1{ID: id})
    return nil
}

func RetryShipmentV1(ctx context.Context, id string) error {
    s, err := repo.Load(ctx, id)
    if err != nil {
        return err
    }
    repo.Save(ctx, s)
    publisher.Publish(ctx, ShipmentRetriedV1{ID: id})
    return nil
}

func ArchiveOrderV1(ctx context.Context, id string) error {
    repo.Save(ctx, Order{ID: id, Archived: true})
    publisher.Publish(ctx, OrderArchivedV1{ID: id})
    return nil
}
```

`SERVICE_MAP.yaml` (one declarative exception covers the whole
package):

```yaml
exceptions:
  - rule: AI-002
    scope:
      path: "internal/legacy/**"
    reason: "legacy v1 publish path; will be removed when v2 GA ships"
    approved_by: "@alice"
    adr: "docs/adr/0051-legacy-v1-publish-path.md"
    expires: "2026-09-30"
```

The diff: minus five inline comments scattered through one file, plus
one structured entry next to the rest of the contract. Reviewers see
the suppression once. The ADR records the v2 GA timeline. `DET-012`
will warn on every commit after `2026-09-30`, prompting either removal
or an extension.

---

## See also

- [`VALIDATION_RULES.md`](./VALIDATION_RULES.md) — full text of every
  rule, including which ones support inline pragmas.
- [`SERVICE_MAP_SPEC.md`](./SERVICE_MAP_SPEC.md) — schema for the
  `exceptions[]` array.
- [`EXTENDING.md`](./EXTENDING.md) — how new linters declare which
  channels they honor.
