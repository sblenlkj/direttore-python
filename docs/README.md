# Direttore documentation

Direttore is an asynchronous, slot-centric application framework for executing
use cases, dispatching events, managing execution-scoped resources, and
coordinating local saga compensation. It supports two application shapes:

- **Simple service** — one handler graph and one root unit of work. This is the
  smallest useful setup and a good default for a service or a small
  application.
- **Modular monolith** — several bounded contexts, each with its own registries
  and root unit-of-work type, executed over one shared resource holder.

Both application shapes expose the same application-facing operations and the
same explicit transactional-lease model.

Direttore currently requires Python 3.12 or newer. In this repository, use
`uv sync --dev` for the test suite or `uv sync --group examples` for the
executable Jupyter examples.

## Documentation map

- [Recommended project structure](project-structure.md) — canonical context,
  adapters/application/domain, shared, and bootstrap layout, including a
  migration map from the earlier language-learning-platform structure.
- [Simple-service guide](simple-service.md) — a complete wiring walkthrough for
  messages, handlers, registries, dependencies, resources, configuration, and
  application execution.
- [Modular-monolith guide](modular-monolith.md) — bounded contexts, UoW routing,
  the coordinator, and execution-scoped in-process dependencies.
- [Warehouse examples](../examples/README.md) — runnable simple-service and
  modular-monolith implementations with Jupyter walkthroughs.

## Mental model

An application facade obtains an execution slot from a provider. The slot
resolves the registered handler, creates an optional lifecycle context and
trace span, invokes the handler, drains emitted events, finalizes resources,
and returns the clean slot to its provider.

```text
application facade
  -> slot provider
    -> execution slot
      -> resolve message and handler
      -> create lifecycle context and trace span
      -> select unit of work
      -> invoke handler
      -> drain queued events
      -> save saga entries, if any
      -> commit or roll back resources
      -> close resources and reset the slot
```

The application facade is the normal entry point. A physical execution slot is
framework-owned infrastructure, while a `SlotLease` gives application code
temporary ownership of a slot for several sequential operations in one
transaction.

## Core objects

### Commands, results, and events

Every use-case request is a concrete subclass of `UseCaseCommand`. Every
ordinary use-case response is a concrete subclass of `UseCaseHandlerResult`.
Do not leave the handler's `command` parameter untyped and do not use a result
object as the command.

For stock receipt, the three distinct types are:

```python
# contexts/warehouse/application/use_cases/receive_stock.py
from dataclasses import dataclass

from direttore import UseCaseCommand, UseCaseHandlerResult


@dataclass(frozen=True, slots=True)
class ReceiveStockCommand(UseCaseCommand):
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class StockBalance(UseCaseHandlerResult):
    product_id: str
    quantity: int
```

- `ReceiveStockCommand` describes the requested operation.
- `StockBalance` describes the successful business result.
- `ReceiveStockHandler` performs the operation and connects those types.

Event messages inherit `Event` and describe facts that have happened:

```python
# contexts/warehouse/application/events/stock_received.py
from dataclasses import dataclass

from direttore import Event


@dataclass(frozen=True, slots=True)
class StockReceived(Event):
    product_id: str
    quantity: int
    new_balance: int
```

All messages inherit the base `Message` payload contract:

- `from_payload(mapping)` constructs the message with keyword arguments;
- `to_payload()` serializes a dataclass with `dataclasses.asdict`, or otherwise
  returns the instance attribute dictionary.

Override those methods when values such as UUIDs or custom value objects need
explicit conversion to and from a stable serialized payload.

### Parameterized handler contexts in `architecture.py`

The earlier project called the corresponding module `orchestration.py`; the
recommended current name is `application/architecture.py`.

`UseCaseHandlerContext` is parameterized by three types:

1. the context's root UoW type;
2. the lifecycle-context type;
3. the span type.

Create context-specific aliases once in `architecture.py` and use them in every
handler in that bounded context:

```python
# contexts/warehouse/application/architecture.py
from direttore import (
    EventHandlerContext,
    EventHandlerRegistry,
    SagaCompensationContext,
    UseCaseHandlerContext,
    UseCaseHandlerRegistry,
)
from direttore.core.contracts import Lifecycle
from direttore.core.tracing import Span

from modular_monolith.contexts.warehouse.application.ports.unit_of_work import (
    WarehouseUnitOfWork,
)
from modular_monolith.shared.lifecycle import (
    WarehouseRequestContext,
    WarehouseRequestInput,
)

type WarehouseUseCaseHandlerContext = UseCaseHandlerContext[
    WarehouseUnitOfWork,
    WarehouseRequestContext,
    Span,
]
type WarehouseEventHandlerContext = EventHandlerContext[
    WarehouseUnitOfWork,
    Span,
]
type WarehouseSagaCompensationContext = SagaCompensationContext[
    WarehouseUnitOfWork,
    Span,
]

use_case_registry: UseCaseHandlerRegistry[
    Lifecycle[WarehouseRequestInput | None, WarehouseRequestContext]
] = UseCaseHandlerRegistry(source_name="warehouse")
event_registry = EventHandlerRegistry(source_name="warehouse")
```

The aliases say exactly which UoW and span Warehouse handlers receive, and the
normal use-case alias also specifies its lifecycle context. The concrete
command type is not placed in an alias because each handler accepts a different
command. It is declared in that use-case module and used directly on the
`command` parameter.

### Use-case handlers

A use-case handler inherits `UseCaseHandler` and implements asynchronous
`handle(command, context)`. Both parameters and the return value should be
annotated precisely:

When a handler needs an external adapter, define an application port rather
than importing the adapter implementation:

```python
# contexts/warehouse/application/ports/stock_receipt_client.py
from typing import Protocol


class StockReceiptClient(Protocol):
    async def validate_receipt(
        self,
        product_id: str,
        quantity: int,
    ) -> None:
        ...
```

The handler requests that port in `__init__`, stores it, and reuses it from
`handle`:

```python
# contexts/warehouse/application/use_cases/receive_stock.py
from direttore import UseCaseHandler

from modular_monolith.contexts.warehouse.application.architecture import (
    WarehouseUseCaseHandlerContext,
    use_case_registry,
)
from modular_monolith.contexts.warehouse.application.events.stock_received import (
    StockReceived,
)
from modular_monolith.contexts.warehouse.application.ports.stock_receipt_client import (
    StockReceiptClient,
)


@use_case_registry.decorator_register(
    command_type=ReceiveStockCommand,
    key="warehouse.receive-stock.v1",
)
class ReceiveStockHandler(UseCaseHandler):
    def __init__(self, client: StockReceiptClient) -> None:
        self._client = client

    async def handle(
        self,
        command: ReceiveStockCommand,
        context: WarehouseUseCaseHandlerContext,
    ) -> StockBalance:
        await self._client.validate_receipt(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        new_quantity = await context.uow.products.receive(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        context.queue.push(
            StockReceived(
                product_id=command.product_id,
                quantity=command.quantity,
                new_balance=new_quantity,
            )
        )
        return StockBalance(
            product_id=command.product_id,
            quantity=new_quantity,
        )
```

The normal handler contract is therefore:

```text
ReceiveStockCommand
  -> ReceiveStockHandler.handle(command, WarehouseUseCaseHandlerContext)
  -> StockBalance
```

The context supplies:

- `uow` — the precisely typed root UoW selected for the handler;
- `queue` — the event queue for publishing events;
- `lifecycle_context` — the typed request-scoped context created by the
  registered lifecycle, or `None`;
- `span` — the active typed span, or `None`.

The handler asks a repository already exposed by its UoW for read/write access
only when needed. It does not commit, roll back, or close resources; the
execution slot owns that boundary.

The two dependencies in this example arrive through different mechanisms:

- `self._client` is an application-scope adapter injected by the handler
  resolver from `Container`, using the `StockReceiptClient` port as its key;
- `context.uow.products` is a repository adapter already assembled by the
  concrete Warehouse UoW. It is not injected into the handler constructor and
  is not stored in `Container`.

### Event handlers

An event handler follows the same typing principle. Its parameter is the
specific event type, while its context alias is parameterized by the context
UoW and span:

```python
from direttore import EventHandler

from modular_monolith.contexts.warehouse.application.architecture import (
    WarehouseEventHandlerContext,
    event_registry,
)


@event_registry.decorator_register(event_type=StockReceived)
class RecordStockMovementHandler(EventHandler):
    async def handle(
        self,
        event: StockReceived,
        context: WarehouseEventHandlerContext,
    ) -> None:
        await context.uow.stock_movements.record(event)
        return None
```

An event can have multiple registered handlers. Event handlers return `None`
unless they contribute saga compensation, and they do not own the top-level
transaction.

## Registries

Registries connect message types to handler types. They store types and
metadata; resolvers create handler instances later.

### Registering use cases

```python
use_case_registry.register(
    ReceiveStockCommand,
    ReceiveStockHandler,
    key="warehouse.receive-stock.v1",
)
```

The optional fields on a use-case registration are:

| Field | Purpose |
| --- | --- |
| `key` | Stable external key used by `handle_by_key` and stored operations. |
| `config` | Per-handler `UseCaseHandlerConfig`, passed to the lifecycle. |
| `lifecycle` | Per-handler lifecycle override. |
| `execution_mode` | Whether plain-slot events run in or after the business transaction. |
| `event_draining_mode` | Sequential or parallel draining of queued events. |
| `saga_key` | Stable compensation lookup key. |
| `compensation_type` | Message type used to reconstruct compensation. |

`saga_key` and `compensation_type` must be supplied together. A registry
rejects duplicate command types, duplicate public keys, and duplicate saga
keys.

The decorator form has the same metadata:

```python
@use_case_registry.decorator_register(
    ReceiveStockCommand,
    key="warehouse.receive-stock.v1",
)
class ReceiveStockHandler(UseCaseHandler):
    async def handle(
        self,
        command: ReceiveStockCommand,
        context: WarehouseUseCaseHandlerContext,
    ) -> StockBalance:
        ...
```

A registry can define `default_lifecycle` and `default_config`. Values supplied
to an individual registration take precedence. `UseCaseHandlerRegistry.merge_many`
combines registries and fails if their message types or keys conflict.

The built-in `UseCaseHandlerConfig` currently carries
`allowed_access_tags: frozenset[str] | None`. Direttore passes this metadata to
the lifecycle; it does not itself authenticate a caller or enforce the tags. A
project that uses access tags should interpret and enforce them in its
lifecycle or another application policy layer.

### Registering events

```python
event_registry.register(StockReceived, RecordStockMovementHandler)
```

The decorator form is also available. `is_ready=False` keeps a registration in
the registry while excluding it from normal event resolution. Event registries
can be combined with `EventHandlerRegistry.merge_many`.

### Importing registries

A practical project keeps one use-case registry and one optional event registry
per service or bounded context. Define those objects in
`application/architecture.py`. Importing `architecture.py` creates the empty
registries; importing the individual use-case and event modules executes their
registration statements.

Load every registration module deliberately. In a modular monolith,
`context.py` normally performs those imports before exporting its
`ModularMonolithDirettoreContext`. In a simple service,
`bootstrap/registries.py` can load the modules before returning the populated
registries. Avoid scanning arbitrary modules or hiding registration imports in
request code, because duplicate registrations are errors and startup becomes
harder to reason about.

For a simple service, pass the imported registries to
`SimpleServiceHandlerConfig`. For a modular monolith, pass each pair of
registries to its own `ModularMonolithDirettoreContext`; the slot creator merges
them and preserves the context-to-UoW routing.

## Dependency container and handler resolution

`Container` stores already-created, application-lifetime adapter objects under
the application port types requested by handler constructors. It does not own
repositories, UoWs, resource holders, sessions, transactions, lifecycle
contexts, or spans.

### Port-to-adapter binding

The mapping key is the port annotation used in the handler. The mapping value
is the concrete adapter object that implements that port:

```python
# contexts/warehouse/adapters/outbound/http_stock_receipt_client.py
class HttpStockReceiptClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def validate_receipt(
        self,
        product_id: str,
        quantity: int,
    ) -> None:
        # Call the external stock-receipt service.
        ...
```

```python
# contexts/warehouse/container.py
from direttore import Container

from modular_monolith.contexts.warehouse.adapters.outbound.http_stock_receipt_client import (
    HttpStockReceiptClient,
)
from modular_monolith.contexts.warehouse.application.ports.stock_receipt_client import (
    StockReceiptClient,
)


def build_warehouse_container(config: ApplicationConfig) -> Container:
    return Container.from_mapping(
        {
            StockReceiptClient: HttpStockReceiptClient(
                base_url=config.stock_receipt_base_url,
            ),
        }
    )
```

This means “when a handler constructor requests `StockReceiptClient`, pass this
`HttpStockReceiptClient` object.” It does not mean that the adapter class itself
must be the mapping key. Handlers depend on the port and never import
`HttpStockReceiptClient`.

The incremental form is equivalent:

```python
container = Container()
container.set(
    StockReceiptClient,
    HttpStockReceiptClient(base_url=config.stock_receipt_base_url),
)
```

Typical container dependencies are outbound HTTP/API clients, publishers,
clock or identifier ports, feature-policy services, and other stateless or
concurrency-safe application-scope adapters.

### Constructor injection into handlers

The resolver inspects `ReceiveStockHandler.__init__`, reads the
`StockReceiptClient` annotation, retrieves the object registered under that
exact port type, and calls the constructor with it:

```python
class ReceiveStockHandler(UseCaseHandler):
    def __init__(self, client: StockReceiptClient) -> None:
        self._client = client

    async def handle(
        self,
        command: ReceiveStockCommand,
        context: WarehouseUseCaseHandlerContext,
    ) -> StockBalance:
        await self._client.validate_receipt(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        new_quantity = await context.uow.products.receive(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        return StockBalance(
            product_id=command.product_id,
            quantity=new_quantity,
        )
```

The parameter name (`client`) is an application choice. Resolution is driven
by its type annotation. Each required constructor parameter must be annotated
with a named class type; a `Protocol` declaration such as `StockReceiptClient`
works as that port type. Parameterized typing expressions, unions, and `Any`
are not valid container keys for resolver injection. A constructor parameter
with a default may use that default when no dependency is registered.

Ordinary handlers are cached after construction, so injected adapter objects
must be suitable for application-lifetime reuse and the application's
concurrency model.

### Repositories belong to the UoW

Repository protocols may be defined under `application/ports/`, but repository
implementations are assembled by the concrete UoW adapter. They are never
registered in `Container` and never injected directly into a handler.

For example, a SQLAlchemy UoW constructs its SQLAlchemy repositories over the
slot's unified resource holder:

```python
class SQLAlchemyWarehouseUnitOfWork(WarehouseUnitOfWork):
    def __init__(self, resources: ResourceHolder) -> None:
        super().__init__(resources)
        self.products = SQLAlchemyProductRepository(resources)
        self.stock_movements = SQLAlchemyStockMovementRepository(resources)
```

The handler receives that UoW through its parameterized execution context and
uses `context.uow.products`. Repository methods resolve the live session lazily
through the UoW/resource holder. This preserves execution-slot ownership and
prevents an application-lifetime handler from retaining a session from an old
slot generation.

The UoW enters Direttore composition differently in each application variant.

For a simple service, provide the concrete UoW factory on the slot config:

```python
slot=SimpleServiceSlotConfig(
    resource_holder_factory=sqlalchemy_resource_holder_factory,
    uow_factory=SQLAlchemyWarehouseUnitOfWork,
)
```

For a modular monolith, the context declares its concrete root UoW type:

```python
warehouse_context = ModularMonolithDirettoreContext(
    use_case_registry=use_case_registry,
    event_registry=event_registry,
    use_case_root_uow_type=SQLAlchemyWarehouseUnitOfWork,
)
```

The modular coordinator must register an instance of that same type over its
shared holder:

```python
class ApplicationUnitOfWorkCoordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(
            SQLAlchemyWarehouseUnitOfWork(self.resource_holder)
        )
```

The modular slot then routes each resolved handler to the UoW type declared by
its context.

### Resolution order and execution-scoped ports

Handler-constructor resolution uses this order:

1. an execution-scoped override in modular-monolith mode;
2. the regular application container;
3. the constructor parameter's default value;
4. a dependency-resolution error.

Cross-context adapters backed by `ModularMonolithExecutionRuntime` are
execution-scoped. Register their port-to-factory binding in
`ModularMonolithExecutionDependencyRegistry`, not in `Container`. The factory
receives the current runtime and produces the adapter for that physical slot
execution.

```python
execution_dependencies.register(
    dependency_type=WarehouseContextClient,
    factory=lambda context: InProcessWarehouseContextClient(
        runtime=context.runtime,
    ),
)
```

A handler can request `WarehouseContextClient` in `__init__` and store it on
`self`; the resolver recognizes that port as execution-scoped and injects the
adapter built for the current runtime instead of consulting the regular
container. Such handlers are constructed per runtime rather than cached as
application-lifetime handler instances. For larger context APIs, the client
may delegate to a Warehouse-owned inbound `WarehouseContextFacade`; see the
[modular-monolith guide](modular-monolith.md#context-owned-facade).

Database sessions, transaction objects, and other execution-local resources
belong in `ResourceHolder`, not in either dependency registry.

Resolvers validate dependencies and warm up ordinary handlers when the slot
creator is built. `application.validate()` provides an explicit startup
validation entry point as well. Handlers that use modular execution-scoped
dependencies are created for the current runtime instead of being cached
globally.

## Lifecycle context (the execution cycle)

`Lifecycle[InputT, LifecycleContextT]` converts optional operation input into a
context supplied to a use-case handler. It also receives the handler config,
active `ResourceHolder`, and active span.

```python
from dataclasses import dataclass

from direttore import ResourceHolder, UseCaseHandlerConfig
from direttore.core.contracts import Lifecycle
from direttore.core.tracing import Span


@dataclass(frozen=True, slots=True)
class RequestInput:
    actor_id: str


@dataclass(frozen=True, slots=True)
class RequestContext:
    actor_id: str | None


class RequestLifecycle(Lifecycle[RequestInput | None, RequestContext]):
    async def create_context(
        self,
        input: RequestInput | None,
        config: UseCaseHandlerConfig,
        resource: ResourceHolder,
        span: Span | None,
    ) -> RequestContext:
        return RequestContext(
            actor_id=input.actor_id if input is not None else None,
        )
```

Set a lifecycle as the registry default when most use cases share it, or on a
single registration for an exception. When neither is configured, handlers
receive `lifecycle_context=None`.

The application, slot creator, provider, and lease should carry the same input
and trace types. Application calls accept `input=None`, so the lifecycle should
handle absence deliberately.

## Resources and units of work

`ResourceHolder` owns lazy, named, execution-scoped resources. It caches each
created resource and remembers whether any caller requested write access. A
concrete application holder must implement:

- `commit()` — apply the application's successful-finalization policy and call
  `_mark_finalized()`;
- `rollback()` — undo opened work and call `_mark_finalized()`;
- `close()` — release every opened resource.

```python
from inspect import isawaitable

from direttore import ResourceHolder


class ApplicationResourceHolder(ResourceHolder):
    async def commit(self) -> None:
        self._ensure_not_finalized()
        for name, resource in self._resources.items():
            method = resource.commit if self._commit_required[name] else resource.rollback
            result = method()
            if isawaitable(result):
                await result
        self._mark_finalized()

    async def rollback(self) -> None:
        if self.is_finalized:
            return
        for resource in self._resources.values():
            result = resource.rollback()
            if isawaitable(result):
                await result
        self._mark_finalized()

    async def close(self) -> None:
        for resource in reversed(tuple(self._resources.values())):
            result = resource.close()
            if isawaitable(result):
                await result
```

This sample expresses one possible session policy, not a guarantee made by
Direttore. Commit order, multi-resource failure recovery, and transaction
semantics remain application responsibilities.

Register resource factories by name when constructing the holder. Factories
may be synchronous or asynchronous. Resources are created only when requested:

```python
holder = ApplicationResourceHolder(
    {
        "primary": primary_session_factory,
        "analytics": analytics_session_factory,
    }
)
```

`BaseUnitOfWork` is a thin typed facade over that holder:

- `read_session(name="primary")` obtains the cached resource without setting
  commit intent;
- `write_session(name="primary")` obtains the same resource and permanently
  sets commit intent for that name during the execution.

Read followed by write returns the same resource. Write followed by read does
not clear commit intent. The UoW owns neither transaction state nor a second
resource cache.

## Configuration and application composition

The complete composition order is:

1. define commands, events, results, and lifecycle input/context types;
2. implement UoWs, handlers, and a concrete resource holder;
3. build and populate handler registries;
4. build the application dependency container;
5. construct a variant-specific slot-creator configuration;
6. create the slot creator;
7. choose a slot provider;
8. construct the application facade;
9. call `application.validate()` during startup;
10. invoke the application facade from an HTTP endpoint, worker, CLI, or
    notebook.

Variant-specific configuration is covered in the two guides. The provider
choice is shared:

- `FactoryExecutionSlotProvider` creates a new physical slot for every
  acquisition. It is simple and useful for examples and low-volume workloads.
- `PoolExecutionSlotProvider` reuses cleaned slots. It requires
  `initial_slot_count >= 1` and `max_slot_count >= initial_slot_count`; callers
  wait when all slots are acquired and the maximum has been reached.

`application.slot_provider_stats()` reports total, free, acquired, and maximum
slot counts. A factory provider has no free-slot pool and no maximum.

For where each object should live in a real application and how registry import
side effects are controlled, see the
[recommended project structure](project-structure.md).

## Running use cases

Both application facades expose the same one-shot entry points:

```python
result = await application.handle(
    ReceiveStockCommand(product_id="P-100", quantity=10),
    input=request_input,
    trace=trace_input,
)

result = await application.handle_by_key(
    "warehouse.receive-stock.v1",
    {"product_id": "P-100", "quantity": 10},
    input=request_input,
)

result = await application.handle_operation(
    "stored-operation-42",
    input=request_input,
)
```

- `handle` resolves by command type.
- `handle_by_key` resolves a registration by its stable `key`, then creates the
  command with `from_payload`.
- `handle_operation` asks a configured `OperationLoader` for a key/payload
  pair, then follows the key-based path.

An operation loader receives the operation ID, current `ResourceHolder`, and
active span:

```python
from direttore import KeyPayloadPair, OperationLoader, ResourceHolder
from direttore.core.tracing import Span


class StoredOperationLoader(OperationLoader):
    async def get_key_payload_pair(
        self,
        operation_id: int | str,
        resource: ResourceHolder,
        span: Span | None,
    ) -> KeyPayloadPair:
        session = await resource.get_session("primary")
        row = await load_operation(session, operation_id)
        return KeyPayloadPair(key=row.key, payload=row.payload)
```

Configure a loader in the variant's `use_case_execution` config. Calling
`handle_operation` without one is an application configuration error.

## Events and transaction timing

Use-case handlers publish events with `context.queue.push(event)` or
`push_many(events)`. Direttore keeps draining until the queue is empty. The
configured `max_processed_events` limit (default: 100) caps the number of
events collected in one drain batch. A handler graph that can continually
produce new events still needs an application-level termination rule.

`UseCaseHandlerExecutionMode` controls plain one-shot execution:

- `IN_TRANSACTION` — drain events before the business-resource commit;
- `AFTER_TRANSACTION` — save saga data and commit business resources first,
  then open a new resource boundary and drain events there.

`UseCaseEventDrainingMode` controls how the currently queued events are drained.
`SEQUENTIAL` dispatches those events one after another; `PARALLEL` dispatches
the queued events concurrently. The handlers registered for one particular
event are still invoked in registry order by its dispatcher. Parallel event
dispatches share the execution resource boundary, so the application's
resource implementation must be safe for that access pattern.

If no event registry is configured, a slot has no dispatcher and clears queued
events without handling them. If a dispatcher exists but a queued event has no
ready registration, resolution fails. Configure registrations for every event
that is meant to have an observable reaction.

An explicit lease always drains each operation's events immediately but defers
its one resource commit until the lease transaction completes.

## Multiple operations in one transaction

Use a `SlotLease` for a transactional island:

```python
async with application.slot(saga_id="order-42") as lease:
    async with lease.transaction():
        await lease.handle(
            ReceiveStockCommand("P-100", 10),
            input=request_input,
        )
        await lease.handle(
            ReceiveStockCommand("P-200", 5),
            input=request_input,
        )
```

The inner `transaction()` context commits once on success and rolls back on an
exception. Releasing an uncommitted lease also rolls it back. A lease is:

- valid only until it is released;
- generation-checked so it cannot access a reused physical slot;
- sequential, not concurrency-safe;
- local runtime state that must never be serialized.

Each normal lease call creates a fresh lifecycle context and operation span.
The three cache forms reuse the lifecycle context and span created by the most
recent normal call:

- `handle_cache(command)`;
- `handle_by_key_cache(key, payload)`;
- `handle_operation_cache(operation_id)`.

Calling a cache form before `handle`, `handle_by_key`, or `handle_operation`
raises `SlotLeaseStateError`. Cache forms are deliberately available only on a
lease, not on physical execution slots.

Prefer `lease.transaction()` to manual `commit()` and `rollback()` unless an
integration requires explicit control. Do not use one lease concurrently from
several tasks; acquire separate slots instead.

## Tracing

Configure a `SpanFactory[TraceT]` on the slot creator. The factory converts an
optional application-specific trace input into a root `Span`. Child work uses
`Span.child`, so handlers receive the active span without needing the original
trace object or the factory.

Direttore includes logging and recording implementations under
`direttore.core.tracing`. A production integration can implement `Span` and
`SpanFactory` for its tracing backend. When no factory is configured, all span
values are `None` and execution continues normally.

## Local saga compensation

Saga support records serializable compensation messages for successfully
handled work. It is used when committed steps may need to be undone later. It
does not replace normal rollback for an exception in the current transaction.

### Compensable use-case types

A normal handler returns its business result directly:

```python
async def handle(
    self,
    command: ReceiveStockCommand,
    context: WarehouseUseCaseHandlerContext,
) -> StockBalance:
    return StockBalance(product_id=command.product_id, quantity=new_quantity)
```

A compensable handler returns `SagaUseCaseHandlerResult` instead. That wrapper
contains both:

- `result` — the ordinary `UseCaseHandlerResult` returned to the caller;
- `compensation` — a `UseCaseCommandCompensation` message stored in the saga
  journal as a payload.

Define a concrete compensation message for the operation:

```python
from dataclasses import dataclass

from direttore import UseCaseCommandCompensation


@dataclass(frozen=True, slots=True)
class ReverseStockReceipt(UseCaseCommandCompensation):
    product_id: str
    quantity: int
```

Because this is a dataclass containing strings and integers, the inherited
`to_payload` and `from_payload` implementations are sufficient. Override them
for UUIDs, enums, value objects, or versioned external representations.

### Saga handler registration

Register the handler with two different keys:

- `key` is the public invocation key used by `handle_by_key`;
- `saga_key` is the stable internal key stored in saga entries and later used
  to find the compensation handler.

The saga key and compensation type must always be provided together:

```python
@use_case_registry.decorator_register(
    command_type=ReceiveStockCommand,
    key="warehouse.receive-stock.v1",
    saga_key="warehouse.receive-stock.compensation.v1",
    compensation_type=ReverseStockReceipt,
)
class ReceiveStockHandler(UseCaseHandler):
    ...
```

The registry verifies that `ReverseStockReceipt` inherits
`UseCaseCommandCompensation` and that the saga key is unique. At execution
time, Direttore also verifies that the handler returned an instance of the
registered compensation type.

### Saga-aware `handle` and `compensate`

The full compensable handler has two methods:

```python
from direttore import (
    SagaUseCaseHandlerResult,
    UseCaseHandler,
)

from modular_monolith.contexts.warehouse.application.architecture import (
    WarehouseSagaCompensationContext,
)


@use_case_registry.decorator_register(
    command_type=ReceiveStockCommand,
    key="warehouse.receive-stock.v1",
    saga_key="warehouse.receive-stock.compensation.v1",
    compensation_type=ReverseStockReceipt,
)
class ReceiveStockHandler(UseCaseHandler):
    def __init__(self, client: StockReceiptClient) -> None:
        self._client = client

    async def handle(
        self,
        command: ReceiveStockCommand,
        context: WarehouseUseCaseHandlerContext,
    ) -> SagaUseCaseHandlerResult:
        await self._client.validate_receipt(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        new_quantity = await context.uow.products.receive(
            product_id=command.product_id,
            quantity=command.quantity,
        )
        context.queue.push(
            StockReceived(
                product_id=command.product_id,
                quantity=command.quantity,
                new_balance=new_quantity,
            )
        )
        return SagaUseCaseHandlerResult(
            result=StockBalance(
                product_id=command.product_id,
                quantity=new_quantity,
            ),
            compensation=ReverseStockReceipt(
                product_id=command.product_id,
                quantity=command.quantity,
            ),
        )

    async def compensate(
        self,
        compensation: ReverseStockReceipt,
        context: WarehouseSagaCompensationContext,
    ) -> None:
        await context.uow.products.remove_received_stock(
            product_id=compensation.product_id,
            quantity=compensation.quantity,
        )
```

Both the regular `handle` context and the compensation context use aliases from
`application/architecture.py`. The generic framework
`SagaCompensationContext[UnitOfWorkT, SpanT]` contains:

- `saga_id` — the saga being compensated;
- `uow` — the UoW routed to the original handler's context;
- `span` — the active compensation span, or `None`.

The `WarehouseSagaCompensationContext` alias binds those generic parameters to
`WarehouseUnitOfWork` and `Span`, so `context.uow` and `context.span` are typed
without casts. The framework performs the actual UoW routing before invoking
`compensate`.

The `compensate` method is discovered when compensation runs. Although it is
not an abstract method on `UseCaseHandler`, every handler registered for saga
compensation must implement it.

### Configure a journal

Saga entries cannot be persisted without a `SagaJournal`. Supply one on the
variant's slot-creator config:

```python
from direttore import InMemorySagaJournal, ModularMonolithSlotCreatorConfig

direttore_config = ModularMonolithSlotCreatorConfig(
    slot=slot_config,
    contexts=modular_contexts,
    saga_journal=InMemorySagaJournal(),
)
```

The simple-service config accepts the same `saga_journal` field.
`InMemorySagaJournal` is appropriate for tests and notebooks, but loses all
records when the process exits. Production applications should implement
`SagaJournal.save` and `SagaJournal.load` with durable storage appropriate to
their recovery policy.

The journal stores `SagaEntry` values containing only:

- handler kind (`use_case` or `event`);
- stable saga handler key;
- serialized compensation payload.

It does not store a live handler, UoW, resource, slot, or compensation object.

### Execute with a saga ID

Pass `saga_id` when invoking a one-shot operation:

```python
balance = await application.handle(
    ReceiveStockCommand(product_id="P-100", quantity=10),
    saga_id="warehouse-receipt-42",
)
```

For several sequential steps that should produce one ordered saga record, use
a lease with the saga ID:

```python
async with application.slot(saga_id="order-O-100") as lease:
    async with lease.transaction():
        await lease.handle(
            ReceiveStockCommand(product_id="P-100", quantity=10)
        )
        await lease.handle(
            ReceiveStockCommand(product_id="P-200", quantity=5)
        )
```

Direttore collects compensation entries only while a `saga_id` is active. If a
handler returns `SagaUseCaseHandlerResult` without a saga ID, the caller still
receives its ordinary `result`, but no saga entry is recorded.

Before committing business resources, Direttore calls the configured journal
to save the collected entries. Journal persistence and business-resource
commit are not a distributed atomic transaction; the concrete infrastructure
must define its own failure-recovery policy.

### Run compensation

Compensation is explicit:

```python
await application.compensate_saga(
    "warehouse-receipt-42",
    trace=trace_input,
)
```

Direttore then:

1. loads the saga record from the journal;
2. reads entries in reverse order;
3. selects the use-case or event registry from the stored handler kind;
4. resolves the original handler by its stable `saga_key`;
5. reconstructs the registered compensation type with `from_payload`;
6. routes the correct context UoW;
7. invokes `handler.compensate(compensation, context)`;
8. commits the compensation execution after all entries succeed.

Compensation methods must be idempotent because a caller may retry after an
unknown outcome. Direttore does not automatically compensate when the current
local handler fails; that execution is rolled back normally. It also does not
provide distributed locks, two-phase commit, a retry daemon, or automatic
scheduling of compensation.

### Compensable event handlers

Event handlers use the corresponding event types:

- the compensation message inherits `EventCompensation`;
- registration supplies `saga_key` and `compensation_type` together;
- `handle` returns `SagaEventHandlerResult(compensation=...)`;
- the same handler implements asynchronous `compensate`.

```python
from dataclasses import dataclass

from direttore import (
    EventCompensation,
    EventHandler,
    SagaEventHandlerResult,
)


@dataclass(frozen=True, slots=True)
class DeleteStockMovement(EventCompensation):
    movement_id: str


@event_registry.decorator_register(
    event_type=StockReceived,
    saga_key="warehouse.stock-movement.compensation.v1",
    compensation_type=DeleteStockMovement,
)
class RecordStockMovementHandler(EventHandler):
    async def handle(
        self,
        event: StockReceived,
        context: WarehouseEventHandlerContext,
    ) -> SagaEventHandlerResult:
        movement_id = await context.uow.stock_movements.record(event)
        return SagaEventHandlerResult(
            compensation=DeleteStockMovement(movement_id=movement_id)
        )

    async def compensate(
        self,
        compensation: DeleteStockMovement,
        context: WarehouseSagaCompensationContext,
    ) -> None:
        await context.uow.stock_movements.delete(compensation.movement_id)
```

Unlike `SagaUseCaseHandlerResult`, `SagaEventHandlerResult` has no business
`result` field because event dispatch does not return a result to the
application caller.

## Startup checklist

Before serving work:

1. import every intended registration module;
2. construct the container and application configuration;
3. call `application.validate()` to catch unresolved handler dependencies;
4. verify every configured resource holder finalizes and closes resources;
5. verify public handler keys and saga keys are unique and versioned;
6. choose event execution/draining modes deliberately;
7. size a pool provider for the application's maximum useful concurrency;
8. test commit, rollback, cleanup, event ordering, and compensation behavior.
