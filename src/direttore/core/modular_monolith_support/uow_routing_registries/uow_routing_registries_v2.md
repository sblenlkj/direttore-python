# Unit of Work Routing Registries v2

This document describes the `core/modular_monolith_support/uow_routing_registries` module.

The module is used only by modular monolith execution mode. It does not replace the core handler registries or handler resolvers. Its only responsibility is to map a resolved **handler type** to the root `BaseUnitOfWork` type that should be used when executing that handler.

```text
core/modular_monolith_support/uow_routing_registries/
  base_uow_routing_registry.py
  use_case_uow_routing_registry.py
  query_uow_routing_registry.py
  event_uow_routing_registry.py
```

## Problem

In a simple service, there is usually one execution context and one Unit of Work type.

```text
one service
one ResourceHolder implementation
one BaseUnitOfWork subclass
one execution context
```

In a modular monolith, each module may have its own root Unit of Work.

```text
users module   -> UsersUnitOfWork
billing module -> BillingUnitOfWork
orders module  -> OrdersUnitOfWork
```

The core handler resolver can resolve a handler instance, but it does not know which module-specific Unit of Work should be used when executing that handler.

The UoW routing registry solves exactly this problem.

## Core Idea

The regular core registries answer:

```text
Which handler type belongs to this message type?
```

The regular core resolvers answer:

```text
How do we construct this handler instance?
```

The UoW routing registries answer:

```text
Which root Unit of Work type should be used for this handler type?
```

This keeps responsibilities separate.

```text
HandlerRegistry
  message type -> handler type

HandlerResolver
  handler type -> handler instance

UowRoutingRegistry
  handler type -> root UnitOfWork type
```

## Why Routing by Handler Type

The first version routed by message type:

```text
UseCaseCommand type -> root UnitOfWork type
Query type          -> root UnitOfWork type
Event type          -> root UnitOfWork type
```

The second version routes by handler type:

```text
UseCaseHandler type -> root UnitOfWork type
QueryHandler type   -> root UnitOfWork type
EventHandler type   -> root UnitOfWork type
```

This is more precise.

A message is an input model. A handler is the executable application component that belongs to a concrete module. In a modular monolith, module ownership is usually clearer at the handler level than at the message level.

This is especially important for events. One event can theoretically have several handlers. Handler-based routing allows each handler to be routed independently.

Even if the project rule says that all handlers for one event belong to one module, handler-based routing is still safer and more consistent.

## Why This Is Separate from Handler Registries

The root Unit of Work type is not part of the universal handler registration model.

In a simple service, adding UoW type to every handler registration would be unnecessary noise. The simple service engine can use one default Unit of Work type for everything.

In a modular monolith, UoW routing is needed because different modules may require different root Unit of Work implementations.

Therefore, UoW routing is kept in a dedicated optional layer under `modular_monolith_support`.

## No Modular Resolver

The modular layer does not need its own handler resolver.

A modular resolver would only do this:

```text
resolved_handler = normal_resolver.resolve(...)
root_uow_type = routing_registry.get_uow_type_by_handler_type(
    resolved_handler.handler_type
)
return resolved_handler + root_uow_type
```

That is only composition, not real resolving.

The engine, runtime, or dispatcher can perform these two lookups directly:

```python
resolved = use_case_resolver.resolve(type(command))

root_uow_type = use_case_uow_routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)
```

This keeps the core resolver layer clean and avoids duplicating auto-wiring, warm-up cache, and validation logic.

## `base_uow_routing_registry.py`

`base_uow_routing_registry.py` contains the shared routing mechanics.

It stores:

```text
handler_type -> root_uow_type
```

Where `handler_type` is a concrete handler class:

```text
UseCaseHandler subclass
QueryHandler subclass
EventHandler subclass
```

And `root_uow_type` is a subclass of:

```text
BaseUnitOfWork
```

The base registry provides:

```text
register(handler_type, root_uow_type)
has_uow_type_by_handler_type(handler_type)
get_uow_type_by_handler_type(handler_type)
iter_routes()
```

It also validates that every registered UoW type is a `BaseUnitOfWork` subclass.

## Routing Item

Bulk construction uses a small dataclass item instead of raw tuples.

Conceptually:

```python
UowRoutingRegistryItem(
    registry=users_use_case_registry,
    root_uow_type=UsersUnitOfWork,
)
```

This is clearer than passing:

```python
(users_use_case_registry, UsersUnitOfWork)
```

The item describes one module registration source:

```text
handler registry from one module
root Unit of Work type for that module
```

When a routing registry is built from this item, it iterates over registrations in the handler registry and stores:

```text
registration.handler_type -> root_uow_type
```

## `use_case_uow_routing_registry.py`

`UseCaseUowRoutingRegistry` maps use case handler types to root Unit of Work types.

```text
UseCaseHandler type -> BaseUnitOfWork subclass
```

It can be built from one handler registry:

```python
routing = UseCaseUowRoutingRegistry.from_registry(
    registry=users_use_case_registry,
    root_uow_type=UsersUnitOfWork,
)
```

Or from multiple module registries:

```python
routing = UseCaseUowRoutingRegistry.from_registry_items(
    [
        UowRoutingRegistryItem(
            registry=users_use_case_registry,
            root_uow_type=UsersUnitOfWork,
        ),
        UowRoutingRegistryItem(
            registry=billing_use_case_registry,
            root_uow_type=BillingUnitOfWork,
        ),
    ]
)
```

The modular runtime or root engine can then do:

```python
resolved = use_case_resolver.resolve(type(command))

root_uow_type = routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)
```

## `query_uow_routing_registry.py`

`QueryUowRoutingRegistry` maps query handler types to root Unit of Work types.

```text
QueryHandler type -> BaseUnitOfWork subclass
```

It follows the same model as use case routing.

Single registry:

```python
routing = QueryUowRoutingRegistry.from_registry(
    registry=users_query_registry,
    root_uow_type=UsersUnitOfWork,
)
```

Multiple registries:

```python
routing = QueryUowRoutingRegistry.from_registry_items(
    [
        UowRoutingRegistryItem(
            registry=users_query_registry,
            root_uow_type=UsersUnitOfWork,
        ),
        UowRoutingRegistryItem(
            registry=billing_query_registry,
            root_uow_type=BillingUnitOfWork,
        ),
    ]
)
```

The modular runtime or query engine can then do:

```python
resolved = query_resolver.resolve(type(query))

root_uow_type = routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)
```

## `event_uow_routing_registry.py`

`EventUowRoutingRegistry` maps event handler types to root Unit of Work types.

```text
EventHandler type -> BaseUnitOfWork subclass
```

This is the main reason v2 routes by handler type.

A modular event dispatcher resolves all handlers for an event, then routes each resolved handler independently:

```python
resolved_handlers = event_resolver.resolve(type(event))

for resolved in resolved_handlers:
    root_uow_type = event_uow_routing.get_uow_type_by_handler_type(
        resolved.handler_type,
    )

    uow = coordinator.get_use_case_uow(root_uow_type)
    context = EventHandlerContext(uow=uow)

    await resolved.handler(event, context)
```

This supports both cases:

```text
one event -> one module -> one event handler
one event -> several handlers -> each handler can still be routed explicitly
```

The current project rule may still be stricter:

```text
one event belongs to one module
```

But the routing layer no longer depends on that rule.

## Engine Usage

A modular use case engine usually performs three separate steps:

```text
resolve handler
route Unit of Work by resolved handler type
execute handler
```

Example:

```python
resolved = use_case_resolver.resolve(type(command))

root_uow_type = use_case_uow_routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)

uow = coordinator.get_use_case_uow(root_uow_type)

context = UseCaseHandlerContext(
    uow=uow,
    queue=queue,
    auth=auth,
    tracer=trace,
)

result = await resolved.handler(command, context)
```

The important point is that handler resolution and UoW routing are independent operations.

## Runtime Usage

`ModularMonolithExecutionRuntime` uses the same routing model for internal in-process invokes.

```python
resolved = use_case_resolver.resolve(
    type(command),
    overrides=dependency_overrides,
)

root_uow_type = use_case_uow_routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)

uow = coordinator.get_use_case_uow(root_uow_type)
```

For queries:

```python
resolved = query_resolver.resolve(
    type(query),
    overrides=dependency_overrides,
)

root_uow_type = query_uow_routing.get_uow_type_by_handler_type(
    resolved.handler_type,
)

uow = coordinator.get_query_uow(root_uow_type)
```

This keeps external root execution and internal `runtime.invoke(...)` execution consistent.

## Dispatcher Usage

A modular event dispatcher resolves event handlers normally, then routes each handler type to the module UoW.

```python
resolved_handlers = event_resolver.resolve(type(event))

for resolved in resolved_handlers:
    root_uow_type = event_uow_routing.get_uow_type_by_handler_type(
        resolved.handler_type,
    )

    uow = coordinator.get_use_case_uow(root_uow_type)

    context = EventHandlerContext(
        uow=uow,
    )

    await resolved.handler(event, context)
```

This is better than event-type routing because event-type routing assumes all handlers for the same event always use the same UoW.

Handler-type routing makes this explicit and future-proof.

## Duplicate Routes

The routing registry rejects conflicting routes.

This is valid:

```text
CreateUserHandler  -> UsersUnitOfWork
CreateOrderHandler -> OrdersUnitOfWork
```

This is invalid:

```text
CreateUserHandler -> UsersUnitOfWork
CreateUserHandler -> BillingUnitOfWork
```

If the same handler type is registered again with the same root UoW type, the registry may treat it as idempotent. If it is registered with a different UoW type, it raises a routing error.

## Design Boundaries

UoW routing registries should not:

```text
resolve handlers
create handlers
create Unit of Work instances
own ResourceHolder lifecycle
execute handlers
perform dependency injection
perform territory validation
```

They only store and return routing metadata.

## Relationship to Other Layers

```text
core/registries
  map messages to handler types

core/resolvers
  instantiate handler types

core/modular_monolith_support/uow_routing_registries
  map handler types to root Unit of Work types

core/modular_monolith_support/coordinator
  stores slot-owned Unit of Work instances

core/engines, execution_runtime, event_dispatchers
  combine resolved handler + routed Unit of Work + execution context
```

## Summary

The UoW routing registry layer exists because modular monolith execution needs to know which module-specific root Unit of Work should be used for a handler.

Version 2 routes by handler type, not by message type:

```text
UseCaseHandler -> root UnitOfWork type
QueryHandler   -> root UnitOfWork type
EventHandler   -> root UnitOfWork type
```

This keeps UoW ownership close to the executable application component, supports modular event dispatching, and avoids unnecessary modular resolver wrappers.

The model stays deliberately small:

```text
resolved.handler_type -> root UnitOfWork type
```

This is enough for modular engines, internal execution runtime, and modular event dispatchers to build the correct execution context without duplicating handler registry or resolver logic.
