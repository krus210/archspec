<!-- archspec:managed-region:start -->
<!-- generated from SERVICE_MAP.yaml — do not edit by hand -->

# listings-svc — Architecture

**Domain:** marketplace.listings
**Team:** marketplace
**Language:** go
**Repo:** github.com/example/listings-svc
**Owners:** primary @alice · oncall @bob

## Responsibilities
- create and update listings
- publish ListingChanged events

## Invariants
- listings are immutable after publication

## API
Version: 1
| Endpoint | Protocol | Idempotent | SLA p99 |
| --- | --- | --- | --- |
| CreateListing | HTTP | yes | 200ms |

## Dependencies
### Sync downstream
_None._

### Async downstream
_None._

### Storage
- **postgres:listings_db** — owned by listings-svc

## Events
**Published:**
- listings.changed.v1 (v1)

**Consumed:**
_None._

## Consistency
- **Model:** eventual
- **Bounded aggregate:** Listing
- **Write path:** outbox
- **Read path:** read-your-writes

## Concurrency
- **Listing** — optimistic

## Diagrams
- [Context](diagrams/context.mmd)
- [Container](diagrams/container.mmd)
- [Sequence](diagrams/sequence.mmd)

<!-- archspec:managed-region:end -->
