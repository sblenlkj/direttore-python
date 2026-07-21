# Tracer in BaseResourceHolder (Future Idea)

## Problem Statement

In the current architecture, tracing is handled by explicitly passing a `tracer`
through handler contexts. This works, but introduces several limitations:

- `tracer` must be explicitly propagated through all handler layers
- repositories and low-level components must receive tracer indirectly
- execution scope context is duplicated across multiple abstractions
- tracing is not consistently accessible across all execution-scoped resources

As the system grows, this leads to repetitive plumbing and inconsistent access
patterns for tracing within deeply nested components.

## Proposed Idea

Move `tracer` into the execution-scoped `ResourceHolder`, making it part of the
same lifecycle as database sessions, Redis clients, and other runtime resources.

Instead of passing `tracer` through handler contexts:

```
context.tracer -> explicit propagation
```

we would access it via execution scope:

```
resources.tracer
```

or:

```
uow.resources.tracer
```

## Desired Behavior

- `tracer` is initialized at engine/execution scope level
- `ResourceHolder` optionally holds a reference to the active tracer
- all execution-scoped components can access tracer without explicit injection
- tracer is automatically tied to execution lifecycle (enter/exit scope)

## Open Questions

### 1. Should tracer live in BaseResourceHolder?

Options:

- A. Direct field:
  - `BaseResourceHolder.tracer`
  - simple but couples holder to tracing system

- B. Factory-based resource:
  - `register("tracer", factory)`
  - consistent with other resources but awkward for global execution tracer

- C. Hybrid:
  - dedicated execution metadata field separate from resources map

### 2. Lifecycle ownership

- Who creates tracer?
  - Engine / execution runtime
- Who closes it?
  - ResourceHolder or engine?

### 3. Type safety

Possible approaches:

- generic `TraceT` parameter on ResourceHolder (currently not desired)
- untyped `Any` tracer (simple initial version)
- typed injection at application level only

## Preferred Direction (Current Thinking)

- Do NOT introduce tracer into BaseResourceHolder yet
- Keep tracer in handler context for now
- Evaluate after stabilizing execution engine and resource lifecycle
- Later unify tracer under execution scope if model proves stable

## Goal

Reduce boilerplate tracing propagation while maintaining:

- clear ownership boundaries
- predictable lifecycle management
- no premature coupling of core primitives to observability layer
