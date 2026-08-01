# Tracing

The tracing module provides a small, backend-independent abstraction for
building and observing execution trees.

It is designed around three concepts:

```text
Trace
SpanFactory
Span
```

The framework creates a root span at an execution boundary and then propagates
only active span objects through handlers, event dispatchers, and
bounded-context invocations.

A tracing implementation may write logs, export telemetry, or record an
in-memory tree.

## Module Layout

A typical module layout is:

```text
core/tracing/
  __init__.py
  tracer.py
  logging_tracer.py
  recording_tracer.py
  tracing.md
```

## Core Model

### Trace

A trace is application-provided input used when a root span is created.

The framework does not define its structure. It may be:

```text
a trace identifier
a dictionary containing trace_id
an OpenTelemetry context
a remote propagation context
a custom application object
None
```

The trace exists only at the root-span creation boundary. After the root span
has been created, the framework propagates spans rather than the original
trace object.

### SpanFactory

`SpanFactory` creates root spans:

```python
class SpanFactory[TraceT](ABC):
    @abstractmethod
    def create_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Span:
        ...
```

A span factory is configured once when the application builds its engines:

```python
engine = SimpleServiceUseCaseEngine(
    resolver=resolver,
    span_factory=span_factory,
)
```

If no span factory is configured, tracing is disabled and the engine executes
normally.

The span factory is not passed through execution methods.

### Span

A span represents one active operation in the trace tree:

```python
class Span(ABC):
    @abstractmethod
    def child(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Span:
        ...

    @abstractmethod
    async def __aenter__(self) -> Span:
        ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        ...

    @abstractmethod
    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        ...

    @abstractmethod
    def add_event(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        ...
```

Every span contains enough backend-specific state to create its own children.

This removes the need to propagate the following values through every layer:

```text
trace
span factory
parent span
```

After root-span creation, the active span is the only tracing object required.

## Trace Tree

A trace is represented as a tree:

```text
use_case.handle
├── runtime.invoke
│   └── nested_handler.handle
└── event_handler.handle
```

Each span has one parent and zero or more children.

A child is created directly from the current span:

```python
async with span.child(
    name="runtime.invoke",
) as child:
    ...
```

When the child context exits, execution returns to the parent operation.

The tracing module does not maintain a global mutable current-span pointer.
This is important for concurrent execution because parallel branches may each
receive a separate child span without modifying shared state.

## Engine Integration

Engines own root-span creation:

```python
if self.span_factory is None:
    return await self._execute(
        ...,
        span=None,
    )

async with self.span_factory.create_span(
    trace=trace,
    name="use_case.handle",
    attributes=attributes,
) as span:
    return await self._execute(
        ...,
        span=span,
    )
```

The engine passes `Span | None` to handler contexts and event dispatchers.

Tracing-disabled execution remains explicit:

```text
span is None
```

A no-op implementation is not required.

## Handler Contexts

Handler contexts expose the active span:

```python
context = UseCaseHandlerContext(
    uow=uow,
    queue=event_queue,
    lifecycle_context=lifecycle_context,
    span=span,
)
```

Application code may use this span to trace its own operations:

```python
if context.span is None:
    return await client.call(...)

async with context.span.child(
    name="external_service.call",
) as child:
    return await client.call(...)
```

The framework does not require application code to create additional spans.

## Event Dispatching

An event dispatcher receives the parent span from the engine.

For every event handler, it creates a child span:

```python
if span is None:
    await handler.handle(
        event,
        EventHandlerContext(
            uow=uow,
            span=None,
        ),
    )
else:
    async with span.child(
        name="event_handler.handle",
        attributes=attributes,
    ) as child:
        await handler.handle(
            event,
            EventHandlerContext(
                uow=uow,
                span=child,
            ),
        )
```

Parallel event handlers remain safe because every task receives its own child
span object.

The dispatcher must await all event-handler tasks before the parent span exits.
Detached child tasks may outlive their parent and produce incomplete traces.

## Modular Runtime Integration

`ModularMonolithExecutionRuntime` does not store active span state.

A bounded-context client passes its current span explicitly:

```python
await runtime.invoke(
    command,
    span=context.span,
)
```

The runtime creates a child span representing the bounded-context invocation:

```python
if span is None:
    return await self._invoke(
        command=command,
        span=None,
    )

async with span.child(
    name="runtime.invoke",
    attributes=attributes,
) as child:
    return await self._invoke(
        command=command,
        span=child,
    )
```

Concurrent runtime invocations are isolated because each call operates only on
the span supplied by its caller.

## Span Names

Span names should identify the framework operation and the invoked message or
handler.

Examples:

```text
simple.use_case.handle my_app.commands.CreateUser
simple.query.handle my_app.queries.GetUser
modular.use_case.handle billing.commands.CreateInvoice
runtime.invoke inventory.commands.ReserveStock
runtime.invoke_query catalogue.queries.GetProduct
event_handler.handle billing.handlers.InvoiceCreatedHandler
```

Names should remain stable enough for logs, tests, and external telemetry.

Backend-specific identifiers should be stored as attributes rather than encoded
into span names.

## Attributes and Events

Spans may record structured attributes:

```python
span.set_attribute(
    "handler.type",
    "billing.handlers.CreateInvoiceHandler",
)
```

Initial attributes may also be provided during creation:

```python
span.child(
    name="runtime.invoke",
    attributes={
        "message.kind": "use_case_command",
        "handler.source_name": "inventory",
    },
)
```

Events represent important moments inside one span:

```python
span.add_event("runtime.invoke.started")
span.add_event("runtime.invoke.finished")
```

A concrete implementation may ignore attributes or events while still
satisfying the tracing contract.

## Exceptions

Span context managers should not suppress execution exceptions.

Implementations should normally return `False` from `__aexit__`.

When an exception is raised inside a span, an implementation may record:

```text
failure status
exception type
exception message
elapsed time
backend-specific error metadata
```

The exception must continue propagating through the framework.

## Recording Tracer

`RecordingSpanFactory` is a lightweight tree-based implementation intended for
development and readable execution logging.

The simplified recording model stores only:

```text
span name
children
start time
finish time
duration
status
exception type
```

It intentionally ignores detailed attributes and events.

### One Log Message per Trace

The recording tracer does not emit a log message for every span operation.

Instead, the root span receives a closure from the factory. When the root span
exits, the closure renders the complete tree and writes one log message:

```python
def create_span(...):
    root = SpanNode(name=name)

    def log_trace() -> None:
        logger.log(
            level,
            "%s",
            render_trace(root),
        )

    return RecordingSpan(
        node=root,
        on_root_exit=log_trace,
    )
```

Child spans do not log independently.

### Configuration

```python
factory = RecordingSpanFactory(
    logger=logging.getLogger("direttore.tracing"),
    level=logging.DEBUG,
    log_on_exit=True,
)
```

`log_on_exit=False` disables output while preserving compatibility with the
same tracing contracts.

### Example Output

```text
Trace [OK] 18.426 ms
└── modular.use_case.handle CreateOrder [OK] 18.426 ms
    ├── runtime.invoke ReserveInventory [OK] 4.213 ms
    └── event_handler.handle OrderCreated [OK] 2.117 ms
```

Failure output may look like:

```text
Trace [FAILED] 9.731 ms
└── modular.use_case.handle CreateOrder [FAILED] 9.731 ms error=RuntimeError
    └── runtime.invoke ReserveInventory [FAILED] 3.114 ms error=StockError
```

## Logging Tracer

A traditional logging tracer may log every span lifecycle operation:

```text
span started
attribute added
event added
span finished
span failed
```

This is useful for low-level diagnostics but can produce noisy logs.

The recording tracer is preferred when the developer wants one readable
execution tree per request.

Both implementations satisfy the same `Span` and `SpanFactory` contracts and
can be exchanged without changing engine or application code.

## Application Configuration

Applications configure the span factory directly:

```python
config = SimpleServiceDirettoreConfig(
    slot=slot_config,
    handlers=handler_config,
    span_factory=RecordingSpanFactory(),
)
```

The application passes the configured factory to its engines during
construction.

The external execution call provides only the trace value:

```python
await application.handle(
    command,
    input=request_context,
    trace={"trace_id": "request-123"},
)
```

The application does not resolve trace headers or create backend-specific trace
objects. That responsibility belongs to the external adapter.

## Boundary Rules

The tracing module should contain:

```text
Span contract
SpanFactory contract
recording models
logging or telemetry implementations
tree rendering helpers
```

It should not contain:

```text
engine execution logic
event-dispatch rules
HTTP header parsing
trace-context extraction
authentication
authorization
lifecycle-context creation
application request parsing
business-specific attributes
```

Those responsibilities belong to engines, adapters, lifecycle implementations,
or application code.

## Concurrency Rules

Tracing remains correct under concurrency when these rules are followed:

1. Every parallel operation receives its own child span.
2. No shared mutable current-span field is used.
3. Child operations finish before their parent span exits.
4. Event dispatch uses structured concurrency such as `TaskGroup` or
   `gather()`.
5. Runtime invocations receive the caller's span explicitly.

Parallel sibling branches are represented naturally:

```text
parent
├── handler.a
└── handler.b
```

## Summary

The final tracing model is:

```text
Trace + SpanFactory
    create root Span

Span
    creates child Span objects

Engine
    owns root-span creation

Handler context
    exposes the active span

Event dispatcher
    creates handler child spans

Modular runtime
    receives the caller span explicitly
    creates a bounded-context child span

RecordingSpanFactory
    records the tree
    logs the complete trace once when the root exits
```

The central invariant is:

```text
Before root creation:
    trace + span factory

After root creation:
    span only
```
