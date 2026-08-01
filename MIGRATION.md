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

Use `await uow.read_session(name)` and `await uow.write_session(name)` to record
intent on the same cached named session.

## Modular coordinator

Construct coordinators with one holder:

```python
class Coordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(OrdersUow(self.resource_holder))
        self.register_query_uow(OrdersReadUow(self.resource_holder))

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

## Provider selection

The default pooled behavior requires no change. Select per-acquisition slots:

```python
slot_provider_factory=lambda factory: FactoryExecutionSlotProvider(
    slot_factory=factory
)
```

## Saga metadata

Compensable registrations now provide both `saga_key` and
`compensation_type`. Return `SagaHandlerResult`; implement an idempotent
`compensate` method and payload round-trip on the compensation type.

## Removed public abstractions

- `AbstractUseCaseResourceHolder`
- `QueryResourceHolder`
- command/query orchestration engine classes
- `ExecutionSlotPool` as an application-facing acquisition mechanism
- query-specific holder/UoW factories in application configuration

Query messages, handlers, registries, resolvers, and application entry points
remain supported.
