# Modular-monolith application

The modular-monolith variant keeps bounded-context registration and UoW
boundaries explicit while executing them in one process and over one shared
`ResourceHolder`. Use it when contexts such as Warehouse and Orders need their
own application models but must participate in one local execution boundary.

Read the [core guide](README.md) first. The facade methods, lifecycle contract,
resource ownership, event timing, tracing, saga behavior, and slot providers
are shared with the simple-service variant.

## What differs from a simple service

The modular variant adds four concepts:

1. a `ModularMonolithDirettoreContext` for each bounded context;
2. one root `BaseUnitOfWork` type per context;
3. a `ModularUnitOfWorkCoordinator` that constructs and stores those UoWs over
   the slot's shared holder;
4. optional execution-scoped dependencies that replace cross-context clients
   with in-process runtime adapters.

The slot creator merges context registries for resolution and separately builds
routing tables from handler type to root UoW type. Command and handler types,
public keys, and saga keys must remain unique across all contexts.

## Define context UoWs and the coordinator

Each root UoW inherits `BaseUnitOfWork`. It can add repository-oriented methods
while delegating named resource access to the common holder:

```python
from direttore import BaseUnitOfWork, ModularUnitOfWorkCoordinator


class WarehouseUnitOfWork(BaseUnitOfWork):
    pass


class OrdersUnitOfWork(BaseUnitOfWork):
    pass


class SQLAlchemyWarehouseUnitOfWork(WarehouseUnitOfWork):
    # Construct SQLAlchemy Warehouse repositories over self.resources.
    pass


class SQLAlchemyOrdersUnitOfWork(OrdersUnitOfWork):
    # Construct SQLAlchemy Orders repositories over self.resources.
    pass


class ApplicationCoordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(
            SQLAlchemyWarehouseUnitOfWork(self.resource_holder)
        )
        self.register_use_case_uow(
            SQLAlchemyOrdersUnitOfWork(self.resource_holder)
        )
```

The application-layer `WarehouseUnitOfWork` and `OrdersUnitOfWork` types define
what handlers may use. Their concrete SQLAlchemy adapters construct and expose
the corresponding SQLAlchemy repositories. Those repositories are not
container dependencies.

The coordinator is created once per physical slot. It owns the concrete UoW
objects but not a separate transaction or resource cache. Both UoWs above point
to the same holder, so named resources and commit intent remain unified for the
execution.

Register each concrete UoW type only once. The type supplied in a context must
match a type registered by the coordinator.

## Define bounded contexts

Give each context its own registries, preferably with a meaningful
`source_name`:

```python
from direttore import (
    EventHandlerRegistry,
    ModularMonolithDirettoreContext,
    UseCaseHandlerRegistry,
)

warehouse_use_cases = UseCaseHandlerRegistry(source_name="warehouse")
warehouse_events = EventHandlerRegistry(source_name="warehouse")

orders_use_cases = UseCaseHandlerRegistry(source_name="orders")
orders_events = EventHandlerRegistry(source_name="orders")

warehouse_context = ModularMonolithDirettoreContext(
    use_case_registry=warehouse_use_cases,
    event_registry=warehouse_events,
    use_case_root_uow_type=SQLAlchemyWarehouseUnitOfWork,
)

orders_context = ModularMonolithDirettoreContext(
    use_case_registry=orders_use_cases,
    event_registry=orders_events,
    use_case_root_uow_type=SQLAlchemyOrdersUnitOfWork,
)
```

`event_registry` is optional. `use_case_root_uow_type` must inherit
`BaseUnitOfWork`.

An event handler registered inside a context is routed to that context's root
UoW. Events are still published to one execution queue, so events can connect
contexts without importing their internal repositories.

## Configure the modular slot creator

```python
from direttore import (
    Container,
    FactoryExecutionSlotProvider,
    ModularMonolithDirettoreApplication,
    ModularMonolithSlotConfig,
    ModularMonolithSlotCreator,
    ModularMonolithSlotCreatorConfig,
)

config = ModularMonolithSlotCreatorConfig(
    slot=ModularMonolithSlotConfig(
        resource_holder_factory=holder_factory,
        coordinator_factory=lambda holder: ApplicationCoordinator(
            resource_holder=holder
        ),
    ),
    contexts=[warehouse_context, orders_context],
)

slot_creator = ModularMonolithSlotCreator(
    config=config,
    container=Container(),
)
provider = FactoryExecutionSlotProvider(slot_creator=slot_creator)
application = ModularMonolithDirettoreApplication(slot_provider=provider)
application.validate()
```

At least one context is required.

## Configuration reference

### `ModularMonolithSlotConfig`

| Field | Required | Meaning |
| --- | --- | --- |
| `resource_holder_factory` | yes | Zero-argument concrete holder factory. |
| `coordinator_factory` | yes | Callable receiving that holder and returning the configured coordinator. |

### `ModularMonolithDirettoreContext`

| Field | Required | Meaning |
| --- | --- | --- |
| `use_case_registry` | yes | Use cases owned by this context. |
| `use_case_root_uow_type` | yes | Root UoW used by this context's use-case and event handlers. |
| `event_registry` | no | Events handled by this context. |

### `ModularMonolithUseCaseExecutionConfig`

| Field | Default | Meaning |
| --- | --- | --- |
| `operation_loader` | `None` | Resolves stored operation IDs to key/payload pairs. |
| `max_processed_events` | `100` | Maximum events collected in one drain batch. |

### `ModularMonolithSlotCreatorConfig`

The top-level configuration combines the slot config, non-empty list of
contexts, optional `SpanFactory`, optional `SagaJournal`, and optional use-case
execution settings.

## Cross-context invocation

Sometimes an Orders handler should call a Warehouse use case synchronously and
receive its result. Model that dependency as an explicit context connector.

### Naming and ownership

Prefer a name ending in `ContextClient`, such as `WarehouseContextClient`, for
an outbound port used by one context to call another. `ContextConnector` is
also acceptable when the abstraction represents a more general bidirectional
or transport-oriented connection. Avoid the bare name `WarehouseContext`: it
is easily confused with the target context's
`ModularMonolithDirettoreContext` configuration object.

The calling context owns the port and its adapter:

```text
contexts/orders/
  application/ports/warehouse_context_client.py  # outbound port
  adapters/in_process_warehouse_context_client.py # in-process adapter
```

An Orders handler depends only on `WarehouseContextClient`. The adapter
translates that interface into the target context's public commands and
results. Neither the handler nor adapter may reach into the Warehouse UoW or
repositories.

### Direct runtime client

For a small context boundary, the in-process client can invoke the modular
runtime directly. This is the pattern used by the runnable example:

```python
from typing import Protocol

from direttore import ModularMonolithExecutionRuntime
from direttore.core.tracing import Span


class WarehouseContextClient(Protocol):
    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        ...


class InProcessWarehouseContextClient:
    def __init__(self, runtime: ModularMonolithExecutionRuntime) -> None:
        self._runtime = runtime

    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        result = await self._runtime.invoke(
            ReserveStock(product_id=product_id, quantity=quantity),
            span=span,
        )
        if not isinstance(result, StockBalance):
            raise TypeError("ReserveStock must return StockBalance")
        return result.quantity
```

Register the execution-scoped factory:

```python
from direttore import ModularMonolithExecutionDependencyRegistry

execution_dependencies = ModularMonolithExecutionDependencyRegistry()
execution_dependencies.register(
    dependency_type=WarehouseContextClient,
    factory=lambda context: InProcessWarehouseContextClient(context.runtime),
)

slot_creator = ModularMonolithSlotCreator(
    config=config,
    container=container,
    execution_dependencies_registry=execution_dependencies,
)
```

When the resolver creates a handler whose constructor requests
`WarehouseContextClient`, it injects the adapter for the current execution
runtime. That runtime invocation:

- resolves the nested command from the merged use-case registry;
- routes it to the Warehouse UoW;
- reuses the active event queue;
- passes through the active lifecycle context;
- can create a child span when the caller supplies its current span.

For that final point, the outer handler should pass `context.span` to the client
when it wants the nested invocation represented as a child trace. The runtime
never stores the active span.

Runtime invocation is an internal command call. It invokes the nested handler
inside the current slot; it does not start a new application facade call or a
new top-level transaction.

### Context-owned facade

For a larger modular monolith, prefer making the target context's callable
surface explicit in one inbound adapter. Warehouse can own a
`WarehouseContextFacade`, while Orders still owns the outbound
`WarehouseContextClient` port and its in-process implementation:

```text
contexts/warehouse/
  adapters/inbound/context_facade.py
contexts/orders/
  application/ports/warehouse_context_client.py
  adapters/in_process_warehouse_context_client.py
```

The facade receives the active runtime and owns translation from its public
methods to Warehouse commands:

```python
class WarehouseContextFacade:
    def __init__(self, runtime: ModularMonolithExecutionRuntime) -> None:
        self._runtime = runtime

    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        result = await self._runtime.invoke(
            ReserveStock(product_id=product_id, quantity=quantity),
            span=span,
        )
        if not isinstance(result, StockBalance):
            raise TypeError("ReserveStock must return StockBalance")
        return result.quantity


class InProcessWarehouseContextClient:
    def __init__(self, facade: WarehouseContextFacade) -> None:
        self._facade = facade

    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        return await self._facade.reserve(
            product_id,
            quantity,
            span=span,
        )
```

Construct both execution-scoped objects from the active runtime:

```python
execution_dependencies.register(
    dependency_type=WarehouseContextClient,
    factory=lambda context: InProcessWarehouseContextClient(
        WarehouseContextFacade(context.runtime)
    ),
)
```

This extra layer is useful when many contexts call Warehouse. Inspecting the
Warehouse inbound facade reveals the complete in-process API it exposes;
searching for `WarehouseContextClient` reveals which contexts consume it. The
facade also centralizes command construction, result validation, and future
compatibility mapping. For a small system, direct runtime invocation inside the
context client remains valid and is intentionally used by the current example.

## Cross-context events versus direct invocation

Choose based on the dependency semantics:

- Use `runtime.invoke` through an interface when the caller needs a result or
  failure before it can continue. Reserving stock while placing an order is a
  typical example.
- Publish an event when the fact is already true and downstream reactions may
  be handled without a direct return value. Recording an order audit entry is a
  typical example.

Do not use a context's repository or UoW directly from another context. That
would bypass routing and couple application models.

## One-shot and leased execution

The public facade matches the simple-service facade:

```python
order = await application.handle(
    PlaceOrder(order_id="O-100", product_id="P-100", quantity=2),
    input=request_input,
)
```

Use `handle_by_key` and `handle_operation` for payload-driven calls. Use a lease
when several top-level operations must commit together:

```python
async with application.slot(saga_id="order-O-100") as lease:
    async with lease.transaction():
        await lease.handle(RegisterProduct("P-100", "Keyboard"))
        await lease.handle(ReceiveStock("P-100", 10))
        await lease.handle(PlaceOrder("O-100", "P-100", 2))
```

Nested runtime calls and events share this boundary. The lease drains events
after each handle but commits the shared holder only once.

## Modular project structure

Organize each bounded context independently, then compose them from the outer
bootstrap layer:

```text
src/warehouse_example/
  contexts/
    warehouse/
      adapters/
      application/
        architecture.py
        events/
        ports/
        use_cases/
      domain/
      container.py
      context.py
    orders/
      adapters/
      application/
        architecture.py
        events/
        ports/
        use_cases/
      domain/
      container.py
      context.py
  shared/
    lifecycle.py
    resources/
  bootstrap/
    application.py
    config.py
    container.py
    contexts.py
    coordinator.py
    execution_dependencies.py
    runtime.py
```

Inside each context, `application/architecture.py` owns that context's
`UseCaseHandlerRegistry`, optional `EventHandlerRegistry`, and typed context
aliases. Those aliases should cover the regular use-case context, event
context, and `SagaCompensationContext` specialized with the context UoW and
span. The context's use-case/event modules register themselves there.
`context.py` explicitly imports registration modules and exports one
`ModularMonolithDirettoreContext`. `bootstrap/contexts.py` collects those
objects into the list passed to `ModularMonolithSlotCreatorConfig`.

`container.py` binds application-lifetime ports to adapters. Runtime-backed
cross-context adapters are different: they are registered by
`bootstrap/execution_dependencies.py`, because they belong to the current
execution slot.

Only public commands, results, events, and client interfaces should cross a
context boundary. Context-specific repositories, entities, and UoWs stay
internal. Shared lifecycle/resource infrastructure lives under `shared/`, not
inside an arbitrary context.

The current API has no query registry or query UoW routing. Read operations
such as `GetStock` and `GetOrder` are normal use cases whose handlers request
read access from their context UoW.

See [Recommended project structure](project-structure.md) for the full tree,
file-by-file responsibilities, import order, and a migration table for the
legacy language-learning-platform structure.

## Common mistakes

- **Using one UoW type for every context:** that removes the routing boundary
  that the modular variant is intended to provide.
- **Forgetting to register a context UoW in the coordinator:** routing can find
  the type, but execution cannot retrieve its instance.
- **Registering overlapping commands or keys:** all context registries are
  merged and must be globally unambiguous.
- **Copying legacy query context fields:** current modular contexts contain one
  use-case registry/root UoW pair and an optional event registry.
- **Putting runtime adapters in the global container:** an adapter points at a
  concrete slot runtime and must be built by the execution dependency registry.
- **Calling another context's repository:** depend on an interface and invoke a
  command or publish an event instead.
- **Opening separate holders per context:** the coordinator and all UoWs must
  use the holder passed to the slot's coordinator factory.
- **Storing the active span in the runtime:** pass the current span explicitly
  to nested invocation when required.
