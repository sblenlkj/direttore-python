# Slot and SlotLease

## Model

Each Direttore application facade owns an `ExecutionSlotProvider`. A provider
owns acquisition and release policy for physical slots. A `SlotLease` grants
one execution temporary ownership of a physical slot.

```text
Application -> Provider -> physical Slot -> ResourceHolder
                      `-> SlotLease -> physical Slot -> ResourceHolder
```

The physical slot is reusable. The lease is not. Every acquisition calls
`prepare_slot()`, increments the slot generation, and sets `is_in_use`.
Lease operations compare their captured generation and in-use state before
touching the slot.

`BaseExecutionSlot[InputT, TraceT]` owns the committing plain-slot invocation.
`SlotLease` owns a separate non-committing invocation so sequential operations
can share one transaction. Both use the typed base-slot resolver, lifecycle,
event-dispatch, saga, and cleanup contracts; neither dynamically probes
concrete slot methods.

## State machine

```text
ACTIVE --commit--> COMMITTED
ACTIVE or COMMITTED --release--> ownership detached
```

Only `ACTIVE` and `COMMITTED` are enum states. Release is ownership cleanup,
not a transaction state; the lease detaches from further use after cleanup.
Double release is idempotent. Execution, commit, and rollback after release are
forbidden. Handler and commit failures do not add states.

## Sequential ownership

A lease can move through sequential nodes of a transactional island, but two
tasks cannot use it concurrently. Parallel branches acquire separate leases.

```python
async with director.slot() as lease:
    async with lease.transaction():
        await lease.handle(command_a, input=context)
        await lease.handle(command_b, input=context)
```

`transaction()` commits on success and rolls back on exceptions, including
cancellation. Release performs rollback when necessary, closes cached tracing
state, and returns the slot directly to its provider.

## Automatic calls

`Application.handle`, `handle_by_key`, `handle_operation`, and
`compensate_saga` use a plain physical slot. Each facade method explicitly owns
its one-shot transaction:

```python
slot = await application.acquire_slot(saga_id=saga_id)
try:
    result = await slot.handle(command=command, input=input, trace=trace)
    return result
except BaseException:
    await slot.rollback()
    raise
finally:
    await application.slot_provider.release_slot(slot)
```

The application facade does not route one-shot calls through `SlotLease`.
Simple-service and modular-monolith have separate facades so their physical
slot return types remain concrete. Plain-slot invocation commits after
in-transaction events or before post-transaction events. Lease invocation
drains events during every handle regardless of transaction-relative execution
mode, then defers its single commit until `SlotLease.commit()` or
`transaction()` exits.

## Lease execution and cache

`SlotLease` has three normal execution methods and three cache methods:

- `handle`, `handle_by_key`, `handle_operation`
- `handle_cache`, `handle_by_key_cache`, `handle_operation_cache`

The physical slot itself exposes no cache methods. This keeps cache ownership
and its public API on the lease boundary.

Normal lease calls create and store a lifecycle context and operation child
span. Cache calls accept no lifecycle input or trace; they reuse the stored
state. Starting another normal lease call replaces the cache. The cached span
is closed when replaced or during lease release.

No lease execution method commits resources. `transaction()` or an explicit
`commit()` controls the transaction boundary.

## Tracing and lifecycle

Each normal lease command or compensation creates the span stored in
`SlotExecutionCache`. A cache call reuses that span. Starting another normal
operation closes and replaces it, and release closes the final cached span.
There is no separate lease-root span.

Normal lifecycle contexts remain operation-local because registrations may use
different lifecycle policies. Cache calls intentionally keep the first
context. Modular runtime state is installed only while an operation executes
and is cleared in `finally`.

## Transactional agent subgraphs

```python
async def execute_database_segment(state):
    async with director.slot() as lease:
        async with lease.transaction():
            return await database_subgraph.ainvoke(
                state,
                context={"slot": lease},
            )
```

Store the lease in transient context/runtime only. Durable graph state may be
serialized, restored in another process, or checkpointed after an internal
node; a live session/transaction cannot safely participate in those operations.

## Providers

`PoolExecutionSlotProvider` maintains a bounded reusable pool and waits at
capacity. It resets slots only after rollback/commit cleanup completes and
exposes provider statistics.

`FactoryExecutionSlotProvider` creates a physical slot per acquisition, closes
it on release, and does not reuse it.
