# Primitives v2

This document describes the current `core/primitives` design after the ResourceHolder lifecycle changes.

The primitives package contains small framework-owned building blocks used by engines, resolvers, handlers, event dispatchers, and application bootstrap code.

```text
core/primitives/
  container.py
  event_queue.py
  resource_holder.py
  uow.py
```

## Core Idea

The primitives layer separates three different kinds of runtime state:

```text
Container
  long-lived dependencies

ResourceHolder
  execution-scoped lazy resources

BaseUnitOfWork
  stable access object over ResourceHolder

EventQueue
  temporary queue for events emitted during use case execution
```

The main architectural rule is:

> Long-lived objects should not store request-scoped sessions directly.

Handlers, services, repositories, clients, and adapters may be reused across executions. Runtime resources such as database sessions should live inside `ResourceHolder`, which is owned by the execution scope.

## `container.py`

`container.py` defines a simple dependency container.

The container stores long-lived dependencies by type. It is used by resolvers, engines, and application bootstrap code to retrieve reusable objects.

Typical examples:

```text
repositories
services
handler dependencies
client wrappers
factories
configuration objects
```

The container is not request-scoped. It should not store database sessions or execution-scoped objects.

Typical use:

```python
container.set(UserRepository, user_repository)

repo = container.get(UserRepository)
```

Main responsibilities:

```text
register dependency by type
retrieve dependency by type
check whether dependency exists
merge containers
merge many containers
```

## `event_queue.py`

`event_queue.py` defines `EventQueue`.

`EventQueue` is used during use case execution to collect events that should be dispatched later by the orchestration layer.

The queue does not dispatch events by itself. It only stores them temporarily.

Typical use:

```python
context.queue.push(UserCreated(user_id=user.id))
```

Main responsibilities:

```text
push event/message
push many events/messages
pop next event/message
check whether queue is empty
clear queue
```

## `resource_holder.py`

`resource_holder.py` defines execution-scoped lazy resource holders.

A resource holder owns resources created during one execution scope. It starts without created resources. A resource is created only when `get(name)` is called for the first time. Repeated calls return the same resource instance.

Typical resources:

```text
database sessions
Redis connections
HTTP clients
broker clients
external API sessions
```

The holder allows repositories and Unit of Work objects to depend on one stable object while real resources are created lazily only when needed.

## `BaseResourceHolder`

`BaseResourceHolder` contains the shared mechanics:

```text
register resource factory
check whether a resource is registered
check whether a resource was created
get or lazily create a resource
run close hook
clear internal resource references
```

`BaseResourceHolder` does not define commit or rollback behavior.

It provides a `close_all()` hook that subclasses may override. The framework calls internal `_close_all()`, which runs `close_all()` and then clears internal resource references. User code should not clear internal holder state manually.

Example cleanup hook:

```python
async def close_all(self) -> None:
    if self.is_created("main_db"):
        session = await self.get("main_db")
        await session.close()

    if self.is_created("redis"):
        redis = await self.get("redis")
        await redis.aclose()
```

## `QueryResourceHolder`

`QueryResourceHolder` is used for read-side execution.

It does not commit or rollback resources. On exit, it only runs the cleanup hook and clears created resource references.

Query execution does not process events and does not need transaction-phase guards.

Applications may subclass `QueryResourceHolder` and override `close_all()` when query resources require explicit cleanup.

## `AbstractUseCaseResourceHolder`

`AbstractUseCaseResourceHolder` is used for write-side use case execution.

It owns the lifecycle of resources created during one use case execution scope.

The framework owns the async context manager protocol:

```text
__aenter__
  marks holder as open

__aexit__
  if execution succeeded -> commit()
  if execution failed    -> rollback()
  always                 -> _close_all()
  finally                -> marks holder as closed
```

Concrete implementations must define:

```text
commit()
rollback()
```

They may override:

```text
close_all()
```

## Use Case Holder Lifecycle Guard

`AbstractUseCaseResourceHolder` has an open/closed lifecycle guard.

During use case execution, `get(name)` is allowed.

After the use case execution scope exits, the holder is closed. Any later attempt to access resources through `get(name)` raises `ResourceClosedError`.

This is intentional.

It protects the framework from cases where an event handler runs outside the transactional phase but still tries to access transactional resources through `UnitOfWork` / `ResourceHolder`.

Typical failure scenario:

```text
use case execution starts
database session is created
use case commits
resource holder exits and becomes closed
out-of-transaction event handler tries to access main_db
ResourceClosedError is raised
```

This gives a clear fail-fast signal instead of silently using an invalid session.

## Correct Commit / Rollback Pattern

`commit()` and `rollback()` should only touch resources that were actually created during execution.

Use `is_created(name)` before calling `get(name)`.

Correct:

```python
async def commit(self) -> None:
    if self.is_created("main_db"):
        session = await self.get("main_db")
        await session.commit()

async def rollback(self) -> None:
    if self.is_created("main_db"):
        session = await self.get("main_db")
        await session.rollback()
```

Incorrect:

```python
async def commit(self) -> None:
    session = await self.get("main_db")
    await session.commit()
```

The incorrect version may create a database session only to commit it.

## Correct Cleanup Pattern

`close_all()` may access created resources while the holder is still open.

This is why `AbstractUseCaseResourceHolder` marks the holder as closed only after `_close_all()` finishes.

Correct lifecycle:

```text
commit / rollback
close_all
clear internal resources
mark holder as closed
```

This allows cleanup code to work:

```python
async def close_all(self) -> None:
    if self.is_created("main_db"):
        session = await self.get("main_db")
        await session.close()
```

User code should not call `clear()` directly. Internal cleanup is handled by `_close_all()`.

## `uow.py`

`uow.py` defines `BaseUnitOfWork`.

`BaseUnitOfWork` is intentionally thin.

It does not:

```text
open sessions
close sessions
commit transactions
rollback transactions
own execution lifecycle
```

The execution scope owns the `ResourceHolder`.

`BaseUnitOfWork` only gives handlers, repositories, and application components a stable access point to the current execution-scoped resources.

Typical use:

```python
session = await uow.resources.get("main_db")
```

Projects may subclass `BaseUnitOfWork` to add typed accessors:

```python
class AppUnitOfWork(BaseUnitOfWork):
    async def main_db(self):
        return await self.resources.get("main_db")
```

## Event Handler Implication

Because `AbstractUseCaseResourceHolder` becomes closed after the use case scope exits, event handlers can reuse the same context shape without needing separate handler types for transactional and out-of-transaction execution.

If an out-of-transaction event handler tries to access transactional resources, it fails with `ResourceClosedError`.

This keeps event handler contracts simple while still enforcing execution boundaries.

## Execution Model

For query execution:

```text
engine creates QueryResourceHolder
engine creates BaseUnitOfWork over holder
handler runs
holder runs close_all hook
holder clears internal resources
```

For use case execution:

```text
engine creates AbstractUseCaseResourceHolder implementation
engine creates BaseUnitOfWork over holder
use case handler runs
holder commits on success or rolls back on failure
holder runs close_all hook
holder clears internal resources
holder becomes closed
events may be processed after transaction
closed holder prevents accidental transactional resource access
```

## Boundary Rules

The primitives package should stay small.

It should not contain:

```text
business logic
domain entities
domain events
repository tracking
external integration code
framework-specific adapters
```

It should contain only low-level orchestration building blocks used by the rest of the kernel.

## Current Design Summary

```text
Container
  long-lived dependencies

EventQueue
  temporary event buffer

BaseResourceHolder
  lazy execution resource access

QueryResourceHolder
  read-side holder without transaction phase guard

AbstractUseCaseResourceHolder
  write-side holder with commit/rollback and closed-state guard

BaseUnitOfWork
  stable access object over the current holder
```
