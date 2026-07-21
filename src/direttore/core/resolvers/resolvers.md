# Resolvers

This document describes the `core/resolvers` module in v2.

Resolvers connect handler registries with executable handler instances. They do not execute handlers themselves. Their responsibility is to take a handler registration, construct or retrieve the corresponding handler object, and return a resolved handler object that the engine can call.

```text
core/resolvers/
  errors.py
  resolved_handlers.py
  base_handler_resolver.py
  use_case_handler_resolver.py
  query_handler_resolver.py
  event_handler_resolver.py
```

## Core Idea

Registries know which handler type belongs to which message type.

Resolvers know how to instantiate handler types.

```text
Registry
  message type -> handler type

Resolver
  handler type -> handler instance
```

The v2 resolver strategy is:

```text
warm-up cache + auto-wiring
```

This means:

```text
inspect handler constructor
resolve constructor dependencies from overrides or Container
create handler instance
cache handler when it does not depend on execution-scoped dependencies
return resolved handler object
```

## Removed from v1

The v2 resolver layer removes the old resolver variants:

```text
ContainerResolver
AutoWiringResolver
WarmUpCacheAutoWiringResolver
Resolver ports
handler group filtering
cache_handler flags
```

There is now one default resolver strategy.

The framework assumes that auto-wiring with warm-up cache is the normal path.

## `errors.py`

`errors.py` contains resolver-specific exceptions:

```text
ResolverError
HandlerConstructorInspectionError
HandlerDependencyResolutionError
HandlerWarmUpError
HandlerValidationError
```

These errors separate resolver failures from registry failures.

Typical cases:

```text
handler constructor cannot be inspected
handler constructor dependency has no type annotation
dependency cannot be found in overrides or container
handler warm-up failed
handler validation failed
```

## `resolved_handlers.py`

`resolved_handlers.py` contains `ResolvedHandler`.

```python
ResolvedHandler[HandlerT, RegistrationT]
```

It stores:

```text
handler
handler_type
registration
```

The engine receives `ResolvedHandler` objects from resolvers.

This keeps together:

```text
the actual handler instance
the handler class
the original registry metadata
```

Example conceptual shape:

```text
ResolvedHandler
  handler = CreateUserHandler(...)
  handler_type = CreateUserHandler
  registration = UseCaseHandlerRegistration(...)
```

## `base_handler_resolver.py`

`base_handler_resolver.py` defines `BaseHandlerResolver`.

It contains the reusable resolver mechanics used by:

```text
UseCaseHandlerResolver
QueryHandlerResolver
EventHandlerResolver
```

Concrete resolvers only need to define how to extract `handler_type` from their registration type.

## Constructor Auto-Wiring

The base resolver inspects the handler constructor and resolves constructor parameters.

Dependency resolution order:

```text
1. runtime overrides
2. Container
3. constructor default value
4. error
```

Example:

```python
class CreateUserHandler(UseCaseHandler):
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
    ) -> None:
        self.users = users
        self.hasher = hasher
```

If `UserRepository` and `PasswordHasher` are registered in `Container`, the resolver can instantiate the handler automatically.

## Runtime Overrides

Runtime overrides are passed at resolve time.

They are useful for execution-scoped dependencies that should not be stored in the long-lived container.

Example:

```python
resolved = resolver.resolve(
    CreateUserCommand,
    overrides={
        AppUnitOfWork: uow,
    },
)
```

If a constructor dependency type exists in overrides, the override value wins over the container.

## Execution Dependency Types

Some dependencies are execution-scoped and should prevent handler caching.

The resolver receives them during initialization:

```python
resolver = UseCaseHandlerResolver(
    registry=registry,
    container=container,
    execution_dependency_types={
        AppUnitOfWork,
    },
)
```

If a handler constructor depends on one of these exact types, the handler is not cached and is created per resolve.

The check is intentionally strict:

```text
dependency_type in execution_dependency_types
```

The resolver does not use `issubclass()` for this check. If a project-specific execution dependency should be treated as scoped, it must be registered explicitly in `execution_dependency_types`.

## Warm-Up Cache

The resolver can warm up cache during initialization.

Warm-up means:

```text
iterate over registrations
inspect handler constructors
create cacheable handlers immediately
store them in handler cache
skip handlers that depend on execution-scoped dependencies
```

This catches many wiring errors during application startup rather than during the first request.

Cacheable handlers are reused.

Non-cacheable handlers are created per resolve.

## Validation

The resolver can validate all registered handlers.

Validation checks constructor dependencies without necessarily creating handler instances.

For each constructor parameter:

```text
if dependency type is execution-scoped -> ok
else if dependency type exists in Container -> ok
else if parameter has default value -> ok
else validation error
```

This is different from warm-up.

Warm-up creates only cacheable handlers.

Validation checks every handler, including handlers that depend on execution-scoped dependencies.

Concrete resolvers expose:

```python
resolver.validate()
```

## `use_case_handler_resolver.py`

`UseCaseHandlerResolver` resolves use case handlers.

It uses:

```text
UseCaseHandlerRegistry
UseCaseHandlerRegistration
UseCaseHandler
UseCaseCommand
```

It supports:

```text
resolve by command type
resolve by key
validate all registered use case handlers
warm-up cache
```

Typical use:

```python
resolver = UseCaseHandlerResolver(
    registry=use_case_registry,
    container=container,
    execution_dependency_types={AppUnitOfWork},
)

resolved = resolver.resolve(CreateUserCommand)
handler = resolved.handler
registration = resolved.registration
```

Key-based resolution:

```python
resolved = resolver.resolve_by_key("users.create")
```

## `query_handler_resolver.py`

`QueryHandlerResolver` resolves query handlers.

It uses:

```text
QueryHandlerRegistry
QueryHandlerRegistration
QueryHandler
Query
```

It supports:

```text
resolve by query type
resolve by key
validate all registered query handlers
warm-up cache
```

Typical use:

```python
resolved = resolver.resolve(GetUserQuery)
handler = resolved.handler
```

Key-based resolution:

```python
resolved = resolver.resolve_by_key("users.get")
```

## `event_handler_resolver.py`

`EventHandlerResolver` resolves event handlers.

It uses:

```text
EventHandlerRegistry
EventHandlerRegistration
EventHandler
Event
```

Unlike use case and query resolvers, event resolver returns a list because one event can have many handlers.

```text
Event -> list[ResolvedHandler[EventHandler, EventHandlerRegistration]]
```

Typical use:

```python
resolved_handlers = resolver.resolve(UserCreated)

for resolved in resolved_handlers:
    await resolved.handler(event, context)
```

## Ready-Only Event Resolution

Event handler registrations may have `is_ready`.

The event resolver supports ready-only resolution.

By default:

```text
ready_only = True
```

This means disabled or not-ready event handlers are not returned by normal resolve calls.

A caller may override this:

```python
resolved_handlers = resolver.resolve(
    UserCreated,
    ready_only=False,
)
```

## Resolver Lifecycle

A typical resolver lifecycle is:

```text
create resolver
validate handlers
warm up cache
resolve handlers during execution
```

Concrete resolvers support `validate` and `warm_up` flags during initialization.

Typical bootstrap:

```python
resolver = UseCaseHandlerResolver(
    registry=registry,
    container=container,
    execution_dependency_types={AppUnitOfWork},
    validate=True,
    warm_up=True,
)
```

## Relation to Container

The `Container` stores long-lived dependencies.

Resolvers use the container to instantiate handlers.

```text
Container
  UserRepository
  PasswordHasher
  EmailClient

Resolver
  reads handler __init__
  pulls required dependencies from Container
  creates handler
```

Execution-scoped objects should not be stored in the container. They should be provided through overrides or through handler call context.

## Relation to Registries

Registries store metadata.

Resolvers instantiate.

```text
Registry:
  command_type -> handler_type

Resolver:
  handler_type -> handler instance
```

The resolver does not decide what belongs to a territory. Territory membership remains the responsibility of manifests and validators.

## Relation to Engines

Engines use resolvers to obtain handlers.

An engine usually does:

```text
receive message
ask registry/resolver for handler
build handler context
call handler
process result/events
```

Resolvers stop before execution. They do not call handler `__call__`.

## Design Summary

```text
errors.py
  resolver-specific exceptions

resolved_handlers.py
  ResolvedHandler record

BaseHandlerResolver
  auto-wiring
  warm-up cache
  validation
  constructor inspection
  dependency resolution

UseCaseHandlerResolver
  resolve one use case handler by command type or key

QueryHandlerResolver
  resolve one query handler by query type or key

EventHandlerResolver
  resolve many event handlers by event type
```

The v2 resolver layer is intentionally opinionated: warm-up cache auto-wiring is the default and only blessed resolver strategy.
