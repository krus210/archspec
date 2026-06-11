---
name: architecture-implement
description: Use when an .archplan.md artifact exists and the user wants the change built — "implement the plan", "build it", or /archspec:implement. Applies the archplan's contract edits, syncs generated docs, writes a coding plan that provably maps to the archplan, implements with TDD, then runs conformance passes + /archspec:validate + /archspec:check-architecture until no BLOCK remains.
---

# architecture-implement

Write-side counterpart of `architecture-investigate`. The archplan artifact is the
**binding contract**: every phase below either derives from it or checks against it.
This skill exists because a green build is not conformance — task_3 shipped a
nil-wired gateway, a declared event with no emit site, a field that never reached the
public edge, and dedup marked before its side effects, all with green unit tests.

Builds on superpowers: `superpowers:writing-plans` for the coding plan,
`superpowers:subagent-driven-development` or `superpowers:executing-plans` for
execution, `superpowers:test-driven-development` per task.

## Phase A — Locate the archplan (gate)

1. Resolve the artifact: the argument, or the newest `docs/plans/*.archplan.md`.
2. **No artifact → refuse.** Tell the user to run `/archspec:investigate` first. Do not
   improvise an architectural plan here: an unreviewed plan is how the task_3 topology
   silently flipped from outbox events to sync RPC.
3. Read the artifact fully. Extract: the YAML patch, the sequence diagram, the
   `edge_cases[]` register, the state-ownership map, the fan-out trace, and the open
   questions. Unresolved open questions that block coding → ask the user now.

## Phase B — Contracts first

1. Apply the archplan's YAML patch to every touched `docs/SERVICE_MAP.yaml` (one per
   service in a monorepo — `cd` into each service directory).
2. Validate each edited contract:

   ```bash
   ARCHSPEC_ROOT="${CLAUDE_PLUGIN_ROOT:-$CLAUDE_PROJECT_DIR}"
   $ARCHSPEC_ROOT/bin/archspec-python \
     $ARCHSPEC_ROOT/skills/architecture-sync/scripts/validate_servicemap.py docs/SERVICE_MAP.yaml
   ```

3. Run `/archspec:sync` in each touched service directory so `docs/diagrams/*.mmd` and
   the managed region of `docs/ARCHITECTURE.md` are regenerated **before** code is
   written — the diagrams must describe the target state, not trail it.
4. Commit the contract change separately: `docs(archspec): contract edits for <slug>`.

## Phase C — Coding plan with a conformance table

Write the coding plan with `superpowers:writing-plans`, saved next to the archplan as
`docs/plans/<date>-<slug>.codingplan.md`. Two extra obligations beyond that skill:

1. **Conformance table** — a table with one row per archplan element: every event,
   endpoint, field, batch call, dedup key, and `edge_cases[]` entry, mapped to the
   coding task that realises it and the test that proves it. An archplan element with
   no row is a missing task; a coding task with no archplan element is scope creep —
   resolve both before coding.
2. **Method-existence gate** — for every downstream call the plan makes, verify the
   method exists in the callee's contract/proto **now**, by grep, not by plausibility:

   ```bash
   grep -rn "GetWorkersBatch" proto/ */docs/SERVICE_MAP.yaml
   ```

   A method that does not exist in the callee is forbidden — `SearchBySkills` in task_3
   was invented at this exact point. Either use the method the contract declares, or go
   back to investigate and change the contract explicitly.

## Phase D — Implement

Execute the coding plan task-by-task (`superpowers:subagent-driven-development` when
subagents are available, else `superpowers:executing-plans`), with
`superpowers:test-driven-development` per task. Frequent commits. Every `edge_cases[]`
entry gets the test its `test:` path names — exercising the behaviour, not just
creating the file.

## Phase E — Conformance passes (the bug-class killers)

Run each pass over the full diff. Each one targets a bug class that shipped in task_3
with green tests. Record the evidence inline; a pass with no evidence is not done.

1. **Wiring pass — no nil dependencies, no wrong addresses.** Open every touched
   composition root (`main.go` / DI container). Every constructor argument for a
   declared dependency is a real client, never `nil` / a placeholder. Then verify every
   new client's **default address/port against the target service's actual listen
   port** (its `main.go` / deploy config) — a geo client defaulting to another
   service's port compiles, passes unit tests, and dials the wrong service in every
   real environment. Unit tests stub these, so only this pass catches both.
2. **Emission pass — every declared event has an emit site.** For each
   `events.published[]` entry in every touched contract, grep the service code for the
   topic string and confirm a publish/outbox append on **every** path the archplan
   shows it on (initial *and* retry/reassignment paths — task_3 published `match.found`
   only on the initial path).
3. **Threading pass — every new field reaches the public edge, end-to-end.** For each
   field added to a model/proto: public entry (gateway proto, HTTP body), the owner's
   write path, every event payload that carries it, every consumer that reads it, and
   the **seed/fixture data** — a field the seeds never populate is dead in every demo
   and test environment. For each new public route: the path declared in the contract
   must match the router registration **string-for-string** (`/decline-offer` declared
   but only `/decline` routed is a documented endpoint that 404s); prove it with a
   handler test that hits the documented path.
4. **Dedup pass — marking is atomic with or after the side effects, never before the
   side effects.** Trace each consumer: if the dedup key is recorded first and a later
   step fails, redelivery is silently swallowed (at-least-once degrades to
   at-most-once). Require CAS/outbox-style "mark completed with the result", or
   marking after the effects. Then trace a **literal second-attempt event** (the
   reassignment/retry copy, not a duplicate) through every consumer's dedup logic: an
   identifier reused across attempts (a match id) with a consumer deduping on that ID
   swallows the retry as a "duplicate" — the ID must be regenerated per attempt or the
   key must include the attempt, in **every** consumer.
5. **Evidence pass — requirement → file:line.** Re-read the original task. For every
   stated requirement, write one line: requirement → `file:line` that implements it →
   test that proves it. A requirement you cannot point into the diff is unimplemented,
   however much surrounding code exists (task_3: "rating is the primary sort" had no
   file:line — it was simply not there).

## Phase F — archspec validation gates

1. Run `/archspec:validate` from the repo root (monorepo-aware: it discovers every
   `*/docs/SERVICE_MAP.yaml` and lints each service).
2. Run `/archspec:check-architecture` for any cross-service change.
3. Fix every BLOCK and re-run until clean; WARNs are fixed or get an explicit
   `exceptions[]` entry with a reason. Findings are never waved off as stale.

## Phase G — Independent final review

Dispatch a reviewer subagent with a **fresh context** (no chat history). Give it: the
archplan path, the coding plan path, and the branch diff (`git diff <base>...HEAD`).
It re-runs Phase E's five passes against the diff plus the archplan's rubric (topology,
batch usage, snapshot reuse, terminal branches) and returns CRITICAL/MAJOR/MINOR
findings with file:line. Fix every CRITICAL and MAJOR, then re-dispatch a fresh
reviewer. Loop until zero CRITICAL findings. Emit the literal line
`Implement-review: CLEAN after <N> round(s), <summary>`.

**Solo degradation is not CLEAN.** If you cannot dispatch subagents, re-reading your
own diff is not an independent review — walk the passes anyway, but emit
`Implement-review: SELF-ONLY after <N> pass(es), <summary>` so the degradation stays
visible to the human and to any later review stage.

## Phase H — Finish

Commit the remaining work in logical commits. **Do not push** and do not open a PR
unless the user explicitly asks. Close with the Definition of done from the archplan,
each box checked with its evidence:

- [ ] every `edge_cases[]` entry has a test that actually exercises it;
- [ ] `/archspec:validate` green (or explicit `exceptions[]`);
- [ ] `/archspec:check-architecture` green for cross-service changes;
- [ ] conformance table fully realised — no archplan element without code+test;
- [ ] `Implement-review: CLEAN` emitted.

## Do not

- Start without an `.archplan.md` artifact — run `/archspec:investigate` first.
- Call a method that does not exist in the callee's contract/proto, however plausible
  the name. The contract decides, not the plan's prose.
- Pass `nil` (or a stub) as a declared dependency in a composition root "to wire it
  later". Later never comes; the first real event panics.
- Re-run an expensive pipeline that the archplan says to snapshot and reuse.
- Mark a dedup key before the side effects it guards.
- Treat green `go build` / `go test` as done — only Phase F/G gates close the work.
- Push, tag, or open a PR without the user's explicit request.
