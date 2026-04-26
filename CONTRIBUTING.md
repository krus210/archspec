# Contributing

Contributions are welcome, especially linters for new languages under
`linters/<lang>/`.

## One-time setup

The project uses a local virtualenv at `.venv/` so commands work the same
on every machine regardless of system `python` / `pip`:

```bash
make bootstrap     # python3 -m venv .venv + pip install -r requirements-dev.txt
```

Requires `python3 >= 3.11` and `go >= 1.23` on PATH.

## Before opening a PR

Run the local checks:

```bash
.venv/bin/ruff check .
make test                  # pytest + go test
make benchmarks            # ./benchmarks/run.sh
```

If the change edits `SERVICE_MAP.yaml`, regenerate derived docs before
committing (the launcher picks `.venv/bin/python` automatically and falls
back to system `python3`):

```bash
bin/archspec-python skills/architecture-sync/scripts/sync.py docs/SERVICE_MAP.yaml docs
```

## Adding a language linter

Add a new directory under `linters/<lang>/`, document its activation in a
`README.md`, and emit findings using the JSON contract described in
`docs/EXTENDING.md`.
