# Direttore

Direttore is a Python 3.12 orchestration kernel for commands, queries, events,
transactional resources, and local saga compensation.

The framework is slot-centric. An application acquires a temporary
`SlotLease`; the physical slot owns handler resolution, lifecycle creation,
tracing, resources, event timing, saga collection, and cleanup. Automatic
application calls and explicit transactional islands use the same pipeline.

## Execution model

```text
Application
  -> ExecutionSlotProvider
    -> SlotLease
      -> physical Slot
        -> resolve + build message
        -> lifecycle + trace
        -> handler + events
        -> saga journal save
        -> resource commit/rollback
      -> cleanup and release
```

Queries remain first-class during this migration, but use the same slot,
resource holder, UoW, lease, and provider infrastructure as commands.

## Resource setup

`ResourceHolder` lazily creates named resources. A UoW requests read or write
intent without maintaining another cache:

```python
holder = ResourceHolder({"primary": async_session_factory})
uow = BaseUnitOfWork(holder)

read_session = await uow.read_session("primary")
same_session = await uow.write_session("primary")

assert same_session is read_session
assert holder.commit_required["primary"] is True
```

On success, write resources commit and read-only resources rollback. On
failure, every opened resource rolls back. Every opened resource closes.
Multiple write resources commit in creation order using deterministic
best-effort sequencing.

> Direttore does not guarantee atomicity across independent resources.

## Simple-service application

```python
config = SimpleServiceDirettoreConfig(
    slot=SimpleServiceSlotConfig(
        resource_holder_factory=lambda: ResourceHolder(
            {"primary": create_session}
        ),
        uow_factory=ApplicationUnitOfWork,
    ),
    handlers=SimpleServiceHandlerConfig(
        use_case_registry=use_cases,
        query_registry=queries,
        event_registry=events,
    ),
    saga_journal=InMemorySagaJournal(),
)

director = SimpleServiceDirettoreApplication(
    config=config,
    container=container,
)

result = await director.handle(command, input=request_input)
query_result = await director.handle_query(query, input=request_input)
```

All six compatibility entry points remain:

- `handle`, `handle_by_key`, `handle_operation`
- `handle_query`, `handle_query_by_key`, `handle_query_operation`

## Transactional islands

Use an explicit lease for several sequential operations in one transaction:

```python
async with director.slot(saga_id="order-42") as lease:
    async with lease.transaction():
        first = await lease.handle(first_command, input=request_input)
        second = await lease.handle(second_command, input=request_input)
```

For an agent subgraph, pass the lease only through transient runtime context:

```python
async with director.slot() as lease:
    async with lease.transaction():
        await database_subgraph.ainvoke(
            state,
            context={"slot": lease},
        )
```

Never put `SlotLease` in durable graph state. A lease is process-local,
generation-checked, invalid after release, and restricted to sequential use.

## Provider strategies

The default is `PoolExecutionSlotProvider`, a bounded reusable pool. Use a
factory provider through explicit construction policy:

```python
director = SimpleServiceDirettoreApplication(
    config=config,
    container=container,
    slot_provider_factory=lambda slot_factory: (
        FactoryExecutionSlotProvider(slot_factory=slot_factory)
    ),
)
```

Both simple-service and modular-monolith applications support both strategies.

## Saga contract

A compensable handler returns an explicit wrapper:

```python
return SagaHandlerResult(
    result=business_result,
    compensation=CancelOrder(order_id=order.id),
)
```

Register a stable handler key and compensation type:

```python
use_cases.register(
    CreateOrder,
    CreateOrderHandler,
    saga_key="orders.create.v1",
    compensation_type=CancelOrder,
)
```

The compensation object implements `to_payload()` and `from_payload()`. Saga
records are saved before business resources commit. Compensation resolves
entries by kind and stable key, reconstructs payloads, and runs handlers in
reverse order. Compensation methods must be idempotent.

## Development

```bash
uv sync --dev
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uvx pyright src
```

See [slot_and_slot_lease.md](slot_and_slot_lease.md),
[MIGRATION.md](MIGRATION.md), and [REFACTOR_REPORT.md](REFACTOR_REPORT.md).
