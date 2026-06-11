from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS = ROOT / "skills"

EXPECTED = ["architecture-sync", "architecture-investigate", "architecture-implement"]


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    out = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_each_skill_has_skill_md_with_frontmatter():
    for name in EXPECTED:
        path = SKILLS / name / "SKILL.md"
        assert path.is_file(), f"missing SKILL.md for {name}"
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        assert fm.get("name") == name, f"{name}: frontmatter name mismatch"
        assert fm.get("description"), f"{name}: missing description"
        # description should mention the trigger phrases or the slash command
        desc = fm["description"].lower()
        assert any(s in desc for s in ("/archspec:", "use when", "regenerates", "read-only"))


def test_architecture_sync_skill_references_all_scripts():
    text = (SKILLS / "architecture-sync" / "SKILL.md").read_text(encoding="utf-8")
    for script in ("validate_servicemap.py", "sync.py", "validate_mermaid.py"):
        assert script in text, f"architecture-sync SKILL.md does not reference {script}"


def test_architecture_investigate_skill_is_read_only():
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "read-only" in text or "do not" in text
    # Belt-and-braces: the skill must NOT mention sync.py / git add — those would be writes.
    assert "git add" not in text
    assert "sync.py" not in text


def test_investigate_has_clarify_gate():
    """investigate must force clarifying questions on ambiguous requirements.

    Regression guard for the failure mode where the skill jumped straight to
    proposing YAML edits without interrogating ownership / idempotency / limits.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "clarif" in text or "ambiguit" in text, "investigate must have a clarify/ambiguity gate"
    assert "askuserquestion" in text, "the clarify gate should use AskUserQuestion to ask the user"
    for dimension in ("ownership", "idempotency", "write-path"):
        assert dimension in text, f"clarify checklist should cover the '{dimension}' dimension"


def test_investigate_covers_async_ordering_and_fanout():
    """investigate must interrogate async/causal ordering and trace every

    changed event/key across all consumers. Regression guard for the failure
    modes where the skill modeled only the prompt's happy path and missed: a
    trigger that races an async write, a dedup key fixed in only one consumer,
    and a dead-end branch with no terminal state.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "async state & ordering" in low, (
        "clarify checklist should have an 'Async state & ordering' dimension"
    )
    assert "reorder" in low, (
        "async dimension should ask whether trigger and async write can reorder"
    )
    assert "producers" in low and "consumers" in low, (
        "investigate should trace every changed event/key across all producers and consumers"
    )
    assert "dead-end" in low, "investigate should force a terminal path for every dead-end branch"


def test_investigate_fanout_scans_full_contract_set():
    """The fan-out trace must scan the WHOLE SERVICE_MAP.yaml set, not just the

    slice from step 2 — otherwise a dedup key fixed in one consumer but missed
    in a sibling consumer stays invisible. Undetermined fan-out must escalate to
    an open question / # UNCONFIRMED, not be assumed complete.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "full" in low and "service_map.yaml" in low, (
        "step 7 should require scanning the full SERVICE_MAP.yaml set"
    )
    assert "events.published" in low and "events.consumed" in low, (
        "step 7 should scan events.published / events.consumed across contracts"
    )
    assert "# unconfirmed" in low, (
        "undetermined fan-out should be marked # UNCONFIRMED, not assumed complete"
    )


def test_investigate_prohibits_dual_role_event():
    """A single event carrying two semantic roles (trigger + premature client

    notification) is prohibited, not merely flagged. The skill must require
    separate events or block the YAML patch.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "must not carry two" in low or "prohibited" in low, (
        "dual-role events must be prohibited, not just discouraged"
    )
    assert "separate events" in low, (
        "the fix for a dual-role event is to split into separate events"
    )
    assert "block the yaml patch" in low, (
        "an unresolvable dual-role event must block the YAML patch, not ship with a warning"
    )


def test_investigate_has_self_review_loop():
    """investigate must re-run its checklist against its own drafted design, not

    just the prompt. Regression guard for architectural details that survive the
    clarify gate but live in the proposal itself (one event serving two semantic
    purposes, a silently degrading fallback, an async race).
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "self-review loop" in low, "investigate should run a self-review loop on its own draft"
    assert "anti-pattern" in low, "the self-review loop should hunt named anti-patterns"
    # the loop must be scoped to the skill's OWN draft (diagram + YAML), not the prompt
    assert "diagram and yaml" in low or "diagram + yaml" in low, (
        "the self-review loop must re-examine the drafted diagram and YAML, not just the prompt"
    )
    # the output note must follow the literal pinned shape, not a freeform sentence.
    # pass(es) keeps singular/plural grammatical while a strict validator can use pass(es)?
    assert "Self-review: <N> pass(es)" in text, (
        "the self-review output note must use the literal 'Self-review: <N> pass(es), ...' shape"
    )


def test_investigate_points_to_validation_gate():
    """investigate must wire the post-implementation validation gate into its
    closing next step so the behavioural linters actually run."""
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "/archspec:validate" in text, (
        "investigate should point to /archspec:validate after implementing"
    )
    assert "/archspec:check-architecture" in text, (
        "investigate should point to /archspec:check-architecture for cross-service changes"
    )


def test_investigate_bridges_findings_to_edge_cases():
    """Every finding must be materialised as an edge_cases[] entry, not left as

    chat prose. Regression guard for the failure mode where investigate named a
    join-key risk verbatim (city_id vs free-text city) and the implementation
    still shipped the wrong field, because the finding lived only in the chat and
    never reached the plan / the code / a test.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "edge_cases" in low, "investigate must turn findings into edge_cases[] entries"
    assert "bridge" in low, "the edge_cases step must be framed as the investigate->code bridge"
    # the bridge only holds because DET-003 forces the test file to exist at commit time
    assert "det-003" in low, (
        "the edge_cases bridge must cite DET-003 — that's what blocks the commit until "
        "the test file exists, which is why an edge_cases entry survives where prose does not"
    )
    assert "prose" in low, "the skill must explicitly contrast an edge_cases entry with chat prose"


def test_investigate_clarify_splits_identity_trust():
    """The identity-trust question must be its own clarify dimension, not bundled

    into 'entry point & ownership'. Regression guard for the failure mode where
    the model answered the entry-point half ('enters via api-gateway') and
    silently skipped 'where does worker_id come from?', leaving client-supplied
    identity trusted.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "trusted identity" in low, (
        "identity-trust must be a first-class clarify dimension, not a clause buried "
        "inside entry-point & ownership"
    )
    assert "checkbox" in low, (
        "the clarify rules must require every sub-question inside a dimension to be "
        "treated as its own checkbox, so a bundled half cannot be silently skipped"
    )


def test_investigate_self_review_hunts_reuse_and_atomicity():
    """The self-review anti-pattern list must cover the design-level bugs that

    investigate itself drew and missed: recompute-instead-of-reuse in a retry
    loop, attempt identity reconstructed from consumer memory instead of the
    event payload, two events from one handler that aren't atomic, a notification
    fired despite a failed state transition, and a terminal guard narrower than
    the real input states.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "recompute instead of reuse" in low, (
        "self-review must hunt a retry loop that recomputes an expensive pipeline "
        "instead of reusing a first-attempt snapshot"
    )
    assert "snapshot" in low, "the reuse anti-pattern must name the snapshot that should be reused"
    assert "consumer memory" in low and "event payload" in low, (
        "self-review must catch attempt/version identity reconstructed from consumer "
        "memory instead of carried in the event payload"
    )
    assert "same outbox transaction" in low, (
        "self-review must catch two events from one handler that must be atomic but "
        "are appended separately"
    )
    assert "narrower than the real input states" in low, (
        "self-review must catch a terminal-state guard tighter than the states the "
        "entity can actually be in when the branch fires"
    )
    assert "state transition and its notification not atomic" in low and "failtask" in low, (
        "self-review must catch a terminal notification fired even when FailTask "
        "failed or was swallowed"
    )
    assert "first attempt" in low and "initial match finds" in low, (
        "self-review must catch a first-attempt no-candidates dead-end, not only "
        "the last retry attempt"
    )


def test_investigate_has_reference_spec_ingest():
    """investigate must offer to cross-check the design against a reference /

    golden architecture spec. Regression guard for naming-drift and out-of-prompt
    invariants (canonical event names, 'reuse the snapshot' rules) that the prompt
    never states and the model otherwise invents.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "reference cross-check" in low, (
        "investigate output must include a reference cross-check note"
    )
    assert "golden architecture spec" in low or "reference / golden" in low, (
        "investigate should offer to ingest a reference/golden architecture spec"
    )
    assert "ask the user **once**" in low and "path provided" in low, (
        "investigate should ask once for a reference spec and define the path-provided flow"
    )
    assert "read it" in low and "conversation context only" in low, (
        "a supplied reference spec should be read as context, not parsed into the contract"
    )
    assert "event/topic names" in low and "rpc names" in low, (
        "the reference cross-check must include event/topic and RPC names"
    )
    assert "dedup/idempotency keys" in low and "invariants" in low, (
        "the reference cross-check must include dedup/idempotency keys and invariants"
    )
    assert "divergence" in low, (
        "a divergence from the reference spec must be named, not silently renamed away"
    )
    # the spec is a hint, never an override — code reality wins on conflict
    assert "never an override" in low, (
        "the reference spec must be a hint, never an override of code reality"
    )


def test_investigate_states_definition_of_done():
    """investigate must spell out a Definition of done so the closing agent does

    not stop at green unit tests. Regression guard for the failure mode where the
    run ended on a green build and never ran /archspec:validate or
    /archspec:check-architecture, leaving the contract unchecked against the code.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "definition of done" in low, "investigate must spell out a Definition of done"
    assert "actually exercises it" in low and "not merely a file that exists" in low, (
        "the Definition of done must require real edge_cases[] test coverage, not only "
        "a DET-003 file reference"
    )
    assert "/archspec:validate" in low and "exceptions[]" in low, (
        "the Definition of done must require /archspec:validate or explicit exceptions"
    )
    assert "/archspec:check-architecture" in low and "cross-service changes" in low, (
        "the Definition of done must require /archspec:check-architecture for cross-service work"
    )
    assert "# unconfirmed" in low and "adr" in low, (
        "the Definition of done must require resolving # UNCONFIRMED markers or carrying "
        "them into edge_cases[] / ADR"
    )
    # green unit tests must be explicitly disqualified as 'done'
    assert "go build" in low and "clears" in low, (
        "the Definition of done must state that a green go build / go test clears none "
        "of the validation boxes"
    )


def test_investigate_forces_state_ownership_map():
    """investigate must force an explicit system-of-record analysis: a clarify
    dimension for state ownership and a forcing State-ownership map artifact.
    Regression guard for the failure mode where an orchestrator service absorbed a
    state transition owned by the aggregate's service (task-service never selected).
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "state ownership" in low, (
        "investigate needs a 'State ownership (system-of-record)' clarify dimension"
    )
    assert "system-of-record" in low, "ownership must be framed by system-of-record"
    assert "state-ownership map" in low, (
        "investigate output must include a forcing State-ownership map artifact"
    )
    assert "# unconfirmed: foreign-state mutation" in low, (
        "a cross-service write that bypasses the system-of-record must be marked "
        "# UNCONFIRMED: foreign-state mutation"
    )


def test_investigate_self_review_hunts_ownership_replay_and_n_plus_1():
    """The self-review anti-pattern list must hunt the three residual bugs: a sync
    RPC mutating another aggregate's state, idempotency that breaks under replay, and
    an N+1 loop where a batch endpoint exists. Plus the topology preference for the
    owner-applies-async-command shape.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "foreign-state mutation via a sync rpc" in low, (
        "self-review must hunt a sync RPC that mutates state owned by another service's aggregate"
    )
    assert "under replay" in low, (
        "self-review must trace a literal duplicate invocation (idempotency under replay)"
    )
    assert "n+1 where a batch endpoint exists" in low, (
        "self-review must catch a per-item loop where the downstream exposes a batch endpoint"
    )
    assert "owner-applies-async" in low, (
        "the clarify/self-review must prefer the owner-applies-async-command shape over a "
        "foreign-aggregate sync mutation"
    )


def test_investigate_draws_sequence_diagram():
    """The chat-only change diagram must be a Mermaid sequence diagram for any
    cross-service flow, mirroring how reference/golden specs are drawn. A
    flowchart hides who calls whom, what is sync vs async, and where the
    terminal branches are — exactly the properties task_3 reviews flagged.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "sequencediagram" in low, (
        "investigate must draw a Mermaid sequenceDiagram for cross-service changes"
    )
    assert "->>" in text and "-)" in text, (
        "the sequence diagram must distinguish sync calls (->>) from async events (-))"
    )
    assert "alt" in low and "terminal" in low, (
        "limit/dead-end branches must appear as alt/else blocks with terminal states"
    )
    assert "intra-service" in low, (
        "a flowchart is allowed only as the named exception for intra-service branch logic"
    )


def test_investigate_persists_archplan_artifact():
    """The investigation output must survive the chat: the plan-writer and the
    implement skill read files, not chat history. Regression guard for task_3,
    where the plan step silently flipped the topology (sync RPC instead of
    outbox events) and dropped snapshot reuse because the investigation lived
    only in conversation context.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert ".archplan.md" in low, (
        "investigate must persist its output contract to a docs/plans/*.archplan.md artifact"
    )
    assert "docs/plans/" in low, "the archplan artifact lives under docs/plans/"
    assert "only file" in low or "single artifact" in low, (
        "the artifact is the ONLY file this skill writes — code and contracts stay untouched"
    )


def test_investigate_has_independent_plan_review_gate():
    """Self-review by the same context is weak: the author re-reads their own
    assumptions. task_3 shipped 3 plan-level bugs (re-run instead of snapshot
    reuse, GetWorkersBatch missing, facade boundary unspecified) straight past
    the self-review loop. The gate must be an INDEPENDENT subagent with a fresh
    context, an adversarial rubric, and a hard verdict loop.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "fresh context" in low and "subagent" in low, (
        "the plan must be reviewed by an independent subagent with a fresh context"
    )
    # rubric items — each maps to a task_3 plan/implementation failure
    assert "does not exist" in low or "invented method" in low, (
        "rubric: every downstream method named in the plan must exist in the callee's contract"
    )
    assert "snapshot" in low and "recompute" in low, (
        "rubric: reuse-vs-recompute — expensive results snapshotted, not re-run per attempt"
    )
    assert "batch" in low, "rubric: batch endpoints used where the downstream exposes them"
    assert "end-to-end" in low and ("seed" in low or "fixture" in low), (
        "rubric: every new field threaded from the public entry point to consumers, incl. seeds"
    )
    assert "requirement" in low and "plan element" in low, (
        "rubric: every stated requirement maps to a concrete plan element"
    )
    assert "Plan-review: APPROVED after <N> round(s)" in text, (
        "the gate must emit the literal 'Plan-review: APPROVED after <N> round(s), ...' line"
    )
    assert "3 round" in low or "three round" in low, (
        "the review loop is bounded: after 3 rounds unresolved findings escalate to the user"
    )


def test_implement_has_conformance_gates():
    """/archspec:implement exists because task_3 proved a green build is not
    conformance: the code shipped a nil-wired gateway, never published
    match.found on reassignment, never threaded city_id through the public
    edge, and marked dedup before the side effects. Each gate below kills one
    of those bug classes.
    """
    text = (SKILLS / "architecture-implement" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    # input: the persisted archplan artifact
    assert ".archplan.md" in low, "implement consumes the .archplan.md artifact from investigate"
    assert "/archspec:investigate" in low, (
        "without an archplan artifact, implement must refuse and point to /archspec:investigate"
    )
    # phase: contracts first
    assert "yaml patch" in low and "/archspec:sync" in low, (
        "implement applies the archplan's YAML patch and regenerates docs via /archspec:sync"
    )
    # phase: coding plan with conformance table
    assert "conformance table" in low, (
        "the coding plan must carry a conformance table: archplan element -> coding task"
    )
    assert "superpowers:writing-plans" in low, (
        "the coding plan is written with superpowers:writing-plans"
    )
    assert "exists in the callee" in low or "does not exist" in low, (
        "pre-code gate: every downstream method in the plan exists in the callee's contract/proto"
    )
    # post-code conformance passes — one per task_3 bug class
    assert "composition root" in low and "nil" in low, (
        "wiring pass: no nil passed for a declared dependency in any composition root/main.go"
    )
    assert "events.published" in low and "emit site" in low, (
        "emission pass: every declared published event has a real emit site in code"
    )
    assert "end-to-end" in low and ("seed" in low or "fixture" in low), (
        "threading pass: every new field reaches the public edge, seeds and fixtures included"
    )
    assert "before the side effects" in low or "after the side effects" in low, (
        "dedup pass: dedup marking must be atomic with or after the side effects, never before"
    )
    assert "file:line" in low and "requirement" in low, (
        "evidence pass: every requirement maps to file:line proof"
    )
    # validation gates
    assert "/archspec:validate" in low and "/archspec:check-architecture" in low, (
        "implement runs the monorepo-aware validate and check-architecture and fixes BLOCKs"
    )
    # final independent review
    assert "fresh context" in low and "diff" in low, (
        "a fresh-context subagent reviews the final diff against the archplan"
    )
    # commit discipline
    assert "do not push" in low or "without pushing" in low or "no push" in low, (
        "implement commits but never pushes"
    )


def test_plan_review_enforces_per_attempt_identity():
    """task_5 shipped the task_1 bug again: matching reused the same MatchID in
    the reassignment match.found and notification deduped on MatchID — the
    re-offer was swallowed as a duplicate. The plan even said "dedup on MatchID
    remains, no key change" and self-review approved it. The rubric must name
    the rule explicitly: an ID reused across retry attempts must either be
    regenerated per attempt or be part of EVERY consumer's dedup key.
    """
    text = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "reused across" in low and "attempt" in low, (
        "plan-review rubric must call out identifiers reused across retry attempts"
    )
    assert "regenerated per attempt" in low or "new per attempt" in low, (
        "the fix options must be named: regenerate per attempt, or attempt-qualify "
        "every consumer's dedup key"
    )


def test_review_gates_mark_solo_degradation():
    """When the executing agent cannot dispatch subagents, the 'independent
    fresh-context review' silently degrades to self-review — in task_5 that
    degraded gate approved the critical bug. The degradation must be visible:
    a SELF-ONLY verdict marker in both gates.
    """
    inv = (SKILLS / "architecture-investigate" / "SKILL.md").read_text(encoding="utf-8")
    imp = (SKILLS / "architecture-implement" / "SKILL.md").read_text(encoding="utf-8")
    assert "SELF-ONLY" in inv, (
        "investigate step 9c must mark a solo (no-subagent) review as SELF-ONLY"
    )
    assert "SELF-ONLY" in imp, (
        "implement phase G must mark a solo (no-subagent) review as SELF-ONLY"
    )


def test_implement_conformance_passes_cover_task5_bug_classes():
    """Three HIGHs in task_5 slipped through the conformance passes because the
    passes did not name them: a gRPC client default pointing at another
    service's port; a documented public route that the router never matches;
    and a replayed second-attempt event swallowed by a consumer's dedup key.
    """
    text = (SKILLS / "architecture-implement" / "SKILL.md").read_text(encoding="utf-8")
    low = text.lower()
    assert "port" in low and ("address" in low or "addr" in low), (
        "wiring pass must verify client default addresses/ports against the target "
        "service's actual listen port"
    )
    assert "router" in low and "string-for-string" in low, (
        "threading pass must require declared public routes to match the router "
        "registration string-for-string"
    )
    assert "second-attempt" in low or "second attempt" in low, (
        "dedup pass must trace a literal second-attempt event through every "
        "consumer's dedup logic"
    )
