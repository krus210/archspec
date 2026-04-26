# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
