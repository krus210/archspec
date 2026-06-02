# archspec Go linters

Day-one rule set for `/archspec:validate` against Go services.

## Subcommands

| Subcommand | Rule | Severity | Checks |
| --- | --- | --- | --- |
| `handler-idempotency` | AI-001 | BLOCK | endpoint declared `idempotency.required: true` but handler does not read the configured header |
| `outbox-pattern` | AI-002 | BLOCK | direct `Publish(...)` after `Save(...)` when `consistency.write_path.pattern: outbox` |
| `optimistic-locking` | AI-003 | BLOCK | UPDATE missing `WHERE <row_version_field> = ?` when an aggregate uses `write_strategy: optimistic` |
| `swallowed-errors` | AI-007 | WARN | `_ = svc.Call(...)` or `resp, _ := svc.Call(...)` discards a downstream call's error when `dependencies.downstream.sync[].on_failure` is declared |
| `redundant-call` | AI-008 | WARN | a singular downstream method called inside a loop when a `*Batch` sibling exists (N+1) |
| `undeclared-event` | AI-009 | WARN | NATS `Publish`/`Subscribe` to a topic (literal or const) absent from `events.published`/`events.consumed` |

## Invocation

For direct manual use (from inside `linters/go/`):

```
go run ./linters/go <subcommand> --service-map docs/SERVICE_MAP.yaml --code .
```

`/archspec:validate` does not call `go run` directly. It invokes the dispatcher
`linters/go/lint.sh`, which honours the cross-language contract:

- `lint.sh --list` prints supported subcommand names, one per line, exit 0.
- `lint.sh <subcommand> [args...]` forwards args to `go run` for that subcommand.

Output: a JSON array of `Finding` objects (see `finding.go`). Exit code 0 = no findings, 1 = findings printed, 2 = usage error.

## Activation

The validate skill iterates over linters when `service.language == "go"`. To add a new subcommand, register it in the `subcommands` map in `main.go` and ship a fixture under `testdata/<name>/{ok,bad}/`.

## Determinism

Linters do not read the system clock, environment, or random state. Output ordering follows file path then source line, both already sorted by the Go AST traversal.
