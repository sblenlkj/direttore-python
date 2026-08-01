# Direttore architecture guide

Direttore is a Python 3.12 slot-centric orchestration framework.

## Ownership

Physical execution slots own the complete execution scope:

- direct/key/operation message resolution and payload construction;
- lifecycle-context creation and cleanup;
- root and child tracing spans;
- the unified `ResourceHolder` and UoW access;
- event queue and transaction-relative event timing;
- saga entry collection, persistence, and compensation;
- commit, rollback, close, and reusable-slot reset.

Do not add orchestration engines back. Shared code may be extracted only when it
retains a concrete responsibility and does not create a second execution path.

## Slot and lease

`BaseExecutionSlot` is a reusable physical container owned by a provider.
`SlotLease` is temporary generation-checked ownership. Automatic application
methods acquire a lease, invoke the same six lease methods exposed publicly,
commit, and release.

One lease is sequential. Concurrent use is a framework error. A failed handler
makes the lease rollback-only. Release is cancellation-safe and rolls back
uncommitted work. A released or stale lease must never reach a reused slot.

## Resources and UoW

Use only `ResourceHolder`. Do not add query-specific or command-specific
holders. Named resources are lazy and cached. Commit intent is monotonic per
name. The UoW delegates reads and writes to the holder and owns no cache or
transaction state.

On successful finalization:

- resources with write intent commit in deterministic creation order;
- read-only resources rollback;
- every resource closes on release.

On failure every opened resource rolls back. Multiple resources are
best-effort and non-atomic; never imply distributed transaction guarantees.

## Queries

Keep Query, QueryHandler, query registries/resolvers, and all three query entry
forms. Query orchestration must share slot, lease, provider, holder, tracing,
lifecycle, and cleanup infrastructure with use cases.

## Events

For `IN_TRANSACTION`, drain events before commit. For `AFTER_TRANSACTION`,
commit business resources first, then open a new resource boundary for events.
Event dispatchers resolve/invoke handlers but never own the top-level
transaction.

## Modular monolith

The coordinator receives one unified holder. Use-case and query UoWs may be
distinct typed facades but delegate to the same holder. Runtime nested
invocations receive lifecycle state for the active operation and explicit
parent spans. Never store an active span in the runtime.

## Saga

Saga keys and compensation types are registration metadata. Commands and
events do not carry handler keys. `SagaHandlerResult` is the only compensable
success wrapper. Store only payload-based `SagaEntry` values in the holder and
journal. Persist before commit. Compensate in reverse order and require
idempotent compensation methods.

Do not add nested sagas, distributed locks, two-phase commit, a retry daemon,
or durable slot storage without a separate architecture change.

## Agent integration

Pass `SlotLease` only through transient agent runtime/context. Never serialize
it into graph state. Use a transactional subgraph so graph checkpoints cannot
claim an internal DB node completed while its encompassing transaction later
rolls back.

## Change checklist

1. Inspect both application variants and public exports.
2. Preserve one automatic/explicit lease execution pipeline.
3. Add focused tests for ownership, failure, cleanup, and ordering.
4. Update `__init__.py` exports and migration docs.
5. Run pytest, Ruff format/lint, Pyright, and stale-reference searches.
