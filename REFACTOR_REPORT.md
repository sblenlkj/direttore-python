# Direttore slot-centric refactor report

## Summary

Direttore now executes commands, events, stored operations, and saga
compensation through physical execution slots and generation-checked
`SlotLease` objects. Separate simple-service and modular-monolith application
facades preserve their concrete slot types. Slots own lifecycle,
tracing, resource boundaries, event timing, saga persistence, and cleanup.

## Major changes

- Replaced separate command/query resource ownership with one `ResourceHolder`.
- Added named lazy resources and monotonic per-resource commit intent.
- Made UoWs delegate read/write access to the holder without caching sessions.
- Moved command entry paths into each physical slot implementation.
- Removed command/query orchestration engines and the old slot-pool facade.
- Added `SlotLease`, state/errors, generation validation, concurrency rejection,
  direct release, and transactional context management.
- Added `ExecutionSlotProvider`, pooled and factory implementations.
- Migrated both service-specific application facades to configurable providers
  and the same transactional-slot pattern.
- Removed query contracts, registries, resolvers, routing, and runtime paths.
- Added payload-only saga models, journal, entry collection, persist-before-
  commit ordering, and reverse compensation.
- Kept the active lease operation span exclusively in `SlotExecutionCache` and
  kept span state out of the modular runtime.

## Removed code

- `AbstractUseCaseResourceHolder` and `QueryResourceHolder`: their split
  duplicated resource scope and transaction rules.
- Simple-service and modular command/query engines: all orchestration now has a
  concrete slot owner.
- `ExecutionSlotPool`: provider abstractions now own acquisition policy.
- Query-specific holder and UoW factories and the remaining query API.
- Initial `saga_storage.py` scaffolding: replaced by payload-based models and a
  journal contract.
- Engine-specific payload-loader contracts: simple-service and modular slots
  use one `OperationLoader` receiving the active `ResourceHolder`; execution
  settings live with application slot config.

## Resource holder

Named resources are created only on first access and cached for the prepared
slot scope. A read requests `commit=False`; a write upgrades intent to `True`.
Intent never decreases. `ResourceHolder` is abstract: application programmers
implement commit, rollback, close, ordering, and failure policy. Implementations
mark finalization through the protected helper. After resources are closed, the
execution slot clears execution-scoped state through public `reset()`.

## Slot and SlotLease

A physical slot contains the holder, UoWs/coordinator, event state, modular
runtime, tracing state, lifecycle handoff, and saga entries. A lease contains a
physical-slot reference and generation token.

Lease states are `ACTIVE` and `COMMITTED`. Release is tracked as ownership
cleanup rather than a transaction state, rolls back unfinished work, and is
idempotent. Released and stale leases fail before reaching the slot. A busy
flag rejects concurrent operations.

## Saga

`SagaEntry` stores only kind, stable handler key, and serialized payload.
`SagaRecord` adds the scope-owned saga ID. `SagaUseCaseHandlerResult` separates
the business result from compensation data, while `SagaEventHandlerResult`
carries event compensation only.

The holder collects entries after successful compensable handlers. Lease commit
saves one record before committing business resources. `InMemorySagaJournal`
deep-copies payloads on save and load. Compensation loads the record, reverses
entries, resolves handlers by kind and saga key, reconstructs compensation via
`from_payload`, and calls the original handler's idempotent `compensate` method.

In-memory/Redis journal persistence is not atomic with SQL. A SQL journal is
atomic only when it uses the same session. With multiple resources, persistence
is atomic only relative to the journal's chosen resource.

## Slot providers

`PoolExecutionSlotProvider` maintains a bounded reusable pool, waits at
capacity, resets only after cleanup, and exposes statistics.

`FactoryExecutionSlotProvider` creates a slot for every acquisition and disposes
its resources on release. Both providers own a service-specific `SlotCreator`;
the configured provider instance is injected into its application facade.

## Tests and checks

The original baseline did not collect: slotted registration multiple inheritance
raised `TypeError: multiple bases have instance lay-out conflict`. The registry
model was flattened as part of the migration.

Added coverage includes:

- lazy/cached named resources, intent upgrades, read rollback, write commit,
  failure rollback, zero-session execution, reuse, and partial commit details;
- sequential lease calls, manual commit/rollback, automatic release rollback,
  concurrency rejection, cancellation cleanup, pool reuse, and factory disposal;
- direct/key/operation application paths and explicit lease paths;
- modular nested runtime lifecycle handoff and cleanup;
- in/after-transaction event ordering and lease trace shape;
- saga persist-before-commit, payload copying, lease-wide collection, and reverse
  compensation.

Final commands and results:

```text
uv run pytest -q
26 passed

uv run ruff format --check src tests
81 files already formatted

uv run ruff check src tests
All checks passed

uvx pyright src
0 errors, 0 warnings, 0 informations

uv run python -m compileall -q src
passed
```

## Breaking changes

- Construct `ResourceHolder`; the two specialized holder classes were removed.
- `SimpleServiceSlotConfig` now accepts `resource_holder_factory` and
  `uow_factory`.
- `ModularMonolithSlotConfig` now accepts `resource_holder_factory` and a
  one-argument `coordinator_factory`.
- Coordinators initialize with `resource_holder=` and expose that one holder.
- Engine orchestration classes and `ExecutionSlotPool` were removed.
- Stored-operation settings moved to `*ExecutionConfig.operation_loader`.
- Stored-operation loaders implement the shared `OperationLoader` contract and
  receive `ResourceHolder` instead of a UoW or modular coordinator.
- Applications expose `slot_provider_stats`; `slot_pool_stats` remains as a
  documented metrics-name bridge during provider migration.
- Applications accept a configured `ExecutionSlotProvider`; configuration,
  dependency resolution, routing, and physical slot construction live in the
  service-specific `SlotCreator`.

## Migration guide

See [MIGRATION.md](MIGRATION.md). In summary, create one holder per physical
slot, construct all UoWs against it, choose read/write intent through the UoW,
and replace any direct engine/pool use with application calls or an explicit
`director.slot()` lease.

## Remaining limitations

- no cross-resource atomicity or distributed transactions;
- no two-phase commit or automatic partial-commit recovery;
- no parallel use of one lease;
- no durable storage of a lease;
- no nested sagas, distributed locks, or automatic retry scheduler;
- basic saga retry/status semantics only;
- after-transaction events run in a new local resource boundary.

## Files changed

- `src/direttore/application`: physical slots, applications, lease, providers.
- `src/direttore/core/primitives`: unified holder and holder-backed UoW.
- `src/direttore/core/saga`: models and journal.
- `src/direttore/core/registries` and `resolvers`: saga metadata/resolution.
- `src/direttore/core/modular_monolith_support`: unified coordinator/runtime.
- `src/direttore/core/event_dispatchers` and `tracing`: slot-owned integration.
- `tests`: focused resource, slot, provider, application, event, trace, and saga
  coverage.
- `README.md`, `AGENT.md`, `MIGRATION.md`, and `slot_and_slot_lease.md`.

## Final status

- Tests pass: yes.
- Formatting passes: yes.
- Lint passes: yes.
- Type checking passes: yes.
- Public export smoke test passes: yes.
- Documentation updated: yes.
