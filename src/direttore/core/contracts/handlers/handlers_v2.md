# Handler Contracts v2

This document describes the current `core/contracts/handlers` design after the v2 simplification.

```text
core/contracts/handlers/
  event_handler.py
  query_handler.py
  use_case_handler.py
```

These files define the public execution contracts for user-defined handlers. They do not implement orchestration logic themselves. Engines, registries, resolvers, dispatchers, and application bootstrap code use these contracts to understand how handlers should be called.

## Core Idea

Handlers are the executable side of the message model.

The message layer defines what can be executed or published:

```text
UseCaseCommand
Query
Event
```

The handler layer defines how these messages are processed:

```text
UseCaseHandler
QueryHandler
EventHandler
```

A handler does not own its registration key. Keys belong to registries. This keeps handlers independent from the environment where they are registered.

## Main v2 Change

The previous design separated event handlers into two categories:

```text
EventHandler
EventHandlerWithUnitOfWork
```

The v2 design removes this split.

Now every event handler receives an `EventHandlerContext` with a `BaseUnitOfWork`.

Whether transactional resources are still accessible is controlled by the `ResourceHolder` lifecycle, not by a separate event handler type.

This gives one consistent event handler contract:

```text
Event -> EventHandler -> None
```

If an event handler runs after the use case transaction has already closed and tries to access transactional resources, the underlying `AbstractUseCaseResourceHolder` raises `ResourceClosedError`.

This keeps event handler code simple while preserving a hard execution boundary.

## `use_case_handler.py`

`use_case_handler.py` defines the contract for write-side use case execution.

It contains:

```text
UseCaseHandler
UseCaseHandlerContext
UseCaseHandlerConfig
UseCaseHandlerExecutionMode
UseCaseHandlerResult
```

### `UseCaseHandler`

`UseCaseHandler` is the abstract contract for executing a `UseCaseCommand`.

A concrete use case handler receives:

```text
command
context
```

and returns:

```text
UseCaseHandlerResult
```

Use case handlers are intended for operations that may change state, emit events, and run inside a write-side execution boundary.

### `UseCaseHandlerContext`

`UseCaseHandlerContext` contains runtime objects provided by the orchestration engine:

```text
uow
queue
auth
tracer
```

The context is generic over:

```text
UnitOfWorkT
AuthT
TraceT
```

This allows application code to use a project-specific `BaseUnitOfWork` subclass while keeping the framework contract stable.

Example:

```python
UseCaseHandlerContext[AppUnitOfWork, AuthContext, Tracer]
```

### `UseCaseHandlerConfig`

`UseCaseHandlerConfig` describes execution metadata for a use case handler.

It currently contains:

```text
execution_mode
allowed_access_tags
```

`execution_mode` tells the engine how the handler should be positioned relative to the main transactional phase.

`allowed_access_tags` is reserved for authorization and access-control checks.

### `UseCaseHandlerResult`

`UseCaseHandlerResult` is the base result contract for use case handlers.

Concrete projects can subclass it when they need structured use case output.

## `query_handler.py`

`query_handler.py` defines the contract for read-side query execution.

It contains:

```text
QueryHandler
QueryHandlerContext
QueryHandlerConfig
QueryHandlerResult
```

### `QueryHandler`

`QueryHandler` is the abstract contract for executing a `Query`.

A concrete query handler receives:

```text
query
context
```

and returns:

```text
QueryHandlerResult
```

Query handlers are intended for read operations. They should not publish application events as part of normal execution.

### `QueryHandlerContext`

`QueryHandlerContext` contains runtime objects for read-side execution:

```text
uow
auth
tracer
```

The context is generic over:

```text
UnitOfWorkT
AuthT
TraceT
```

The query context is lighter than the use case context. It does not contain an event queue because queries should not be the source of application events.

### `QueryHandlerConfig`

`QueryHandlerConfig` contains query execution metadata.

It currently contains:

```text
allowed_access_tags
```

This is reserved for authorization and access-control checks.

### `QueryHandlerResult`

`QueryHandlerResult` is the base result contract for query handlers.

Concrete projects can subclass it when they need structured query output.

## `event_handler.py`

`event_handler.py` defines the contract for reacting to events.

It contains:

```text
EventHandler
EventHandlerContext
```

### `EventHandler`

`EventHandler` is the abstract contract for processing an `Event`.

A concrete event handler receives:

```text
event
context
```

and returns:

```text
None
```

There is only one event handler contract in v2.

The event handler does not need to know whether it is running inside or outside the transaction. It always receives a context with `uow`. The `ResourceHolder` inside that UoW decides whether execution-scoped resources are still available.

### `EventHandlerContext`

`EventHandlerContext` contains:

```text
uow
```

The context is generic over:

```text
UnitOfWorkT
```

Example:

```python
EventHandlerContext[AppUnitOfWork]
```

This allows event handlers to use the same application-specific Unit of Work type as use case handlers.

## Transaction Boundary Behavior

The v2 event handler model relies on `AbstractUseCaseResourceHolder`.

During use case execution:

```text
holder is open
resources can be accessed
```

After the use case execution scope exits:

```text
holder is closed
transactional resource access through get(name) fails fast
```

This means that event handlers can reuse the same context shape, but invalid resource access is still detected.

Typical scenario:

```text
use case starts
main_db resource is created
use case commits
holder exits and becomes closed
out-of-transaction event handler tries to access main_db
ResourceClosedError is raised
```

This is intentional. It makes execution boundary violations explicit and easy to debug.

## Design Notes

The handler contracts are intentionally small.

They avoid:

```text
handler-owned registration keys
automatic caching flags
domain-event assumptions
repository tracking
separate event handler contracts for transaction modes
business-specific infrastructure
```

Registration belongs to registries. Resolution belongs to resolvers. Execution belongs to engines. Resource lifecycle belongs to resource holders.

Handler contracts only describe how user-defined handler classes are called.

## Current Contract Summary

```text
UseCaseCommand -> UseCaseHandler -> UseCaseHandlerResult
Query          -> QueryHandler   -> QueryHandlerResult
Event          -> EventHandler   -> None
```

Contexts:

```text
UseCaseHandlerContext
  uow
  queue
  auth
  tracer

QueryHandlerContext
  uow
  auth
  tracer

EventHandlerContext
  uow
```

The event handler model is now simpler: one event handler type, one context, and lifecycle enforcement through `ResourceHolder`.
