---
name: architecture-investigate
description: Use before non-trivial feature or bugfix work — phrases like "let's add X", "investigate Y", "understand how Z works", or when the user runs /archspec:investigate. Read-only: consults SERVICE_MAP.yaml and proposes change plan + chat-only Mermaid.
---

# architecture-investigate

Read-side workflow. Never modifies files. Produces:

1. A short summary of the relevant slice of `SERVICE_MAP.yaml`.
2. An inline Mermaid diagram showing **only the change** the user is proposing.
3. A bulleted list of YAML edits the user should make before writing code.

## When to run

- User asks "let's add X", "investigate Y", "how does Z work?".
- Before any new feature or bugfix that touches an endpoint, dependency, event, or aggregate.
- User typed `/archspec:investigate`.

## Procedure

1. **Locate the contract**:

   ```bash
   test -f docs/SERVICE_MAP.yaml || echo "no SERVICE_MAP.yaml — run /archspec:init"
   ```

   If missing, stop and tell the user.

2. **Read the slice that matters**. Use the Read tool on `docs/SERVICE_MAP.yaml`. Identify which sections relate to the user's question:

   | User mention | Relevant sections |
   | --- | --- |
   | endpoint, route, handler | `api.endpoints`, `architecture_rules.required_layers` |
   | call, dependency, downstream | `dependencies.downstream`, `dependencies.storage` |
   | event, kafka, topic | `events.published`, `events.consumed`, `consistency.write_path` |
   | aggregate, lock, conflict | `concurrency.aggregates`, `consistency.bounded_aggregate` |
   | retry, fallback, failure | `dependencies.downstream.sync.*.fallback`, `failure_modes` |

3. **Summarise** what the contract says, in 5–8 lines. Quote field paths (e.g. `consistency.write_path.pattern: outbox`) so the user can verify.

4. **Draw a chat-only Mermaid diagram of the proposed change**. Embed it in the response — do **not** write to disk. Highlight new/changed nodes with a `:::new` class:

   ```mermaid
   flowchart LR
     classDef new stroke:#0a0,stroke-width:2px;
     svc[listing-service]
     newEp[POST /listings/bulk]:::new
     newEp --> svc
     svc --> kafka>listings.created v1]
   ```

5. **Propose YAML edits** as a unified-diff snippet. Don't apply them — let the user accept, tweak, then run /archspec:sync. Example shape:

   ```diff
   api:
     endpoints:
   +   - name: BulkCreateListings
   +     protocol: HTTP
   +     idempotency:
   +       required: true
   +       key_source: "header: X-Idempotency-Key"
   +       storage: "redis: idemp:{key}"
   +     contract: "api/openapi.yaml#/paths/~1listings~1bulk/post"
   +     sla: { p99_latency: "300ms", availability: "99.9%" }
   ```

6. **Flag invariants the user must preserve**, citing `service.invariants` and `consistency.cross_service_invariants`.

7. **End with a one-line next step**: e.g. `apply the YAML edits, then /archspec:sync`.

## Do not

- Modify any file. This skill is read-only.
- Run /archspec:validate here — that is a separate command for after the code change.
- Read code that is unrelated to the user's question. Stay scoped to the contract.
