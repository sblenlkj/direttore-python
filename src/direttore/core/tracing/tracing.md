# Slot-owned tracing

Applications optionally configure a `SpanFactory`. A plain slot creates one
span for its operation. A lease stores its current operation span in
`SlotExecutionCache`.

```text
command A span --closed/replaced--> command B span
                                      `-- reused by cache calls
```

Starting a normal lease operation closes the previous cached span and creates a
new one from that operation's trace input. Cache calls reuse the stored span.
Release closes the final cached span. There is no separate lease-root span or
global current-span mechanism.

Modular runtime invocation receives its parent `Span` explicitly and creates a
child boundary. The runtime never stores active span state. Handler contexts
receive only their active `Span | None`.

Tracing implementations must return `False` from `__aexit__`; tracing never
suppresses application exceptions.

## Included implementations

`LoggingSpanFactory` logs every span transition immediately. It is useful when
the execution timeline matters more than a single tree-shaped record.

`RecordingSpanFactory` accumulates a `SpanNode` tree. A root is appended to
`completed_traces` exactly once, after its `__aexit__` finishes the trace. The
factory then invokes an optional `on_trace_complete` callback and, when
`log_on_exit=True`, emits one rendered log entry. Running roots are not exposed
through `completed_traces`.

Recorded nodes retain their trace input on the root, attributes, events,
children, timing, status, and exception type. `render_trace(root)` produces a
compact tree for logs, notebooks, and tests.
