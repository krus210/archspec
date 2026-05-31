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

## Output contract

Every run should end with the same shape, so the user can act on it without
guessing what is next:

- **Contract slice** — 5-8 lines citing exact field paths from `docs/SERVICE_MAP.yaml`.
- **Open questions** — only the ambiguity dimensions not already answered by the prompt or contract.
- **Change diagram** — chat-only Mermaid, scoped to the proposed change, with new or changed nodes marked `:::new`.
- **YAML patch** — unified-diff snippet the user can apply before coding; no files are edited by this skill.
- **Event/key fan-out** — from a scan of the full `SERVICE_MAP.yaml` set, the complete list of producers and consumers for each new or changed event and dedup/join key, with each dead-end branch's terminal state + notification; undetermined fan-out marked `# UNCONFIRMED`.
- **Invariant/deviation notes** — explicit callouts when the proposal touches ownership, write path, or declared invariants.
- **Self-review** — one line in the literal shape `Self-review: <N> passes, <findings or "no findings">` recording the loop result (always emitted).
- **Next loop** — `apply YAML edits -> /archspec:sync -> implement -> /archspec:validate -> /archspec:check-architecture` when the change spans services.

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
   | Entry point & ownership | Which service receives the trigger? When the trigger comes from an **external actor**, does the request enter through the public edge (api-gateway / BFF) and not just the internal owner — i.e. is the whole reference flow (client → gateway → owner) wired, not only the last hop? Does an existing endpoint/flow already own this action (a decline/cancel path), and which aggregate owns the state it mutates? Is any identifier in the request payload (e.g. `worker_id`) **trusted** instead of derived from the session/caller identity? | Bolting the trigger onto the wrong service, leaving no public entry point, and trusting client-supplied identity. |
   | Async state & ordering | Does the trigger **read or mutate state that a *different* async path writes** (e.g. it checks `assigned_worker`, which a `match.found` consumer sets)? Can the trigger arrive **before** that write lands, or can a **stale/replayed** copy of that event arrive **after** the trigger and overwrite what it just changed? | Trigger no-ops because the state it depends on isn't there yet; a late or duplicate event resurrects state the trigger just cleared. |
   | Delivery semantics & idempotency | Is the trigger event at-least-once? What is the dedup key, and which side dedups? If the dedup key changes (e.g. `task_id` → `(task_id, attempt)`), is the new key applied to **every** consumer of that event, not just the one you touched? | Duplicate delivery double-counting attempts; a dedup key fixed in one consumer but left stale in another. |
   | Numeric limits & boundaries | Exact meaning of every limit ("max 3 retries" = 3 *after* the first attempt, or 3 total?). | Off-by-one in retry/attempt caps. |
   | Identity & join keys | Which identifiers join entities across services (`city_id` vs free-text city, `task_id` vs `match_id`)? When a lookup can **fail to resolve** (free-text "Saint Petersburg" never maps to a `city_id`), what happens — and is that failure **silent**? | Joining on the wrong field; a lookup that silently degrades the result for every row. |
   | Failure & terminal paths | For **every branch that can dead-end** (limit exhausted, *and* no candidates found, *and* a downstream returns empty), which state transition and which notification happen? Not just the happy path, and not just one terminal. | Silent terminal failures; a dead-end branch that logs-and-returns, leaving the aggregate stuck. |
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

7. **Trace every new or changed event and key across *all* producers and consumers.** Step 2 let you read only the slice that matters; this step is the exception — you must **scan the full `SERVICE_MAP.yaml` set** (every service's contract in the monorepo), because the "dedup fixed in one consumer but missed in another" class is invisible from a single slice. Operationally, for each event you add or change and each dedup / idempotency / join key you change:

   - Grep/scan **every** contract for `events.published`, `events.consumed`, and the topic/event name, plus any `idempotency` / dedup / join-key field that references it.
   - **Producers** — who emits it, and through which write path.
   - **Consumers** — *every* subscriber found by the scan, and for each: does it dedup on the (possibly new) key? does it order-depend on another event? does it even have a handler for this event, or does it silently drop it?
   - **Dead-ends** — branches where processing stops (no candidates, empty result, exhausted limit). Each must end in a state transition **and** the notification the terminal-path dimension demands.

   If the fan-out cannot be fully determined from the contracts (a consumer's dedup key is undocumented, a topic's subscriber set is unclear), it is **not** a free pass — raise it as an open question and mark the affected YAML lines `# UNCONFIRMED` rather than assuming the fan-out is complete.

   **A single event must not carry two unrelated semantic roles.** One `task.reassignment_requested` used both as the matching trigger *and* as a "we are reassigning" client notification fires the notification *before* a new worker is actually found — that is prohibited, not merely discouraged. Either propose **separate events** (one trigger, one notification emitted only after the outcome is known) or, if you cannot resolve the split yourself, **block the YAML patch** and surface it as an open question. Do not ship a single dual-role event with only a warning attached.

8. **Flag invariants the user must preserve**, citing `service.invariants` and `consistency.cross_service_invariants`.

9. **Self-review loop — turn the checklist on your own draft, not just the prompt.** The clarify gate (step 3) interrogates the *requirements*; this step interrogates the *design you just drew*. Re-read your own diagram and YAML and walk the checklist again, plus the anti-pattern list below. Loop until a full pass surfaces nothing new — the first pass routinely does.

   Anti-patterns to hunt in your own proposal:

   - A state read in the trigger that races an async write (Async state & ordering): does the trigger rely on a field (e.g. `assigned_worker`) that arrives via a *separate* event consumer, and can the two reorder?
   - A changed dedup / join key applied to one consumer but not its siblings (Delivery semantics): did the new `(task_id, attempt)` key reach *every* handler of that event, including the one in the owning service?
   - A dead-end branch that logs-and-returns with no state transition or notification (Failure & terminal paths): what marks the entity terminal when the pipeline finds **no** candidates?
   - A fallback that silently changes the result (Identity & join keys): does an unresolved lookup quietly collapse every value to a default (e.g. `maxDistance`), killing a tie-breaker with no signal?
   - One event with two semantic consumers where one is a client notification fired before the outcome is known (step 7).
   - An external trigger with no public-edge entry point, or one that trusts a client-supplied identity (Entry point & ownership).

   Record the outcome as a one-line note in the output using the literal prefix and shape `Self-review: <N> passes, <what was found and fixed, or "no findings">` — e.g. `Self-review: 2 passes, found+fixed premature client notify and a stale dedup key; no remaining findings`. Always emit this line, even on a clean first pass (`Self-review: 1 pass, no findings`). If a finding can't be resolved without the user, raise it as a new open question rather than shipping it.

10. **End with the full loop, not just sync.** The contract is only safe if code is checked back against it. Spell out the path: apply the YAML edits → `/archspec:sync` → implement → `/archspec:validate` (runs the behavioural linters — outbox, idempotency, optimistic-locking) → `/archspec:check-architecture` for any change that spans more than one service. A green build or passing unit tests is **not** a substitute for `/archspec:validate`: those tests usually cover only the happy path that was just written.

## Do not

- Modify any file. This skill is read-only.
- Skip the clarify gate (step 3) because "the prompt looks clear". Cross-service prompts that look clear are exactly where ownership and idempotency get assumed wrong.
- Skip the self-review loop (step 9) because the draft "looks complete". The bugs that survive the clarify gate live in the design you just drew — async races, a dedup key fixed in only one consumer, a dead-end branch, an event doing two jobs.
- Invent answers to the clarify checklist and write them into the YAML as if decided.
- Run /archspec:validate here — that is a separate command for after the code change.
- Read code that is unrelated to the user's question. Stay scoped to the contract.
