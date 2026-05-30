# task-service init output

Reference Mermaid output from running `/archspec:init` on a small `task-service`.

The files under `docs/diagrams/` show the shape users should expect from a fresh
bootstrap:

- `context.mmd` — service in its upstream/storage/event context.
- `container.mmd` — service container with caller methods and owned resources.
- `sequence.mmd` — endpoint-level read/write flow, idempotency note, and event publish.

