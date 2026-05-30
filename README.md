# archspec

> Spec-driven architecture validation for microservices.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Benchmarks](https://github.com/krus210/archspec/actions/workflows/benchmarks.yml/badge.svg)](.github/workflows/benchmarks.yml)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-blue)](https://www.anthropic.com/claude-code)

## What it does

archspec captures a microservice's architecture as a versioned, machine-readable
contract (`SERVICE_MAP.yaml`), generates Mermaid diagrams and `ARCHITECTURE.md`
deterministically from it, and validates code changes against it on two layers:

- **Deterministic gate** in pre-commit (schema, cycles, breaking changes, exceptions)
- **AI deep dive** via `/archspec:validate` (idempotency, race conditions, eventual consistency)

```
                    ┌─────────────────────────┐
                    │  docs/SERVICE_MAP.yaml  │  ← single source of truth
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  /archspec:sync          pre-commit hook         /archspec:validate
  (Mermaid + ARCH.md)     (DET-001..015)          (AI-001..010)
```

## Why

| Pain | archspec answer |
|---|---|
| `ARCHITECTURE.md` rots — written by hand, updated by goodwill | Generated from YAML; CI fails on drift |
| C4 diagrams in Lucidchart aren't version-controlled | Mermaid in repo, deterministic |
| Invariants like "endpoint must be idempotent" live in tribal knowledge | Encoded in `SERVICE_MAP.yaml`; AI rules check the code |
| Reviewers can't mechanically check contracts | Pre-commit + `/archspec:validate` reports |
| New contributors need weeks to understand the bounded context | Read one YAML, get diagrams + invariants |

## 5-minute install

### Option A — Claude Code plugin (recommended)

```bash
/plugin marketplace add krus210/archspec
/plugin install archspec@archspec
```

After installation, run `/reload-plugins` (or restart Claude Code) so commands and skills become available.

### Option B — standalone skills

```bash
git clone https://github.com/krus210/archspec
ln -s "$PWD/archspec/skills/architecture-sync"        ~/.claude/skills/
ln -s "$PWD/archspec/skills/architecture-investigate" ~/.claude/skills/
```

### Bootstrap a service

```bash
cd path/to/your-service
/archspec:init
```

This creates `docs/SERVICE_MAP.yaml`, generates initial diagrams + `ARCHITECTURE.md`,
installs the pre-commit hook, and appends the archspec block to `CLAUDE.md`.

## What you get

archspec is intentionally small: each command/skill has a concrete artifact at the
end, and those artifacts stay in the repo.

| Flow | Output |
|---|---|
| `/archspec:init` / `architecture-sync` bootstrap | `docs/SERVICE_MAP.yaml`, `docs/diagrams/{context,container,sequence}.mmd`, generated `docs/ARCHITECTURE.md`, `.servicemap/schema.json`, `docs/adr/`, installed git hooks, and the archspec block in `CLAUDE.md` |
| `/archspec:sync` / `architecture-sync` | Regenerated Mermaid diagrams and the managed region of `docs/ARCHITECTURE.md` |
| `/archspec:investigate` / `architecture-investigate` | Read-only contract summary, clarification questions, chat-only Mermaid for the proposed change, YAML diff to apply before coding, and the validation loop to run after implementation |
| `/archspec:validate` | Markdown report grouped by `BLOCK` / `WARN` / `INFO` / `SUPPRESSED`, with file references and fix hints |
| `/archspec:check-architecture` | Monorepo-wide architecture audit across all `SERVICE_MAP.yaml` files |

The generated diagrams are plain Mermaid, so a fresh `/archspec:init` produces
reviewable text artifacts rather than screenshots. Example output from a
`task-service` init is checked in under
[`examples/task-service-init-output/docs/diagrams`](examples/task-service-init-output/docs/diagrams).

Context diagram:

```mermaid
flowchart LR
  subgraph this["task-service"]
    svc[task-service]
  end
  upstream_api-gateway[api-gateway] --> svc
  svc -.-> storage_task-store[("in-memory: task-store")]
  svc ==>|publish| topic_task-created>task.created]
```

Container diagram:

```mermaid
flowchart LR
  subgraph svc_box["task-service"]
    svc[task-service]
  end
  up_api-gateway[api-gateway] -->|CreateTask, GetTask, ListTasks| svc
  svc -.-> store_task-store[("in-memory: task-store")]
  svc ==>|publish v1| pub_task-created>task.created]
```

Sequence diagram:

```mermaid
sequenceDiagram
  autonumber
  participant client as Client
  participant svc as task-service
  participant task-store as in-memory:task-store
  participant events as message-bus
  client->>svc: gRPC CreateTask
  Note over svc: read X-Idempotency-Key
  svc->>task-store: write
  svc->>events: publish task.created (v1)
  svc-->>client: response
  client->>svc: gRPC GetTask
  svc->>task-store: read
  svc-->>client: response
  client->>svc: gRPC ListTasks
  svc->>task-store: read
  svc-->>client: response
```

## What `/archspec:init` does

For Go services, `init` runs a read-only scanner over your source files and pre-fills `docs/SERVICE_MAP.yaml` with what it finds:

- HTTP endpoints from `net/http`, `chi`, `gin`, `echo` route registration
- gRPC endpoints from `pb.RegisterXxxServer` calls
- Downstream gRPC dependencies from `grpc.NewClient` / `grpc.Dial`, with the target service name resolved from address constants where possible
- Storage clients: postgres (`pgx`, `pgxpool`), redis (`go-redis`), mongodb (`mongo-driver`), generic SQL (`sqlx`/`database/sql`), and in-memory repository factories
- Messaging topics from Kafka (`segmentio/kafka-go` writer/reader, `IBM/sarama` producer/consumer-group) and NATS (`nats-io/nats.go` core `Publish`/`Subscribe`/`QueueSubscribe` and JetStream `Publish`), with subjects resolved through Go const tables in the same file

For each finding, archspec asks you to confirm it and to supply the fields the scanner cannot extract from code: SLA, idempotency policy, timeouts, retries, fallback strategy, and contract paths. Skipped findings do not enter the YAML.

If the service is not Go, or the scanner finds nothing, `init` falls back to a fully manual questionnaire. **Messaging stacks the scanner does not know yet (RabbitMQ, GCP Pub/Sub, in-house queues) do not cause failures** — events just come back empty and the questionnaire asks you to list them manually. Adding a new backend to the scanner is a small contribution: extend `_MESSAGING_BACKENDS` in `skills/architecture-sync/scripts/scan_go.py` with one publish/subscribe pattern pair plus a fixture.

## Commands

| Command | Purpose |
|---|---|
| `/archspec:init` | Bootstrap a new service |
| `/archspec:sync` | Regenerate Mermaid + ARCHITECTURE.md from `SERVICE_MAP.yaml` |
| `/archspec:validate` | Run the AI rules and produce a markdown report |
| `/archspec:investigate` | Pre-feature workflow: read contract, propose YAML changes inline |

See `commands/*.md` for full details.

## Skills (autopilot)

| Skill | Triggers when | Produces |
|---|---|---|
| `architecture-sync` | After Edit on `SERVICE_MAP.yaml`; phrases like "regenerate diagram", "service map drift" | Validated `SERVICE_MAP.yaml`, refreshed Mermaid diagrams, refreshed `ARCHITECTURE.md`, staged generated artifacts |
| `architecture-investigate` | Phrases like "let's add X", "investigate Y", "understand how Z works" | Read-only architecture slice, clarification gate, change-only Mermaid, proposed YAML diff, validation checklist |

## What gets validated

<details>
<summary>Click to expand the rule list</summary>

**Deterministic (DET-*)** — pre-commit, < 1s, zero false positives:

- DET-001 schema validation · DET-002 dependency cycles · DET-003 reference paths
- DET-004 diagram drift · DET-005 hand-edited diagrams · DET-006 idempotency breaks
- DET-007 removed edge_cases / scenarios · DET-008 missing changelog
- DET-009 consistency model change · DET-010..015 exception discipline

**AI (AI-*)** — `/archspec:validate`, contextual:

- AI-001 idempotency · AI-002 outbox bypass · AI-003 optimistic locking
- AI-004 façade-only violation · AI-005..006 coverage · AI-007 swallowed errors
- AI-008 redundant fetches · AI-009 undeclared dependency · AI-010 undeclared endpoint

</details>

Full catalog: [`docs/VALIDATION_RULES.md`](docs/VALIDATION_RULES.md).

## Extending to your language

Day one ships `linters/go/`. Adding `linters/python/` or `linters/node/` means dropping a
folder and following [`docs/EXTENDING.md`](docs/EXTENDING.md). Activation is automatic via
`service.language` in `SERVICE_MAP.yaml`.

## Determinism guarantees

Generators sort inputs by stable key, use a pure `slugify()` for IDs (no hashing), and read
no clocks, randomness, environment, or filesystem state beyond the input YAML and templates.
LF line endings, UTF-8 no BOM, fixed trailing newline. The benchmark suite enforces this:
20 runs of every input must produce one SHA-256 per output file.

## Benchmarks

```bash
./benchmarks/run.sh
```

Three suites: determinism, schema, violations (F1 ≥ 0.95 threshold). Behavioral evaluation
requiring `ANTHROPIC_API_KEY` is deferred to a later milestone.

## How it compares

| | archspec | hand-written `ARCHITECTURE.md` | Structurizr / C4 modeling |
|---|---|---|---|
| Source of truth | YAML in repo | Markdown, drifts | DSL in separate tool |
| CI gate | yes | no | partial |
| Generated diagrams | yes (Mermaid) | no | yes |
| AI-level invariant checks | yes | no | no |
| Cost | free, local | free, manual | commercial |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Linters for new languages are very welcome.

## License

MIT. See [`LICENSE`](LICENSE).
