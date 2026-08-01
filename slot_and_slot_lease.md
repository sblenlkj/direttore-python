# Slot and SlotLease

## Model

The Director owns an `ExecutionSlotProvider`. A provider owns acquisition and
release policy for physical slots. A `SlotLease` grants one execution temporary
ownership of a physical slot.

```text
Director -> Provider -> SlotLease -> physical Slot -> ResourceHolder
```

The physical slot is reusable. The lease is not. Every acquisition increments
the slot generation; lease operations compare their captured generation with
the slot before touching it.

## State machine

```text
ACTIVE --commit--> COMMITTED --release--> RELEASED
ACTIVE --rollback--> ROLLED_BACK --release--> RELEASED
ACTIVE --handler failure--> ROLLBACK_ONLY --rollback/release--> RELEASED
ACTIVE --commit failure--> FAILED --release cleanup--> RELEASED
```

Double release is idempotent. Execution, commit, and rollback after release are
forbidden. A handler failure prevents new execution until rollback/release. A
commit failure leaves the lease non-reusable and release performs best-effort
rollback and cleanup.

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
cancellation. Lease release shields cleanup so slot return is not interrupted.

## Automatic calls

`Application.handle` and its five sibling methods are convenience wrappers over
the same lease calls:

```python
async with application.slot(saga_id=saga_id) as lease:
    async with lease.transaction():
        return await lease.handle(command, input=input, trace=trace)
```

There is no engine-specific automatic path.

## Tracing and lifecycle

The first traced operation opens one lease root span. Each command/query or
compensation call is a child. The root remains active through saga persistence,
commit/rollback, after-transaction events, and resource cleanup, then closes on
release.

Lifecycle contexts remain operation-local because registrations may use
different lifecycle policies. Modular runtime state is installed only while an
operation executes and is cleared in `finally`.

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
