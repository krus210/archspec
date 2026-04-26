# archspec benchmarks

Reproducible quality benchmarks for archspec skills, schemas, and linters.
Each suite writes a JSON report to `benchmarks/results/` (gitignored) and
exits non-zero on regression.

## Suites

| Suite        | Entry point                                               | What it asserts                                                                          |
| ------------ | --------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| determinism  | `python -m benchmarks.determinism.run_determinism`        | `sync()` produces byte-identical outputs across N runs (default 20) for every fixture.   |
| schema       | `python -m benchmarks.schema.run_schema`                  | Valid YAMLs validate; invalid YAMLs fail with the expected error substring.              |
| violations   | `python -m benchmarks.violations.run_violations`          | (Plan 06 Task 4+) Linter detection precision/recall on labeled fixtures.                 |

## Run all suites

```bash
./benchmarks/run.sh
```

To run a single suite, pass `--suite <name>`:

```bash
./benchmarks/run.sh --suite determinism
./benchmarks/run.sh --suite schema
./benchmarks/run.sh --suite violations
```

## Record mode

Use `--record <fixture-dir>` to refresh the golden expectations for a single
violations fixture (rerun after intentionally changing linter output):

```bash
./benchmarks/run.sh --record benchmarks/violations/fixtures/01_missing_idempotency_key
```

The recorder rewrites the fixture's `expected.json` (or equivalent golden
file) in place; review the diff before committing.

## Output layout

```
benchmarks/results/
  determinism.json
  schema.json
  violations.json
```

All reports are written atomically with stable key ordering, so they diff
cleanly across runs.
