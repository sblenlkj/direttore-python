# Simple-service application

The simple-service variant runs every use-case and event handler with one root
unit-of-work type. It is suitable when the application has one transactional
model or does not need bounded-context-specific UoW routing.

Read the [core guide](README.md) first for the contracts shared by both
application variants.

## What must be supplied

A simple-service application needs:

- a concrete `ResourceHolder` factory;
- a `BaseUnitOfWork` factory;
- a populated `UseCaseHandlerRegistry`;
- an optional `EventHandlerRegistry`;
- a `Container` for application-lifetime handler dependencies;
- optional operation loading, tracing, and saga components;
- a slot provider and application facade.

## Minimal composition

Assume `ApplicationResourceHolder`, concrete
`SQLAlchemyWarehouseUnitOfWork`, the messages, handlers, registries, resource
factory, `StockReceiptClient` port, and its `HttpStockReceiptClient` adapter
have already been defined:

```python
from direttore import (
    Container,
    FactoryExecutionSlotProvider,
    SimpleServiceDirettoreApplication,
    SimpleServiceHandlerConfig,
    SimpleServiceSlotConfig,
    SimpleServiceSlotCreator,
    SimpleServiceSlotCreatorConfig,
)

container = Container.from_mapping(
    {
        StockReceiptClient: HttpStockReceiptClient(
            base_url=stock_receipt_base_url,
        ),
    }
)

config = SimpleServiceSlotCreatorConfig(
    slot=SimpleServiceSlotConfig(
        resource_holder_factory=lambda: ApplicationResourceHolder(
            {"primary": session_factory}
        ),
        uow_factory=SQLAlchemyWarehouseUnitOfWork,
    ),
    handlers=SimpleServiceHandlerConfig(
        use_case_registry=use_cases,
        event_registry=events,
    ),
)

slot_creator = SimpleServiceSlotCreator(
    config=config,
    container=container,
)
slot_provider = FactoryExecutionSlotProvider(slot_creator=slot_creator)
application = SimpleServiceDirettoreApplication(slot_provider=slot_provider)
application.validate("validation_results.md")
```

The optional path produces a context-grouped report of all use-case and event
handlers, their constructor port-to-adapter bindings, and whether each handler
is cached. Calling `application.validate()` without a path performs the same
validation without writing a report.

The important ownership boundary is that `resource_holder_factory` returns a
new holder for each newly created physical slot. The UoW factory receives that
holder and should return a UoW delegating resource access to it.

## Configuration reference

### `SimpleServiceSlotConfig`

| Field | Required | Meaning |
| --- | --- | --- |
| `resource_holder_factory` | yes | Zero-argument factory for a concrete holder. |
| `uow_factory` | yes | Callable receiving the holder and returning the service UoW. |

### `SimpleServiceHandlerConfig`

| Field | Required | Meaning |
| --- | --- | --- |
| `use_case_registry` | yes | All use-case registrations for the service. |
| `event_registry` | no | Event registrations; omit it if the service dispatches no events. |

### `SimpleServiceUseCaseExecutionConfig`

| Field | Default | Meaning |
| --- | --- | --- |
| `operation_loader` | `None` | Resolves stored operation IDs to key/payload pairs. |
| `max_processed_events` | `100` | Maximum events collected in one drain batch. |

### `SimpleServiceSlotCreatorConfig`

This is the top-level immutable configuration. It combines:

- `slot` — `SimpleServiceSlotConfig`;
- `handlers` — `SimpleServiceHandlerConfig`;
- `span_factory` — optional `SpanFactory`;
- `saga_journal` — optional `SagaJournal`;
- `use_case_execution` — optional execution settings with safe defaults.

An extended setup looks like this:

```python
from direttore import (
    InMemorySagaJournal,
    SimpleServiceUseCaseExecutionConfig,
)
from direttore.core.tracing import LoggingSpanFactory

config = SimpleServiceSlotCreatorConfig(
    slot=SimpleServiceSlotConfig(
        resource_holder_factory=holder_factory,
        uow_factory=SQLAlchemyWarehouseUnitOfWork,
    ),
    handlers=SimpleServiceHandlerConfig(
        use_case_registry=use_cases,
        event_registry=events,
    ),
    span_factory=LoggingSpanFactory(),
    saga_journal=InMemorySagaJournal(),
    use_case_execution=SimpleServiceUseCaseExecutionConfig(
        operation_loader=stored_operation_loader,
        max_processed_events=200,
    ),
)
```

`InMemorySagaJournal` is useful for tests and demonstrations. Production code
usually needs a durable implementation appropriate to its recovery model.

## Choosing a provider

Use the factory provider when each acquisition should create and dispose a
slot:

```python
provider = FactoryExecutionSlotProvider(slot_creator=slot_creator)
```

Use the pool provider to reuse cleaned slots and cap concurrency:

```python
from direttore import PoolExecutionSlotProvider

provider = PoolExecutionSlotProvider(
    slot_creator=slot_creator,
    initial_slot_count=5,
    max_slot_count=20,
)
```

Pooled slots retain their constructed UoW and framework objects, but the slot
closes resources and resets execution-scoped holder state before reuse.
Repositories must therefore resolve live sessions lazily from the current UoW
or holder instead of retaining an old session.

## Executing the application

Normal application code uses one-shot facade methods:

```python
balance = await application.handle(
    ReceiveStock(product_id="P-100", quantity=10),
    input=RequestInput(actor_id="worker-7"),
)
```

The application acquires a slot, performs the full use-case pipeline, commits
or rolls back, closes resources, and releases the slot. `handle_by_key` and
`handle_operation` provide payload-driven alternatives, as described in the
[core guide](README.md#running-use-cases).

For several operations that must commit together, use a lease:

```python
async with application.slot() as lease:
    async with lease.transaction():
        await lease.handle(RegisterProduct("P-100", "Keyboard"))
        await lease.handle(ReceiveStock("P-100", 10))
```

The lease is sequential. Do not pass it to concurrent tasks or retain it after
the outer context exits.

## Simple-service project structure

A small service should use the same adapters/application/domain/bootstrap
boundaries as a modular monolith, but without modular context objects:

```text
src/
  simple_service/
    adapters/
      outbound/
        in_memory/
          repositories.py
          unit_of_work.py
    application/
      architecture.py
      events/
      ports/
        repositories.py
        unit_of_work.py
      use_cases/
        register_product.py
        receive_stock.py
        get_stock.py
        place_order.py
    domain/
      entities/
        product.py
        order.py
    shared/
      lifecycle.py
      resources/
        resource_holder.py
    bootstrap/
      application.py
      config.py
      container.py
      registries.py
```

`application/architecture.py` owns the service's use-case and optional event
registries plus handler-context type aliases. Use-case and event modules import
those registry objects and register their handlers. `bootstrap/registries.py`
imports the registration modules deliberately before the slot creator is
built.

If a larger simple service keeps `contexts/warehouse` and `contexts/orders`
for code ownership, each context may have its own `application/architecture.py`.
The simple-service bootstrap then uses `UseCaseHandlerRegistry.merge_many` and
`EventHandlerRegistry.merge_many` and supplies one application UoW to every
handler. It does not create `ModularMonolithDirettoreContext` objects or a
modular coordinator.

Read operations such as `GetStock` stay under `application/use_cases/`. The
current framework has no query registry, query handler, query UoW, or separate
query resource holder. The handler uses the normal UoW and asks it for read
access.

See [Recommended project structure](project-structure.md) for complete file
responsibilities, import direction, registration loading, and the mapping from
the earlier language-learning-platform layout.

## Common mistakes

- **Committing in a handler:** handlers request write access; the slot commits.
- **Putting sessions in `Container`:** sessions are execution-scoped and belong
  in `ResourceHolder`.
- **Putting repositories in `Container`:** the concrete UoW constructs its
  repository adapters and exposes them through `context.uow`.
- **Constructing handlers manually:** register handler types and let the
  resolver inject their long-lived dependencies.
- **Forgetting the registration import:** populate registries before creating
  the slot creator.
- **Copying the legacy query folders:** represent reads as registered use cases
  with read-oriented UoW methods.
- **Reusing external keys accidentally:** public `key` and `saga_key` values
  must be stable and unique.
- **Calling `handle_operation` without a loader:** configure
  `SimpleServiceUseCaseExecutionConfig.operation_loader` first.
- **Sharing a lease concurrently:** one lease permits sequential use only.
- **Using cached lease methods first:** initialize cache state with a normal
  lease handle call.
