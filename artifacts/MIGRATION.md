# Slot-centric migration guide

## Resource holders

Replace separate command/query holders:

```python
# before
SimpleServiceSlotConfig(
    use_case_resource_holder_factory=create_write_holder,
    use_case_uow_factory=create_write_uow,
    query_resource_holder_factory=create_read_holder,
    query_uow_factory=create_read_uow,
)
```

with one holder and UoW factory:

```python
SimpleServiceSlotConfig(
    resource_holder_factory=create_resource_holder,
    uow_factory=create_uow,
)
```

`ResourceHolder` is now abstract. Implement `commit`, `rollback`, and `close`
in the application infrastructure holder. Use `_mark_finalized()` after commit
or rollback. `close()` only closes infrastructure resources; the execution slot
calls the public `reset()` method afterward.

Use `await uow.read_session(name)` and `await uow.write_session(name)` to record
intent on the same cached named session.

## Modular coordinator

Construct coordinators with one holder:

```python
class Coordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(OrdersUow(self.resource_holder))

coordinator = Coordinator(resource_holder=holder)
```

## Explicit transactions

Application methods still isolate one call automatically. Code that needs
several operations in one local transaction should acquire a lease:

```python
async with director.slot() as lease:
    async with lease.transaction():
        await lease.handle(first, input=context)
        await lease.handle(second, input=context)
```

Do not run `asyncio.gather` with one lease.

If a sequential transactional island should reuse the first operation's
lifecycle context and span, use the cache forms:

```python
async with director.slot() as lease:
    async with lease.transaction():
        await lease.handle(first, input=context, trace=trace)
        await lease.handle_by_key_cache(key, payload)
```

The lease API has six use-case methods: the three normal forms and the three
`*_cache` forms. None commits between calls.

## Provider selection

Slot construction is now explicit and lives outside the application facade.
Create the service-specific creator, choose a provider, and inject the provider:

```python
slot_creator = SimpleServiceSlotCreator(config=config, container=container)
slot_provider = FactoryExecutionSlotProvider(
    slot_creator=slot_creator
)
director = SimpleServiceDirettoreApplication(slot_provider=slot_provider)
```

Choose the application facade and slot creator for the execution model, inject
the creator into a provider, and pass that provider to the application. The
simple-service and modular-monolith facades share the same transaction pattern
but preserve their concrete slot types.

## Saga metadata

Compensable registrations now provide both `saga_key` and
`compensation_type`. Use `UseCaseCommandCompensation` for use-case handlers and
`EventCompensation` for event handlers. Return `SagaUseCaseHandlerResult` from
compensable use cases or `SagaEventHandlerResult` from compensable event
handlers; implement an idempotent `compensate` method and payload round-trip on
the compensation type.

## Removed public abstractions

- `AbstractUseCaseResourceHolder`
- `QueryResourceHolder`
- command/query orchestration engine classes
- `ExecutionSlotPool` as an application-facing acquisition mechanism
- query-specific holder/UoW factories in application configuration

The query API was removed from both core and application. Remove query message,
handler, lifecycle, registry, resolver, routing, and runtime usage from clients.
