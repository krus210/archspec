<!-- archspec:managed-region:start -->
<!-- generated from SERVICE_MAP.yaml — do not edit by hand -->

# example-service — Architecture

**Domain:** example
**Team:** platform
**Language:** go
**Repo:** github.com/example/service
**Owners:** primary @alice · oncall @oncall

## Responsibilities
- expose REST API

## Invariants
- all writes go through the outbox

## API
Version: 1
_No endpoints declared._

## Dependencies
### Sync downstream
_None._

### Async downstream
_None._

### Storage
_None._

## Events
**Published:**
_None._

**Consumed:**
_None._

## Consistency
- **Model:** eventual
- **Bounded aggregate:** example
- **Write path:** outbox
- **Read path:** eventual

## Concurrency
_No aggregates declared._

## Diagrams
- [Context](diagrams/context.mmd)
- [Container](diagrams/container.mmd)
- [Sequence](diagrams/sequence.mmd)

<!-- archspec:managed-region:end -->
