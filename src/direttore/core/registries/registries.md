# Registries

This document describes the `core/registries` design introduced in v2.

The registries package stores mappings between orchestration messages and their handlers. Registries do not execute handlers, resolve dependencies, or own lifecycle. They only describe which handler type should be used for a given message type or key.

```text
core/registries/
  errors.py
  registrations.py
  base_handler_registry.py
  use_case_handler_registry.py
  query_handler_registry.py
  event_handler_registry.py
```

## Core Idea

The registry layer is intentionally simple.

```text
UseCaseCommand -> UseCaseHandler
Query          -> QueryHandler
Event          -> one or more EventHandlers
```

Registries are core objects, not external dependencies. Therefore, v2 does not use registry ports or protocols.

A registry is responsible for:

```text
registering handler types
checking duplicates
looking up registrations by message type
looking up keyed handlers by key
providing registration metadata
supporting registry merging
```

Engines, resolvers, dispatchers, and validators use registries to understand what handlers are available.

## Removed from v1

The v2 registry design removes several older concepts:

```text
registry ports
handler-owned keys
register_key flags
handler groups
query handler groups
domain-event assumptions
```

Handler keys are no longer stored on handler classes. Keys belong to registry registration calls.

Territory membership is not handled by registry groups anymore. Territory membership is handled by territory manifests.

## `errors.py`

`errors.py` contains registry-specific exceptions.

Expected errors include:

```text
RegistryError
HandlerAlreadyRegisteredError
HandlerKeyAlreadyRegisteredError
HandlerNotRegisteredError
HandlerKeyNotRegisteredError
InvalidHandlerTypeError
InvalidMessageTypeError
```

These errors make registry failures explicit and easier for engines or bootstrap code to catch.

Typical cases:

```text
same message type registered twice
same key registered twice
handler not found by message type
handler not found by key
invalid message class
invalid handler class
```

## `registrations.py`

`registrations.py` contains immutable registration records.

Registrations are data objects. They describe what was registered, where it came from, and how it should be configured.

### Base registrations

The common metadata is extracted into base registration classes:

```text
BaseHandlerRegistration
  source_name

BaseKeyedHandlerRegistration
  source_name
  key
```

`source_name` identifies the module, territory, package, or application area that produced the registration.

`key` is used only for registries that support handle-by-key execution.

### Use case registration

```text
UseCaseHandlerRegistration
  command_type
  handler_type
  key
  source_name
  config
```

A use case registration maps one `UseCaseCommand` type to one `UseCaseHandler` type.

### Query registration

```text
QueryHandlerRegistration
  query_type
  handler_type
  key
  source_name
  config
```

A query registration maps one `Query` type to one `QueryHandler` type.

### Event registration

```text
EventHandlerRegistration
  event_type
  handler_type
  source_name
  is_ready
```

An event registration maps one `Event` type to one `EventHandler` type. Unlike use case and query handlers, multiple handlers may be registered for the same event type.

## `base_handler_registry.py`

`base_handler_registry.py` defines `BaseHandlerRegistry`.

It is an abstract base class used by single-handler registries:

```text
UseCaseHandlerRegistry
QueryHandlerRegistry
```

It is not intended for event handlers, because event handlers use different cardinality.

### Responsibility

`BaseHandlerRegistry` stores:

```text
message_type -> registration
key          -> registration
```

It provides:

```text
has_handler(message_type)
has_key(key)
get_registration(message_type)
get_registration_by_key(key)
iter_registrations()
merge_many(...)
```

It also performs duplicate checks:

```text
same message type cannot be registered twice
same key cannot be registered twice
```

### Abstract methods

Concrete registries must implement:

```text
_get_message_type(registration)
_get_handler_type(registration)
_get_key(registration)
```

This keeps base storage reusable without forcing one generic registration shape on all concrete registries.

### Source name

`source_name` is passed when a registry is created:

```python
registry = UseCaseHandlerRegistry(source_name="users")
```

Every registration created by this registry receives that source name.

Merged registries may also receive a source name:

```python
merged = UseCaseHandlerRegistry.merge_many(
    [users_registry, billing_registry],
    source_name="app",
)
```

Individual registrations still preserve their original `source_name`.

## `use_case_handler_registry.py`

`UseCaseHandlerRegistry` maps one `UseCaseCommand` type to one `UseCaseHandler` type.

```text
UseCaseCommand -> UseCaseHandler
```

It supports optional key-based lookup:

```text
"users.create" -> UseCaseHandlerRegistration
```

### Direct registration

```python
registry.register(
    command_type=CreateUserCommand,
    handler_type=CreateUserHandler,
    key="users.create",
)
```

### Decorator registration

```python
@registry.decorator_register(
    CreateUserCommand,
    key="users.create",
)
class CreateUserHandler(UseCaseHandler):
    ...
```

`decorator_register` is only a decorator-friendly wrapper around `register`.

### Lookup

```python
registration = registry.get_registration(CreateUserCommand)
handler_type = registry.get_handler_type(CreateUserCommand)
handler_type = registry.get_handler_type_by_key("users.create")
config = registry.get_config(CreateUserCommand)
```

### Validation

The registry validates:

```text
command_type is a UseCaseCommand subclass
handler_type is a UseCaseHandler subclass
```

## `query_handler_registry.py`

`QueryHandlerRegistry` maps one `Query` type to one `QueryHandler` type.

```text
Query -> QueryHandler
```

It has the same shape as `UseCaseHandlerRegistry`.

### Direct registration

```python
registry.register(
    query_type=GetUserQuery,
    handler_type=GetUserHandler,
    key="users.get",
)
```

### Decorator registration

```python
@registry.decorator_register(
    GetUserQuery,
    key="users.get",
)
class GetUserHandler(QueryHandler):
    ...
```

### Lookup

```python
registration = registry.get_registration(GetUserQuery)
handler_type = registry.get_handler_type(GetUserQuery)
handler_type = registry.get_handler_type_by_key("users.get")
config = registry.get_config(GetUserQuery)
```

### Validation

The registry validates:

```text
query_type is a Query subclass
handler_type is a QueryHandler subclass
```

## `event_handler_registry.py`

`EventHandlerRegistry` maps one `Event` type to many `EventHandler` types.

```text
Event -> list[EventHandler]
```

It does not use keys. Event dispatch is based on event type.

### Direct registration

```python
registry.register(
    event_type=UserCreated,
    handler_type=SendWelcomeEmailHandler,
)
```

### Decorator registration

```python
@registry.decorator_register(UserCreated)
class SendWelcomeEmailHandler(EventHandler):
    ...
```

### Ready flag

Event registrations support `is_ready`.

```python
registry.register(
    event_type=UserCreated,
    handler_type=SendWelcomeEmailHandler,
    is_ready=True,
)
```

This can be used for staged rollout, migration, or temporarily disabled handlers.

### Lookup

```python
registrations = registry.get_registrations(UserCreated)
handler_types = registry.get_handler_types(UserCreated)
```

By default, lookups return only ready handlers. The registry may also expose all handlers when `ready_only=False`.

### Duplicate check

The same handler type cannot be registered twice for the same event type.

## Registry Cardinality

The three registries intentionally use different cardinality.

```text
UseCaseHandlerRegistry
  one command type -> one handler type

QueryHandlerRegistry
  one query type -> one handler type

EventHandlerRegistry
  one event type -> many handler types
```

This reflects execution semantics:

```text
a command should have one executor
a query should have one reader
an event may have many reactions
```

## Relation to Territory Manifest

Registries do not decide which messages belong to a territory.

That responsibility belongs to territory manifests.

A territory manifest says:

```text
this territory includes these commands
this territory includes these queries
this territory includes these events
```

A registry says:

```text
this command/query/event has these handlers
```

A validator can compare:

```text
global message catalog
territory manifest
handler registries
```

to detect missing handlers or invalid registrations.

## Design Summary

```text
registrations.py
  immutable registration records

errors.py
  registry-specific exceptions

BaseHandlerRegistry
  reusable storage for single-handler registries

UseCaseHandlerRegistry
  UseCaseCommand -> UseCaseHandler
  optional key lookup

QueryHandlerRegistry
  Query -> QueryHandler
  optional key lookup

EventHandlerRegistry
  Event -> many EventHandlers
  no key lookup
  optional is_ready flag
```

The v2 registry model is deliberately smaller than v1. It keeps registration explicit, removes ports and groups, and delegates territory membership to manifests.
