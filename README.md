# Direttore

Direttore is a Python 3.12 orchestration kernel for commands, events,
transactional resources, and local saga compensation.

The framework is slot-centric. One-shot application methods acquire a physical
slot directly. Explicit transactional islands acquire a `SlotLease` when they
need several operations, state validation, or manual transaction control.

## Execution model

```text
Application
  -> ExecutionSlotProvider
    -> physical Slot (one-shot calls)
    -> SlotLease -> physical Slot (transactional islands)
      -> resolve + build message
      -> optional lifecycle + trace
      -> handler + events
      -> saga journal save
      -> resource commit/rollback
    -> cleanup and release
```

## Resource setup

`ResourceHolder` is abstract. It lazily creates named resources and tracks read
or write intent, while the programmer implements `commit`, `rollback`, and
`close` for the selected infrastructure:

```python
class ApplicationResourceHolder(ResourceHolder):
    async def commit(self) -> None:
        # Apply the application's transaction policy.
        self._mark_finalized()

    async def rollback(self) -> None:
        # Roll back the application's resources.
        self._mark_finalized()

    async def close(self) -> None:
        # Close infrastructure resources. Direttore resets holder state.
        ...


holder = ApplicationResourceHolder({"primary": async_session_factory})
uow = BaseUnitOfWork(holder)

read_session = await uow.read_session("primary")
same_session = await uow.write_session("primary")

assert same_session is read_session
assert holder.commit_required["primary"] is True
```

Direttore does not prescribe commit ordering, partial-failure recovery, or
cross-resource transaction semantics. Those rules belong to the concrete
holder implementation. After closing the resources, the execution slot calls
`ResourceHolder.reset()` to clear its execution-scoped state.

The holder also owns the active `saga_id`. Opening a slot scope assigns it;
closing and resetting that scope clears it. Slots and leases only expose a view
of the holder-owned value.

## Simple-service application

```python
config: SimpleServiceDirettoreConfig[RequestInput, TraceInput] = (
    SimpleServiceDirettoreConfig(
        slot=SimpleServiceSlotConfig(
            resource_holder_factory=lambda: ApplicationResourceHolder(
                {"primary": create_session}
            ),
            uow_factory=ApplicationUnitOfWork,
        ),
        handlers=SimpleServiceHandlerConfig(
            use_case_registry=use_cases,
            event_registry=events,
        ),
        saga_journal=InMemorySagaJournal(),
    )
)

slot_creator = SimpleServiceSlotCreator(
    config=config,
    container=container,
)
slot_provider = PoolExecutionSlotProvider(
    slot_creator=slot_creator,
    initial_slot_count=5,
    max_slot_count=20,
)
director: SimpleServiceDirettoreApplication[RequestInput, TraceInput] = (
    SimpleServiceDirettoreApplication(slot_provider=slot_provider)
)

result = await director.handle(command, input=request_input)
```

`input` is optional on application, physical-slot, and lease handle methods.
When omitted, the lifecycle receives `None`.

The application exposes three one-shot entry points:

- `handle`, `handle_by_key`, `handle_operation`

Both application variants use the same stored-operation contract. The loader
receives the active `ResourceHolder` and `Span | None`, never a
service-specific UoW or modular coordinator:

```python
from direttore import KeyPayloadPair, OperationLoader, ResourceHolder
from direttore.core.tracing import Span


class StoredOperationLoader(OperationLoader):
    async def get_key_payload_pair(
        self,
        operation_id: int | str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> KeyPayloadPair:
        session = await resource.get_session()
        return await load_operation(session, operation_id)
```

## Transactional islands

Use an explicit lease for several sequential operations in one transaction:

```python
async with director.slot(saga_id="order-42") as lease:
    async with lease.transaction():
        first = await lease.handle(first_command, input=request_input)
        second = await lease.handle(second_command, input=request_input)
```

A lease exposes six use-case entry points:

- `handle`, `handle_by_key`, `handle_operation`
- `handle_cache`, `handle_by_key_cache`, `handle_operation_cache`

Physical slots expose only the three normal forms. Cache methods and cached
state belong exclusively to `SlotLease`.

The normal lease forms create and cache a lifecycle context and child span.
The cache forms reuse that state and therefore accept only their command, key
and payload, or operation ID. They are useful when several operations
intentionally share one request context and trace operation:

```python
async with director.slot() as lease:
    async with lease.transaction():
        first = await lease.handle(
            first_command,
            input=request_input,
            trace=request_trace,
        )
        second = await lease.handle_cache(second_command)
```

A cache form called before a normal lease handle is a lease-state error.

Neither form commits between lease calls. The transaction boundary commits or
rolls back once for the whole lease.

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

## Lifecycle typing

Simple-service and modular-monolith use the same lifecycle contract. A
lifecycle receives the operation input, handler config, and the active
`ResourceHolder` and `Span | None`; it does not depend on either a
simple-service UoW or a modular coordinator:

```python
from direttore import ResourceHolder, UseCaseHandlerConfig
from direttore.core.tracing import Span


class RequestLifecycle(Lifecycle[RequestInput | None, RequestContext]):
    async def create_context(
        self,
        input: RequestInput | None,
        config: UseCaseHandlerConfig,
        resource: ResourceHolder,
        span: Span | None,
    ) -> RequestContext:
        return RequestContext(input=input, resource=resource)


use_cases = UseCaseHandlerRegistry[RequestLifecycle](
    default_lifecycle=RequestLifecycle(),
)
```

Both application configurations accept that registry. When neither the
registry nor a registration provides a lifecycle, the handler receives
`lifecycle_context=None`.

The application facade, its slot creator/provider, and `SlotLease` carry the
same `InputT` and `TraceT`. Consequently, both one-shot methods and lease
methods are checked against the types selected when the application is wired.

## Provider strategies

`PoolExecutionSlotProvider` is a bounded reusable pool.
`FactoryExecutionSlotProvider` creates a physical slot for each acquisition.
Both providers expose plain-slot and lease acquisition. Choose and initialize
the provider before constructing the application:

```python
slot_creator = SimpleServiceSlotCreator(config=config, container=container)
director = SimpleServiceDirettoreApplication(
    slot_provider=FactoryExecutionSlotProvider(slot_creator=slot_creator),
)
```

Simple-service and modular-monolith use separate application facades with their
concrete slot types. Both support pooled and factory providers and share the
same transactional-slot pattern.

## Saga contract

A compensable handler returns an explicit wrapper:

```python
return SagaUseCaseHandlerResult(
    result=business_result,
    compensation=CancelOrder(order_id=order.id),
)
```

Use-case compensation messages inherit `UseCaseCommandCompensation`; event
compensation messages inherit `EventCompensation`. Compensable event handlers
return `SagaEventHandlerResult(compensation=...)`.

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
