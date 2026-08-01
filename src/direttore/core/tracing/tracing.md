# Slot-owned tracing

Applications optionally configure a `SpanFactory`. A physical slot opens one
root span for a lease and creates a child for each command, query, event, or
compensation operation.

```text
slot lease
├── command A
│   └── event handler
├── query B
└── compensation C
```

The root stays open through saga persistence, resource finalization,
after-transaction events, cleanup, and release. The first operation's trace
input initializes the lease trace; later operations create children without a
global current-span mechanism.

Modular runtime invocation receives its parent `Span` explicitly and creates a
child boundary. The runtime never stores active span state. Handler contexts
receive only their active `Span | None`.

Tracing implementations must return `False` from `__aexit__`; tracing never
suppresses application exceptions.
