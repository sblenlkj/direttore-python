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
