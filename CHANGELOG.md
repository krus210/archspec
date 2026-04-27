# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
