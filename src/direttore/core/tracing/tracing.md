# Tracing Module

This document describes the `core/modules/tracing` module.

The tracing module provides a small framework contract for creating spans around orchestration operations. It also provides a default logging-based implementation that can be used during development or as a lightweight fallback.

```text
core/modules/tracing/
  __init__.py
  tracer.py
  logging_tracer.py
  tracing.md
```

## Core Idea

The framework does not own a concrete tracing backend.

Instead, it defines a minimal tracing contract:

```text
Tracer
  creates spans

TraceSpan
  represents one measured execution block

LoggingTracer
  default implementation that logs span activity
```

The engine or dispatcher may use this module to wrap operations such as:

```text
query execution
use case execution
handler invocation
event dispatching
resolver work
background task execution
```

## `tracer.py`

`tracer.py` contains the core tracing contracts.

It defines:

```text
Tracer
TraceSpan
```

These classes are framework contracts. They are intentionally small and do not depend on OpenTelemetry, LangFuse, Phoenix, or any other concrete backend.

## `TraceSpan`

`TraceSpan` represents one traced execution block.

It is an async context manager:

```python
async with tracer.start_span(
    trace=trace,
    name="use_case.handle",
    attributes={
        "command_type": type(command).__qualname__,
    },
) as span:
    span.add_event("handler.started")
    result = await handler(command, context)
    span.add_event("handler.finished")
```

A span supports:

```text
__aenter__
__aexit__
set_attribute(...)
add_event(...)
```

Implementations should normally return `False` from `__aexit__`, so exceptions are not suppressed.

## `Tracer`

`Tracer` creates spans.

Conceptually:

```text
trace object + span name + attributes -> TraceSpan
```

The framework does not define the shape of the `trace` object.

`TraceT` may be:

```text
trace id
request id
OpenTelemetry context
LangFuse trace/client object
Phoenix trace object
custom application trace object
None
```

This keeps the tracing module independent from any tracing vendor.

## `logging_tracer.py`

`logging_tracer.py` contains the default implementation:

```text
LoggingTracer
LoggingTraceSpan
```

This implementation does not export real distributed traces. It writes span lifecycle information into Python logging.

It is useful for:

```text
development
debugging
tests
early application bootstrap
projects that want trace-like visibility without a tracing backend
```

## `LoggingTracer`

`LoggingTracer` implements `Tracer`.

It creates `LoggingTraceSpan` objects.

Typical use:

```python
import logging

from direttore.orchestration.core.modules.tracing import LoggingTracer

tracer = LoggingTracer(
    logger=logging.getLogger("app.orchestration"),
    level=logging.INFO,
)
```

Then the engine can use it in the same way as any other tracer implementation.

## `LoggingTraceSpan`

`LoggingTraceSpan` logs:

```text
span start
span finish
span failure
span attributes
span events
elapsed time in milliseconds
```

Example log flow:

```text
Trace span started: use_case.handle
Trace span event: use_case.handle | event=handler.started
Trace span attribute: use_case.handle | command_type='CreateUserCommand'
Trace span finished: use_case.handle | elapsed_ms=12.431
```

If an exception occurs inside the span, it logs failure and returns `False`, allowing the exception to propagate.

## Why There Is No `ports.py`

The v2 codebase avoids extra port layers for simple framework contracts.

The tracing module uses direct names:

```text
tracer.py
  Tracer
  TraceSpan

logging_tracer.py
  LoggingTracer
  LoggingTraceSpan
```

This keeps the module easier to understand.

## Why There Is No `noop.py`

A no-op tracer is not required at this stage.

Engines can either:

```text
run without a tracer
or receive LoggingTracer as a default lightweight implementation
```

`LoggingTracer` is more useful than a silent no-op because it shows that spans are opened, enriched, and closed.

A true no-op tracer can be added later if there is a clear need.

## Engine Usage

A simple engine may use tracing like this:

```python
if tracer is None:
    result = await handler(message, context)
else:
    async with tracer.start_span(
        trace=trace,
        name="query.handle",
        attributes={
            "query_type": type(query).__qualname__,
        },
    ) as span:
        span.add_event("handler.started")
        result = await handler(query, context)
        span.add_event("handler.finished")
```

The engine should not know whether the tracer writes logs, sends OpenTelemetry spans, writes LangFuse spans, or does something else.

## Application-Specific Tracing

Applications may implement their own tracer.

Example:

```python
class OpenTelemetryTracer(Tracer[OpenTelemetryContext]):
    def start_span(
        self,
        *,
        trace: OpenTelemetryContext | None,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> TraceSpan:
        ...
```

The custom tracer only needs to satisfy the `Tracer` and `TraceSpan` contracts.

## Boundary Rules

The tracing module should not contain:

```text
engine logic
handler execution logic
event dispatch logic
OpenTelemetry-specific code
LangFuse-specific code
Phoenix-specific code
application request parsing
trace id extraction from HTTP headers
```

Those belong to application adapters or backend-specific integrations.

## Summary

The tracing module defines a small stable contract:

```text
Tracer
  creates spans

TraceSpan
  async span context manager with attributes/events

LoggingTracer
  default implementation backed by Python logging

LoggingTraceSpan
  logging-backed span implementation
```

This is enough for engines and dispatchers to add observability hooks without depending on a concrete tracing backend.
