---
name: architecture-investigate
description: Use before non-trivial feature or bugfix work — phrases like "let's add X", "investigate Y", "understand how Z works", or when the user runs /archspec:investigate. Read-only: consults SERVICE_MAP.yaml, asks clarifying questions about ambiguous requirements, then proposes a change plan + chat-only Mermaid.
---

# architecture-investigate

Read-side workflow. Never modifies files. Produces:

1. A short summary of the relevant slice of `SERVICE_MAP.yaml`.
2. Clarifying questions for every ambiguity the prompt and the contract do not already settle.
3. An inline Mermaid diagram showing **only the change** the user is proposing.
4. A bulleted list of YAML edits the user should make before writing code.

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

3. **Clarify ambiguities before proposing anything (gate)**. A feature prompt is almost never complete enough to design a cross-service change. Walk the checklist below and, for every dimension the prompt and `SERVICE_MAP.yaml` do **not** already answer unambiguously, ask the user with `AskUserQuestion` (batch the questions into as few calls as possible). Asking is read-only — it modifies nothing.

   | Dimension | What to pin down | Failure it prevents |
   | --- | --- | --- |
   | Entry point & ownership | Which service receives the trigger? Does an existing endpoint/flow already own this action (a decline/cancel path), and which aggregate owns the state it mutates? Is any identifier in the request payload (e.g. `worker_id`) trusted instead of derived from the session/owner? | Bolting the trigger onto the wrong service and bypassing ownership/auth. |
   | Delivery semantics & idempotency | Is the trigger event at-least-once? What is the dedup key, and which side dedups? | Duplicate delivery double-counting attempts or emitting duplicate downstream events. |
   | Numeric limits & boundaries | Exact meaning of every limit ("max 3 retries" = 3 *after* the first attempt, or 3 total?). | Off-by-one in retry/attempt caps. |
   | Identity & join keys | Which identifiers join entities across services (`city_id` vs free-text city, `task_id` vs `match_id`)? | Joining on the wrong field; geo/lookup mismatches. |
   | Failure & terminal paths | What state and which notification happen when the whole flow finally fails — not just the happy path? | Silent terminal failures; the client is never told. |
   | Write-path conformance | Must the new publish/persist go through this service's `consistency.write_path.pattern` (e.g. `outbox`)? May the publish error be swallowed? | Publishing straight to the broker outside the outbox; returning success after a swallowed error. |

   Rules:

   - Skip a dimension **only** when the contract already answers it — quote the field that does.
   - **Never invent an answer and bake it into the proposed YAML.** A guessed dedup key or ownership boundary in the contract is worse than an open question: it looks decided.
   - If the user is unavailable, list the open questions explicitly in the output and mark the affected YAML lines `# UNCONFIRMED` instead of asserting them.

4. **Summarise** what the contract says, in 5–8 lines. Quote field paths (e.g. `consistency.write_path.pattern: outbox`) so the user can verify.

5. **Draw a chat-only Mermaid diagram of the proposed change**. Embed it in the response — do **not** write to disk. Highlight new/changed nodes with a `:::new` class:

   ```mermaid
   flowchart LR
     classDef new stroke:#0a0,stroke-width:2px;
     svc[listing-service]
     newEp[POST /listings/bulk]:::new
     newEp --> svc
     svc --> kafka>listings.created v1]
   ```

6. **Propose YAML edits** as a unified-diff snippet. Don't apply them — let the user accept, tweak, then run /archspec:sync. Example shape:

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

   **Deviation guard**: when an edit crosses an existing boundary — changes who owns an action, adds a publish that sidesteps `consistency.write_path.pattern`, or relaxes an entry in `service.invariants` / `consistency.cross_service_invariants` — call it out in one line ("this deviates from `<field>`: `<why>`") and get explicit confirmation. A generated contract line must not silently ratify a design the user never affirmed.

7. **Flag invariants the user must preserve**, citing `service.invariants` and `consistency.cross_service_invariants`.

8. **End with the full loop, not just sync.** The contract is only safe if code is checked back against it. Spell out the path: apply the YAML edits → `/archspec:sync` → implement → `/archspec:validate` (runs the behavioural linters — outbox, idempotency, optimistic-locking) → `/archspec:check-architecture` for any change that spans more than one service. A green build or passing unit tests is **not** a substitute for `/archspec:validate`: those tests usually cover only the happy path that was just written.

## Do not

- Modify any file. This skill is read-only.
- Skip the clarify gate (step 3) because "the prompt looks clear". Cross-service prompts that look clear are exactly where ownership and idempotency get assumed wrong.
- Invent answers to the clarify checklist and write them into the YAML as if decided.
- Run /archspec:validate here — that is a separate command for after the code change.
- Read code that is unrelated to the user's question. Stay scoped to the contract.
