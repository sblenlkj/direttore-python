# Recommended project structure

Direttore does not require a particular filesystem layout, but applications
benefit from a consistent boundary between domain code, application
orchestration, infrastructure adapters, shared execution infrastructure, and
the composition root.

This guide adapts the structure used by the earlier language-learning-platform
project to the current Direttore API. The earlier project is a structural
reference only: it targets an older API and is not expected to compile against
the current package.

## Canonical modular-monolith tree

The recommended full structure is:

```text
src/
  warehouse_example/
    __init__.py
    contexts/
      warehouse/
        __init__.py
        context.py
        container.py
        adapters/
          __init__.py
          orders_context.py            # optional cross-context adapter
          inbound/                     # optional HTTP/CLI/worker adapters
          outbound/
            __init__.py
            in_memory/
              __init__.py
              models.py
              repositories.py
              unit_of_work.py
        application/
          __init__.py
          architecture.py
          errors.py
          events/
            __init__.py
            product_registered.py
            stock_received.py
            stock_reserved.py
          ports/
            __init__.py
            repositories.py
            unit_of_work.py
            orders_context.py          # only when Warehouse calls Orders
          use_cases/
            __init__.py
            register_product.py
            receive_stock.py
            get_stock.py
            reserve_stock.py
            release_stock.py
        domain/
          __init__.py
          entities/
            __init__.py
            product.py
      orders/
        __init__.py
        context.py
        container.py
        adapters/
          __init__.py
          warehouse_context.py         # runtime-backed implementation
          inbound/
          outbound/
            __init__.py
            in_memory/
              __init__.py
              models.py
              repositories.py
              unit_of_work.py
        application/
          __init__.py
          architecture.py
          errors.py
          events/
            __init__.py
            order_placed.py
            order_cancelled.py
          ports/
            __init__.py
            repositories.py
            unit_of_work.py
            warehouse_context.py
          use_cases/
            __init__.py
            place_order.py
            get_order.py
            cancel_order.py
        domain/
          __init__.py
          entities/
            __init__.py
            order.py
    shared/
      __init__.py
      lifecycle.py
      resources/
        __init__.py
        resource_holder.py
        in_memory.py
      tracing/
        __init__.py
    bootstrap/
      __init__.py
      application.py
      config.py
      container.py
      contexts.py
      coordinator.py
      execution_dependencies.py
      runtime.py                     # optional type alias/helper
```

Use fewer files when a context is small. The important part is ownership, not
creating empty directories. For example, an in-memory demonstration may keep
its models, repositories, and UoW in one adapter module until they become large
enough to split.

## Dependency direction

The intended imports point inward:

```text
domain
  <- application ports and use cases
    <- adapters
      <- context/container composition
        <- application bootstrap
```

- `domain/` imports neither Direttore nor infrastructure.
- `application/` may import Direttore contracts, its own domain, and its own
  ports. It does not import concrete database or network adapters.
- `adapters/` implement application ports and may import external libraries.
- `context.py` and `container.py` are context-level composition modules and may
  import concrete adapters.
- `bootstrap/` is the only layer that knows all contexts and constructs the
  complete application.
- `shared/` contains genuine cross-context infrastructure or policy, not
  miscellaneous domain objects.

## Responsibilities inside one context

### `domain/`

This folder owns business state and invariants: entities, value objects, and
domain-specific rules. A `Product` or `Order` belongs here. Direttore commands,
handler contexts, registries, resource holders, and database models do not.

### `application/use_cases/`

Each module contains one closely related command, result, and handler. Read
operations are use cases too. For example, `GetStock` inherits
`UseCaseCommand`, and `GetStockHandler` uses a read session through its UoW.

There is no current `Query`, `QueryHandler`, or `QueryHandlerRegistry` API.
Do not recreate a query execution path in the project. Separate read and write
repository methods if useful, but route both through registered use cases.

Handlers implement `handle`, not the legacy `__call__` method.

### `application/events/`

Each module defines an event and its handlers, or a small cohesive event group.
Handlers register with the context's event registry from
`application/architecture.py`.

If an event is part of a context's public language, re-export only its message
type from a deliberate public module. Do not expose its concrete handler or
repository implementation to other contexts.

### `application/ports/`

Ports describe dependencies required by application handlers:

- repository protocols;
- the context's root UoW type;
- outbound publisher/client interfaces;
- interfaces representing another bounded context.

The root UoW inherits `BaseUnitOfWork`. In the current design it covers both
read and write use cases and delegates all live resource access to the unified
`ResourceHolder`.

### `application/architecture.py`

This is the stable center of a context's Direttore integration. It creates the
registries and, when useful, context-specific handler-context aliases:

```python
from typing import TypeAlias

from direttore import (
    EventHandlerContext,
    EventHandlerRegistry,
    SagaCompensationContext,
    UseCaseHandlerContext,
    UseCaseHandlerRegistry,
)
from direttore.core.tracing import Span

from warehouse_example.contexts.warehouse.application.ports.unit_of_work import (
    WarehouseUnitOfWork,
)
from warehouse_example.shared.lifecycle import WarehouseRequestContext

WarehouseUseCaseHandlerContext: TypeAlias = UseCaseHandlerContext[
    WarehouseUnitOfWork,
    WarehouseRequestContext,
    Span,
]
WarehouseEventHandlerContext: TypeAlias = EventHandlerContext[
    WarehouseUnitOfWork,
    Span,
]
WarehouseSagaCompensationContext: TypeAlias = SagaCompensationContext[
    WarehouseUnitOfWork,
    Span,
]

use_case_registry = UseCaseHandlerRegistry(source_name="warehouse")
event_registry = EventHandlerRegistry(source_name="warehouse")
```

This module should be cheap and deterministic to import. It owns registry
objects but should not import every use-case module itself. Registration loading
is made explicit by `context.py` or a dedicated registration-import module.

If a context has no event handlers, omit its event registry rather than
creating an unused object.

### Registration modules

A use-case module imports `use_case_registry` from `architecture.py` and uses
`register` or `decorator_register`. An event module follows the same pattern
with `event_registry`.

Package `__init__.py` files should not accidentally become magical scanners.
Either make their registration imports explicit, or let `context.py` import
each registration module directly. The project should have one obvious place
where readers can see which modules are loaded for registration.

### `adapters/`

Adapters implement the ports defined by the application layer.

- `adapters/outbound/in_memory/` contains the first example's persistence
  models, repository adapters, and concrete context UoW.
- A production project might replace `in_memory/` with `relational_db/`,
  `redis/`, or a remote client without changing handlers.
- `adapters/inbound/` is optional. It may contain HTTP, CLI, scheduled-job, or
  message-consumer adapters that translate external input into application
  facade calls.
- A file such as `adapters/in_process_warehouse_context_client.py` implements
  an outbound `WarehouseContextClient` port by invoking the current modular
  runtime. Because it is tied to one physical execution, the bootstrap
  execution-dependency registry constructs it. For a larger public surface,
  that client can delegate to a target-owned
  `adapters/inbound/context_facade.py`.

### `container.py`

The context container binds application-lifetime port types to concrete
adapters:

```python
from direttore import Container


def build_warehouse_container(config: ApplicationConfig) -> Container:
    container = Container()
    container.set(Clock, SystemClock())
    container.set(StockAuditPublisher, FileStockAuditPublisher(config.audit_path))
    return container
```

Do not put repositories, sessions, holders, context UoWs, runtime-backed
cross-context adapters, or request state in this container. Concrete UoWs
assemble their repository adapters; the container binds other application
ports such as clients and publishers.

### `context.py`

This module completes one modular context. It deliberately loads registrations
and exports one `ModularMonolithDirettoreContext`:

```python
from direttore import ModularMonolithDirettoreContext

from warehouse_example.contexts.warehouse.application.architecture import (
    event_registry,
    use_case_registry,
)
from warehouse_example.contexts.warehouse.adapters.outbound.in_memory.unit_of_work import (
    InMemoryWarehouseUnitOfWork,
)

# Explicit imports execute decorators and populate the registries.
from warehouse_example.contexts.warehouse.application import events as _events
from warehouse_example.contexts.warehouse.application import use_cases as _use_cases

warehouse_context = ModularMonolithDirettoreContext(
    use_case_registry=use_case_registry,
    event_registry=event_registry,
    use_case_root_uow_type=InMemoryWarehouseUnitOfWork,
)
```

For this pattern to work, the `events` and `use_cases` package initializers must
explicitly import their registration modules. An equally valid and often more
visible option is for `context.py` to import every module directly.

`context.py` is a composition module, so importing a concrete root UoW here is
acceptable. The use-case handlers themselves still depend on application
ports.

## Shared layer

The shared layer owns execution concerns used by more than one context:

- the concrete unified `ResourceHolder`;
- resource/session factories;
- the common lifecycle input and context;
- common trace input or span-factory integration;
- genuinely generic identifiers or clock interfaces, if appropriate.

The current framework uses one holder for both read and write operations. Do
not retain legacy `query_resource_holder.py` and
`use_case_resource_holder.py` modules. Use one `resource_holder.py`, and let
`read_session` versus `write_session` express intent through the context UoW.

Avoid putting Warehouse or Orders entities in `shared/`. Cross-context
communication should use public commands, results, events, or application
ports, not a shared domain-model bucket.

## Bootstrap responsibilities

Bootstrap modules compose the process. They should contain wiring, not business
rules.

### `bootstrap/config.py`

Defines runtime/environment configuration such as database URLs, file paths,
provider sizes, and tracing settings. This application configuration is
distinct from Direttore's immutable slot-creator configuration classes.

### `bootstrap/container.py`

Calls each context's container builder and combines them with
`Container.merge_many`. If two context containers bind the same type, the later
container wins, so shared bindings should be intentional.

### `bootstrap/contexts.py`

Imports each context object and exposes the ordered context list:

```python
from warehouse_example.contexts.orders.context import orders_context
from warehouse_example.contexts.warehouse.context import warehouse_context

MODULAR_CONTEXTS = [
    warehouse_context,
    orders_context,
]
```

Keeping this list separate makes the installed bounded contexts visible
without opening the full application builder.

### `bootstrap/coordinator.py`

Defines the concrete `ModularUnitOfWorkCoordinator`. Its `register()` method
constructs one root UoW for every configured context over
`self.resource_holder`:

```python
class ApplicationUnitOfWorkCoordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(
            InMemoryWarehouseUnitOfWork(self.resource_holder)
        )
        self.register_use_case_uow(
            InMemoryOrdersUnitOfWork(self.resource_holder)
        )
```

There is no query-UoW registration in the current coordinator.

### `bootstrap/execution_dependencies.py`

Creates the `ModularMonolithExecutionDependencyRegistry` and registers
per-execution cross-context adapters. For example, it binds the Orders
`WarehouseContextClient` port to an `InProcessWarehouseContextClient`
constructed with `context.runtime`.

Name outbound context ports with a `ContextClient` suffix, or
`ContextConnector` for a more general transport-oriented abstraction. Place
the port under the calling context's `application/ports/` and its in-process
implementation under that context's `adapters/`. A large target context may
add an inbound `adapters/inbound/context_facade.py`; the in-process client then
delegates to that facade instead of constructing target commands itself.

These adapters must not go in the regular container because they reference the
runtime of the currently acquired slot.

### `bootstrap/runtime.py`

Optional convenience module for a project-specific runtime type alias or small
adapter helpers. It should not hold global active runtime, lifecycle, holder,
lease, or span state.

### `bootstrap/application.py`

The final composition root:

1. reads `ApplicationConfig`;
2. prepares external infrastructure;
3. builds the unified holder factory;
4. builds the application container;
5. imports the modular context list;
6. builds the UoW coordinator factory;
7. builds execution dependencies;
8. creates `ModularMonolithSlotCreatorConfig`;
9. constructs `ModularMonolithSlotCreator`;
10. chooses a factory or pool slot provider;
11. constructs `ModularMonolithDirettoreApplication`;
12. calls application validation;
13. returns an application wrapper that can also close process-level resources.

No handler registry should be created here. Contexts own their registries;
bootstrap merely installs the context objects.

## Simple-service adaptation

A simple service can keep the same architectural layers without pretending
that Direttore routes bounded contexts. There are two reasonable layouts.

For one small domain, omit `contexts/`:

```text
src/simple_service/
  adapters/
  application/
    architecture.py
    events/
    ports/
    use_cases/
  domain/
  shared/
  bootstrap/
```

For a service that still groups Warehouse and Orders code, retain
`contexts/warehouse` and `contexts/orders`, but the simple-service bootstrap
must explicitly merge their registries and provide one root application UoW:

```python
use_cases = UseCaseHandlerRegistry.merge_many(
    [warehouse_use_cases, orders_use_cases],
    source_name="simple_service",
)
events = EventHandlerRegistry.merge_many(
    [warehouse_events, orders_events],
    source_name="simple_service",
)
```

In that layout, per-context `context.py` files are unnecessary because
`ModularMonolithDirettoreContext` is not used. A small
`bootstrap/registries.py` can load registration modules and perform the merge.
The single `SimpleServiceSlotConfig.uow_factory` supplies the UoW used by every
handler.

## Migration from the legacy reference

The language-learning-platform structure contains concepts removed or renamed
by the current framework. Translate them as follows:

| Legacy reference | Current Direttore project |
| --- | --- |
| `application/orchestration.py` | Prefer `application/architecture.py`; keep use-case/event registries and context aliases there. |
| `application/queries/` | Move read operations into `application/use_cases/` as `UseCaseCommand` handlers. |
| `QueryHandlerRegistry` | Remove; register read commands in `UseCaseHandlerRegistry`. |
| `QueryHandlerContext` | Remove; use `UseCaseHandlerContext` and a read-oriented UoW method. |
| Separate query/use-case UoWs | One root context UoW with read and write capabilities. |
| Separate query/use-case resource holders | One concrete `ResourceHolder`. |
| `query_registry` and `query_root_uow_type` on a context | Remove; current context has `use_case_registry`, `use_case_root_uow_type`, and optional `event_registry`. |
| Handler `__call__` | Implement asynchronous `handle`. |
| `ModularMonolithDirettoreConfig` | `ModularMonolithSlotCreatorConfig`. |
| Application constructed directly from config/container/pool sizes | Construct slot config, slot creator, provider, then application facade. |
| Framework-specific auth config | Put request/auth policy in a `Lifecycle` and `UseCaseHandlerConfig` policy. |
| Framework tracing config object | Supply a `SpanFactory` on the slot-creator config. |

Copy the ownership boundaries and composition layers from the reference, not
its obsolete imports or initialization code.

## Import and startup order

Circular imports are easiest to avoid when startup follows one direction:

1. domain and port types load;
2. `application/architecture.py` creates empty registries;
3. handler modules import those registries and register themselves;
4. each modular `context.py` imports the handler modules and exposes its
   configured context;
5. `bootstrap/contexts.py` collects context objects;
6. bootstrap builds containers, holder/coordinator factories, slot creator,
   provider, and facade.

Do not import `bootstrap.application` from a handler, port, domain object, or
adapter. Bootstrap sits at the outer edge and depends on them, never the other
way around.
