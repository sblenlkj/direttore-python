# AGENT.md

## Project purpose

Direttore is a Python 3.12 orchestration framework for application-layer message handling.

Its purpose is to coordinate use cases, queries, and events without forcing application code to depend on transport details, infrastructure setup, or transaction-management mechanics.

The framework is responsible for:

- registering message handlers;
- resolving the correct handler for a message;
- opening and closing execution resources;
- coordinating units of work and transactions;
- dispatching domain and integration events;
- preparing per-execution lifecycle state;
- invoking handlers through explicit contracts;
- supporting both simple services and modular monoliths;
- integrating tracing without coupling handlers to a concrete tracing implementation.

Direttore is not a dependency-injection container, web framework, ORM, or domain framework. It provides application orchestration around user-defined messages, handlers, units of work, resources, and lifecycle policies.

## Design principles

### Explicit execution flow

Core execution stages should be visible in code. Prefer named methods such as `handle` over magic invocation through `__call__`.

### Framework-owned orchestration

The framework owns:

- resource opening and closing;
- transaction boundaries;
- event dispatch;
- handler resolution;
- lifecycle sequencing;
- tracing integration.

Application code owns:

- commands, queries, and events;
- handlers;
- units of work;
- resource implementations;
- lifecycle-context types;
- lifecycle implementations;
- repositories and gateways.

### Registry-driven behaviour

Handler-specific execution metadata belongs to registrations.

Registries determine:

- which handler type handles a message;
- which lifecycle applies;
- which configuration applies;
- which execution mode applies;
- optional keyed lookup;
- source metadata.

Global configuration should not contain handler-specific authentication, authorisation, or execution policies.

### Stateless shared components

Registries, lifecycles, resolvers, and similar framework components may be shared between concurrent executions.

Per-execution mutable data must not be stored on shared lifecycle instances. It belongs in a fresh lifecycle context created for each execution.

### Typed but generic application state

The framework-owned handler context contains infrastructure fields and one user-defined lifecycle context:

```python
context.lifecycle_context
```

The lifecycle context may contain any application-specific state, for example:

- authentication claims;
- current session;
- current user;
- permissions;
- tenant;
- locale;
- request metadata.

Direttore passes this object through the lifecycle and into the handler without interpreting its fields.

### Python 3.12 style

Use Python 3.12 and PEP 695 generic syntax.

Prefer:

```python
class Registry[RegistrationT]:
    ...
```

Do not introduce `TypeVar` and `Generic` unless compatibility constraints explicitly require them.

## Execution model

A typical command or query execution follows this sequence:

1. Receive the message and user-provided invocation input.
2. Resolve the handler registration.
3. Resolve or instantiate the handler.
4. Read the effective lifecycle, handler config, and execution metadata.
5. Create a fresh lifecycle context.
6. Run the lifecycle hook before resources are opened.
7. Open the resource holder or modular coordinator resources.
8. Obtain the unit of work and other execution dependencies.
9. Run the lifecycle hook after resources are opened.
10. Build the framework-owned handler context.
11. Invoke `handler.handle(message, context)`.
12. Commit or roll back according to the execution mode.
13. Dispatch queued events.
14. Close resources.
15. Finalise tracing.

The exact transaction and event order depends on the use-case execution mode and engine implementation.

## Main package structure

The source package is located under:

```text
src/direttore
```

### `application`

High-level application façades and execution-slot management.

```text
application/
├── base_execution_slot.py
├── execution_slot_pool.py
├── simple_service/
└── modular_monolith/
```

#### `base_execution_slot.py`

Defines the common execution-slot abstraction used to host or reuse execution infrastructure.

Execution slots should remain orchestration objects. They should not contain application business logic.

#### `execution_slot_pool.py`

Manages execution-slot reuse and lifecycle.

#### `application/simple_service`

Public application layer for a service with one resource-holder model.

Expected responsibilities:

- application configuration;
- construction of simple-service engines;
- public command/query invocation;
- execution-slot integration.

#### `application/modular_monolith`

Public application layer for modular-monolith execution.

Expected responsibilities:

- modular application configuration;
- coordinator integration;
- module-aware engine construction;
- public invocation APIs.

Application façades should delegate execution mechanics to engines rather than duplicating engine logic.

### `core/contracts`

Public framework contracts used by application code.

```text
core/contracts/
├── handlers/
├── lifecycle/
└── messages.py
```

#### `messages.py`

Defines base message categories:

- use-case commands;
- queries;
- events.

Messages should remain transport-independent data objects.

#### `contracts/handlers`

Defines handler contracts, handler contexts, configs, and result types.

Expected contracts:

- `UseCaseHandler`;
- `QueryHandler`;
- `EventHandler`.

Handlers expose an explicit async `handle` method.

Use-case and query contexts are framework-owned dataclasses. They contain infrastructure references and the user-defined lifecycle context.

Use-case handler configuration contains lifecycle-relevant metadata such as allowed access tags.

Use-case execution mode is registration metadata, not lifecycle configuration.

#### `contracts/lifecycle`

Defines lifecycle contracts for the simple-service execution model.

Expected contracts:

- `UseCaseLifecycle`;
- `QueryLifecycle`.

A lifecycle:

- creates a fresh per-execution lifecycle context;
- may enrich it before resources are opened;
- may enrich it after resources are opened.

Default lifecycle hook implementations should be no-ops where practical, so implementations only override required stages.

### `core/engines`

Contains orchestration engines.

```text
core/engines/
├── base_engine.py
├── config.py
├── simple_service/
└── modular_monolith/
```

Engines are responsible for execution sequencing.

They should:

- resolve registrations and handlers;
- call lifecycle stages;
- open resources;
- construct handler contexts directly;
- invoke handlers;
- manage transaction flow;
- coordinate event dispatch;
- propagate tracing state.

They should not:

- contain application-specific authentication logic;
- construct user-specific handler-context subclasses;
- require handler-context factories;
- inspect lifecycle-context fields;
- duplicate registry logic.

#### `engines/simple_service`

Command and query engines for one service/resource-holder model.

#### `engines/modular_monolith`

Command and query engines that use the modular coordinator and UoW routing.

Modular lifecycle after-open hooks receive the concrete `Coordinator` when cross-module resources are required.

### `core/event_dispatchers`

Contains event-dispatch orchestration.

```text
core/event_dispatchers/
├── base_event_dispatcher.py
├── simple_service_event_dispatcher.py
└── modular_monolith_event_dispatcher.py
```

Event dispatchers resolve event handlers and invoke them through `handle`.

They should preserve the same explicit-contract style used by command and query handlers.

Simple-service and modular-monolith dispatchers differ in resource and coordinator access, not in event semantics.

### `core/modular_monolith_support`

Infrastructure specific to modular-monolith execution.

```text
core/modular_monolith_support/
├── coordinator.py
├── execution_dependencies.py
├── execution_runtime.py
├── lifecycle/
└── uow_routing_registries/
```

#### `coordinator.py`

Coordinates access to module resources and units of work during one execution.

The coordinator is a concrete framework object and should not be made generic without a real type-level requirement.

#### `execution_dependencies.py`

Groups dependencies needed to construct or run modular execution.

#### `execution_runtime.py`

Stores runtime state required during modular execution.

Keep runtime state separate from user lifecycle state.

#### `modular_monolith_support/lifecycle`

Defines:

- `ModularUseCaseLifecycle`;
- `ModularQueryLifecycle`.

These contracts mirror simple-service lifecycle contracts, but their after-open hooks may use the coordinator.

#### `uow_routing_registries`

Maps message types or handler execution paths to module-specific units of work.

Routing registries should only express routing. They should not execute handlers or own transactions.

### `core/primitives`

Low-level reusable execution primitives.

```text
core/primitives/
├── container.py
├── event_queue.py
├── resource_holder.py
└── uow.py
```

#### `container.py`

Abstraction for resolving application services or handler instances where required.

#### `event_queue.py`

Per-execution event collection used by use-case handlers and dispatch flow.

#### `resource_holder.py`

Abstraction for resources opened during execution.

A resource holder may expose database connections, units of work, or other managed resources.

#### `uow.py`

Base unit-of-work contracts.

Transaction semantics should remain explicit and engine-controlled.

### `core/registries`

Stores handler registrations.

```text
core/registries/
├── base_handler_registry.py
├── registrations.py
├── use_case_handler_registry.py
├── query_handler_registry.py
├── event_handler_registry.py
└── errors.py
```

#### `registrations.py`

Defines immutable registration records.

A use-case registration should contain:

- command type;
- handler type;
- lifecycle;
- execution mode;
- handler config;
- optional key;
- optional source name.

A query registration should contain:

- query type;
- handler type;
- lifecycle;
- handler config;
- optional key;
- optional source name.

An event registration contains event-specific handler metadata.

#### `base_handler_registry.py`

Implements common storage, lookup, duplicate detection, keyed access, iteration, and merge behaviour.

#### Concrete registries

Concrete registries validate message and handler types and expose registration APIs.

Each use-case and query registry should have a default lifecycle. A registration may override it.

The effective lifecycle should be resolved at registration time where possible, so engines do not need ambiguous `None` handling.

### `core/resolvers`

Resolves registered handler types into executable handler instances.

```text
core/resolvers/
├── base_handler_resolver.py
├── use_case_handler_resolver.py
├── query_handler_resolver.py
├── event_handler_resolver.py
└── resolved_handlers.py
```

Resolvers bridge registrations and the application container.

They should not:

- execute handlers;
- open resources;
- run lifecycle hooks;
- manage transactions.

Resolved-handler wrappers should preserve explicit `handle` invocation.

### `core/tracing`

Tracing contracts and implementations.

```text
core/tracing/
├── tracer.py
├── logging_tracer.py
└── config.py
```

Tracing is runtime-owned because the framework controls execution boundaries, nested invocation, events, and resource stages.

Tracing should not be implemented as lifecycle state.

The user lifecycle context may contain correlation or request metadata, but the tracer itself remains part of runtime configuration and handler infrastructure.

### `core/modules`

Legacy or optional framework modules.

The existing auth-specific module is transitional.

Authentication and authorisation should be implemented through application-defined lifecycle implementations and lifecycle-context state rather than permanent special framework ports.

Avoid adding new dependencies on the auth module during ongoing lifecycle refactoring.

## Handler contracts

### Use-case handlers

Use-case handlers mutate application state through a unit of work and may enqueue events.

Conceptual shape:

```python
class CreateOrderHandler(UseCaseHandler):
    async def handle(
        self,
        command: CreateOrder,
        context: UseCaseHandlerContext[
            OrderUnitOfWork,
            ApplicationLifecycleContext,
            ApplicationTracer,
        ],
    ) -> UseCaseHandlerResult:
        ...
```

### Query handlers

Query handlers read application state and return query results.

```python
class GetOrderHandler(QueryHandler):
    async def handle(
        self,
        query: GetOrder,
        context: QueryHandlerContext[
            OrderUnitOfWork,
            ApplicationLifecycleContext,
            ApplicationTracer,
        ],
    ) -> QueryHandlerResult:
        ...
```

### Event handlers

Event handlers react to events and are invoked explicitly through `handle`.

The event model may differ from command/query lifecycle handling, but event invocation should remain consistent and explicit.

## Lifecycle contracts

Lifecycle is generic execution preparation, not authentication-specific middleware.

A typical lifecycle context:

```python
@dataclass(slots=True)
class ApplicationLifecycleContext:
    current_user: User | None = None
    session: Session | None = None
    permissions: frozenset[str] = frozenset()
    tenant: Tenant | None = None
```

A lifecycle implementation may:

- parse transport metadata before resources open;
- load sessions after resources open;
- validate access tags from handler config;
- resolve tenant state;
- prepare handler-visible application context.

Lifecycle methods must mutate the same context object later passed to the handler.

Do not create a second execution-context abstraction and copy fields between objects.

## Configuration boundaries

### Application config

Application config should contain framework-wide construction dependencies, such as:

- registries;
- resolvers;
- resource-holder factories;
- coordinator factories;
- tracing configuration;
- execution-slot configuration.

It should not contain handler-context factories.

### Handler config

Handler config contains metadata intended for lifecycle or handler-adjacent policies.

Current example:

```python
allowed_access_tags: frozenset[str] | None
```

### Registration metadata

Registration metadata contains engine-facing execution policy.

Current example:

```python
execution_mode
```

Do not mix engine-only execution policy into handler config.

## Naming conventions

Use these names consistently:

- `handle` for handler invocation;
- `dispatch` or the established public application verb for top-level routing;
- `lifecycle_context` for user-defined per-execution state;
- `create_context` for lifecycle-context construction;
- `before_resource_holder_opened`;
- `after_resource_holder_opened`;
- `execution_mode`;
- `allowed_access_tags`.

Avoid:

- handler `__call__`;
- `outs`;
- auth-specific context names in generic contracts;
- vague names such as `process` where `handle` is clearer;
- multiple aliases for the same execution stage.

## Concurrency rules

Every execution must receive a distinct lifecycle-context instance.

Never store mutable request data on:

- lifecycle singletons;
- registries;
- resolvers;
- engines shared across requests;
- application configuration objects.

Use execution-local objects for all mutable state.

## Error-handling expectations

Framework errors should be specific and raised close to the violated invariant.

Examples:

- duplicate handler registration;
- missing handler registration;
- duplicate key;
- unknown key;
- invalid message type;
- invalid handler type;
- invalid routing configuration;
- missing unit-of-work route.

Do not convert programming/configuration errors into silent fallbacks.

## Change guidelines for agents

When modifying this repository:

1. Inspect the relevant contract, registration, resolver, engine, and application façade together.
2. Search all invocation paths before changing a public method name.
3. Keep simple-service and modular-monolith implementations aligned.
4. Update exports in `__init__.py`.
5. Update tests and executable documentation examples.
6. Preserve Python 3.12 typing style.
7. Avoid introducing new factories unless object construction cannot remain framework-owned.
8. Keep engine code orchestration-focused.
9. Keep user-specific state inside lifecycle context.
10. Run formatter, linter, type checker, and tests before completing the change.

## Verification checklist

For repository-wide refactors, search for stale references to:

```text
__call__
outs
auth
execution_mode
allowed_access_tags
lifecycle_context
before_resource_holder_opened
after_resource_holder_opened
```

Review every match rather than applying blind replacement.

Verify that:

- all handlers expose `handle`;
- all production invocation sites use `handle`;
- each execution creates a fresh lifecycle context;
- the same lifecycle-context object reaches lifecycle hooks and handler;
- execution mode is stored on use-case registration;
- handler config is passed to lifecycle hooks;
- engines directly create framework-owned handler contexts;
- no handler-context factory is required;
- modular after-open hooks receive the coordinator;
- tests cover default lifecycle and registration overrides.

## Non-goals

Do not use this framework to define domain entities, repositories, transport schemas, HTTP routing, persistence models, or dependency-injection policy.

Direttore should remain focused on application orchestration and execution lifecycle.
