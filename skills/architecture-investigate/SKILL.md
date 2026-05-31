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
- **Reference cross-check** — when a reference/golden architecture spec was supplied, a short note on where the proposed event names, RPC names, dedup keys, and invariants agree with or deviate from it. Deviations are called out, never silently renamed away.
- **Open questions** — only the ambiguity dimensions not already answered by the prompt or contract.
- **Change diagram** — chat-only Mermaid, scoped to the proposed change, with new or changed nodes marked `:::new`.
- **YAML patch** — unified-diff snippet the user can apply before coding; no files are edited by this skill.
- **Event/key fan-out** — from a scan of the full `SERVICE_MAP.yaml` set, the complete list of producers and consumers for each new or changed event and dedup/join key, with each dead-end branch's terminal state + notification; undetermined fan-out marked `# UNCONFIRMED`.
- **Invariant/deviation notes** — explicit callouts when the proposal touches ownership, write path, or declared invariants.
- **Risk register (`edge_cases`)** — every gap, deviation, `# UNCONFIRMED`, and join-key risk surfaced above, restated as a concrete `edge_cases[]` entry inside the YAML patch (`id` + a `description` that carries the given/when/then + a `test:` path). This is the bridge that carries a finding into code: a sentence in chat is forgotten the moment the plan step takes over, but an `edge_cases[]` entry persists in the contract and DET-003 blocks the commit until its test file exists.
- **Self-review** — one line in the literal shape `Self-review: <N> pass(es), <findings or "no findings">` recording the loop result (always emitted).
- **Definition of done** — an explicit checklist stating that the change is *not* done on a green build: it is done only when `/archspec:validate` (and, for cross-service work, `/archspec:check-architecture`) is green and every `edge_cases[]` entry added above has a test that exercises it.
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

2a. **Optional: ingest a reference / golden architecture spec.** A feature prompt rarely states the naming conventions or the out-of-prompt invariants the team already expects (e.g. "reassignment reuses the initial match snapshot — do not re-run the search"; the canonical subject is `offer.declined`, not a freshly invented `task.offer_rejected`). Ask the user **once** with `AskUserQuestion`:

   > "Is there a reference / golden architecture spec for this change — a design doc, an RFC, a target-state diagram, a naming convention? Paste a path, or answer `skip`."

   - **Path provided** — Read it and keep it as conversation context only (do not parse it into the contract). Use it to cross-check the design you are about to draw: event/topic names, RPC names, dedup/idempotency keys, and the invariants it mandates. When your proposal diverges from the reference, **name the divergence** in the Reference cross-check note — never silently rename `offer.declined` → `task.offer_rejected` or quietly drop an invariant the spec requires. The spec is a hint, never an override: if it contradicts the live `SERVICE_MAP.yaml` or the code, prefer reality and say so.
   - **`skip` / none** — proceed, and note in the output that no reference spec was supplied, so naming and any out-of-prompt invariants were inferred from the contract alone (a known blind spot — the prompt cannot be assumed complete).

3. **Clarify ambiguities before proposing anything (gate)**. A feature prompt is almost never complete enough to design a cross-service change. Walk the checklist below and, for every dimension the prompt and `SERVICE_MAP.yaml` do **not** already answer unambiguously, ask the user with `AskUserQuestion` (batch the questions into as few calls as possible). Asking is read-only — it modifies nothing.

   | Dimension | What to pin down | Failure it prevents |
   | --- | --- | --- |
   | Entry point & ownership | Which service receives the trigger? When the trigger comes from an **external actor**, does the request enter through the public edge (api-gateway / BFF) and not just the internal owner — i.e. is the whole reference flow (client → gateway → owner) wired, not only the last hop? Does an existing endpoint/flow already own this action (a decline/cancel path), and which aggregate owns the state it mutates? | Bolting the trigger onto the wrong service, or leaving no public entry point. |
   | Trusted identity & actor | Separate sub-question — do **not** consider it answered just because the entry point is settled. Is any identifier in the request payload (e.g. `worker_id`, `user_id`, `account_id`) used as the **actor's identity** instead of being derived from the authenticated session/caller? Whoever the action runs *as* must come from the caller's credentials, not the body. If the source is unproven, mark the field `# UNCONFIRMED: trusted from client` and ask. | A client spoofing another actor by passing their id in the request body (declining an offer on behalf of any worker). |
   | Async state & ordering | Does the trigger **read or mutate state that a *different* async path writes** (e.g. it checks `assigned_worker`, which a `match.found` consumer sets)? Can the trigger arrive **before** that write lands, or can a **stale/replayed** copy of that event arrive **after** the trigger and overwrite what it just changed? | Trigger no-ops because the state it depends on isn't there yet; a late or duplicate event resurrects state the trigger just cleared. |
   | Delivery semantics & idempotency | Is the trigger event at-least-once? What is the dedup key, and which side dedups? If the dedup key changes (e.g. `task_id` → `(task_id, attempt)`), is the new key applied to **every** consumer of that event, not just the one you touched? | Duplicate delivery double-counting attempts; a dedup key fixed in one consumer but left stale in another. |
   | Numeric limits & boundaries | Exact meaning of every limit ("max 3 retries" = 3 *after* the first attempt, or 3 total?). | Off-by-one in retry/attempt caps. |
   | Identity & join keys | Which identifiers join entities across services (`city_id` vs free-text city, `task_id` vs `match_id`)? When a lookup can **fail to resolve** (free-text "Saint Petersburg" never maps to a `city_id`), what happens — and is that failure **silent**? | Joining on the wrong field; a lookup that silently degrades the result for every row. |
   | Failure & terminal paths | For **every branch that can dead-end** (limit exhausted, *and* no candidates found, *and* a downstream returns empty), which state transition and which notification happen? Not just the happy path, and not just one terminal. | Silent terminal failures; a dead-end branch that logs-and-returns, leaving the aggregate stuck. |
   | Write-path conformance | Must the new publish/persist go through this service's `consistency.write_path.pattern` (e.g. `outbox`)? May the publish error be swallowed? | Publishing straight to the broker outside the outbox; returning success after a swallowed error. |

   Rules:

   - **Treat every sub-question inside a dimension as its own checkbox.** Answering the entry-point half ("it enters via api-gateway") does **not** discharge the identity-trust half ("but where does `worker_id` come from?"). A dimension is cleared only when *every* clause in it is answered or quoted from the contract — a dimension that bundles two questions is the most common place one half gets silently skipped.
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

8a. **Materialise every risk as an `edge_cases[]` entry — the investigate→code bridge.** This is the step that stops a finding from dying as chat prose. The strongest investigate output is worthless if it never reaches the code: an agent that writes the plan next, then dispatches implementation subagents, does **not** re-read this chat — it reads the contract. So for **each** gap, deviation, `# UNCONFIRMED`, join-key risk, and dead-end terminal you surfaced in steps 3–8, add a concrete `edge_cases[]` entry to the YAML patch:

   ```yaml
   edge_cases:
     - id: EC-014
       description: "worker city joins to geo by city_id, not free-text city_name; an unresolved city_id must fail loudly, never silently collapse the distance tie-breaker to a default"
       test: "services/matching-service/usecase/matching_geo_test.go::TestEC014"
   ```

   Why an `edge_cases[]` entry works where prose does not:

   - It **persists in the contract** and renders into `ARCHITECTURE.md`, so the plan-writer and the implementation subagents see it without the chat history.
   - The `test:` path is enforced by **DET-003** at commit time — the commit is **blocked** until that test file exists. A risk you cannot yet test is a risk you must at least name.
   - Deleting it later trips **DET-007** (no edge_case removal without an ADR), so the guard cannot be quietly dropped during implementation.

   Schema is closed — exactly three fields: `id` matches `^EC-\d+$` (use the next free `EC-NNN`); `description` is one line carrying the given/when/then; `test` is a `path::TestName` reference. The single highest-value entry is usually a **join-key** risk (the field a lookup resolves on) or a **reuse-vs-recompute** invariant (a snapshot that must not be recomputed) — exactly the findings that read as obvious in chat and then vanish. If a risk genuinely cannot be expressed as a test, it stays an **open question**, not a silent omission.

9. **Self-review loop — turn the checklist on your own draft, not just the prompt.** The clarify gate (step 3) interrogates the *requirements*; this step interrogates the *design you just drew*. Re-read your own diagram and YAML and walk the checklist again, plus the anti-pattern list below. Loop until a full pass surfaces nothing new — the first pass routinely does.

   Anti-patterns to hunt in your own proposal:

   - A state read in the trigger that races an async write (Async state & ordering): does the trigger rely on a field (e.g. `assigned_worker`) that arrives via a *separate* event consumer, and can the two reorder?
   - A changed dedup / join key applied to one consumer but not its siblings (Delivery semantics): did the new `(task_id, attempt)` key reach *every* handler of that event, including the one in the owning service?
   - A dead-end branch that logs-and-returns with no state transition or notification (Failure & terminal paths): what marks the entity terminal when the pipeline finds **no** candidates?
   - A fallback that silently changes the result (Identity & join keys): does an unresolved lookup quietly collapse every value to a default (e.g. `maxDistance`), killing a tie-breaker with no signal?
   - One event with two semantic consumers where one is a client notification fired before the outcome is known (step 7).
   - An external trigger with no public-edge entry point, or one that trusts a client-supplied identity (Entry point & ownership / Trusted identity & actor).
   - **Recompute instead of reuse** in a retry/reassignment loop: does the loop re-run an expensive or non-deterministic pipeline (a text analysis, a candidate search) on every attempt, when the result should be **snapshotted on the first attempt** and reused? Re-running both wastes the downstream call *and* lets the candidate set drift between attempts.
   - **Attempt/version identity reconstructed from consumer memory**: does a consumer infer "which attempt is this" from its own in-memory state instead of reading it from the **event payload**? On restart or replay that state is gone and a stale event re-triggers the flow. The attempt/version must travel *in* the durable event.
   - **Two events from one handler that must be consistent but are appended separately**: when a handler emits two events that must both land or neither (a worker offer *and* a client "you were reassigned" notice), are they written in the **same outbox transaction**, or can a crash between the two appends deliver one without the other?
   - **State transition and its notification not atomic**: does a terminal notification ("task failed") fire even when the state transition it announces (`FailTask`) failed or was swallowed? The notification must be gated on the transition actually committing.
   - **Terminal-state invariant narrower than the real input states**: is a transition guard (e.g. "fail only from `open`") tighter than the states the entity can actually be in when the branch fires (it may be `assigned` by then), so the terminal silently no-ops?
   - **A dead-end on the *first* attempt, not just the last**: the first hop can also dead-end (the initial match finds **no** candidates). Does that first-attempt empty result transition the entity to a terminal state and notify, or does it log-and-return and leave the entity stuck?
   - **A finding left as prose with no `edge_cases[]` entry** (step 8a): did every gap / deviation / `# UNCONFIRMED` / join-key risk become a testable `edge_cases[]` entry or an explicit open question, or is one still sitting in the narrative where the plan step will scroll past it?

   Record the outcome as a one-line note in the output using the literal prefix and shape `Self-review: <N> pass(es), <what was found and fixed, or "no findings">` — write the count grammatically (`1 pass`, `2 passes`). E.g. `Self-review: 2 passes, found+fixed premature client notify and a stale dedup key; no remaining findings`. Always emit this line, even on a clean first pass (`Self-review: 1 pass, no findings`). If a finding can't be resolved without the user, raise it as a new open question rather than shipping it.

10. **End with the full loop, not just sync.** The contract is only safe if code is checked back against it. Spell out the path: apply the YAML edits → `/archspec:sync` → implement → `/archspec:validate` (runs the behavioural linters — outbox, idempotency, optimistic-locking) → `/archspec:check-architecture` for any change that spans more than one service. A green build or passing unit tests is **not** a substitute for `/archspec:validate`: those tests usually cover only the happy path that was just written.

   Spell out the **Definition of done** as a literal checklist, because the agent that closes the branch is often a separate `finishing-a-development-branch` pass that knows nothing about archspec and will otherwise stop at green unit tests:

   - [ ] every `edge_cases[]` entry added in step 8a has a test that actually exercises it (not merely a file that exists);
   - [ ] `/archspec:validate` is green, or every finding has an `exceptions[]` entry with a reason;
   - [ ] `/archspec:check-architecture` is green for cross-service changes;
   - [ ] every `# UNCONFIRMED` marker is now resolved, or carried into an `edge_cases[]` entry or an ADR.

   A green `go build` / `go test` clears **none** of these boxes.

## Do not

- Modify any file. This skill is read-only.
- Skip the clarify gate (step 3) because "the prompt looks clear". Cross-service prompts that look clear are exactly where ownership and idempotency get assumed wrong.
- Skip the self-review loop (step 9) because the draft "looks complete". The bugs that survive the clarify gate live in the design you just drew — async races, a dedup key fixed in only one consumer, a dead-end branch, an event doing two jobs.
- Invent answers to the clarify checklist and write them into the YAML as if decided.
- Let a finding live only as chat prose. Every gap, deviation, `# UNCONFIRMED`, and join-key risk must become an `edge_cases[]` entry (step 8a) or an explicit open question — never a sentence the plan step will scroll past.
- Silently rename an event/RPC or drop an invariant that a supplied reference spec mandates. Name the divergence (step 2a) and let the user decide.
- Run /archspec:validate here — that is a separate command for after the code change.
- Read code that is unrelated to the user's question. Stay scoped to the contract.
