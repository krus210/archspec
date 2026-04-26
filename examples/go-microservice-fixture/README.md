# go-microservice-fixture

A self-contained example service demonstrating archspec end-to-end:

- `docs/SERVICE_MAP.yaml` — the contract.
- `docs/diagrams/*.mmd` and `docs/ARCHITECTURE.md` — generated; do not hand-edit.
- `internal/...` — Go code that satisfies AI-001..003.

## Try it

```bash
cd examples/go-microservice-fixture
"$(git rev-parse --show-toplevel)/bin/archspec-python" \
  ../../skills/architecture-sync/scripts/validate_servicemap.py docs/SERVICE_MAP.yaml
go build ./...
```

Expected: both commands exit 0.

To regenerate diagrams after editing `docs/SERVICE_MAP.yaml`:

```bash
"$(git rev-parse --show-toplevel)/bin/archspec-python" \
  ../../skills/architecture-sync/scripts/sync.py docs/SERVICE_MAP.yaml docs/
```
