# Warehouse and Orders domain specification

This document defines the domain shared by the implemented simple-service and
modular-monolith examples. The executable code remains in the two example
packages.

## Domain language

### Warehouse context

The Warehouse context owns products and their available quantity.

A product has:

| Field | Type | Rule |
| --- | --- | --- |
| `product_id` | string | Stable, non-empty, unique identifier. |
| `name` | string | Non-empty display name. |
| `quantity` | integer | Available units; never negative. |

The example deliberately uses one quantity value rather than separate on-hand,
reserved, and available balances. Reserving stock decreases quantity; releasing
a reservation increases it.

Warehouse invariants:

- a product must exist before stock can be received or reserved;
- a product ID cannot be registered twice;
- received and reserved quantities must be positive;
- stock cannot be reserved when the requested quantity exceeds availability;
- a failed operation does not mutate product state.

### Orders context

The Orders context owns customer-independent orders.

An order has:

| Field | Type | Rule |
| --- | --- | --- |
| `order_id` | string | Stable, non-empty, unique identifier. |
| `product_id` | string | References the requested warehouse product. |
| `quantity` | integer | Positive number of requested units. |
| `status` | enum/string | `placed` or `cancelled` in the first version. |

Order invariants:

- an order ID cannot be placed twice;
- an order can be placed only after stock is reserved successfully;
- only a placed order can be cancelled;
- cancelling an order releases exactly its reserved quantity;
- a failed reservation means no order is stored.

## Messages and results

These public names and keys are used consistently in both example variants.

### Warehouse use cases

| Command | Input | Result | Purpose |
| --- | --- | --- | --- |
| `RegisterProduct` | product ID, name | product snapshot | Create a zero-stock product. |
| `ReceiveStock` | product ID, quantity | stock balance | Increase available stock. |
| `GetStock` | product ID | stock balance | Demonstrate read-only resource access. |
| `ReserveStock` | product ID, quantity | stock balance | Decrease stock or fail. |
| `ReleaseStock` | product ID, quantity | stock balance | Restore quantity after cancellation/compensation. |

Proposed stable keys:

| Command | Key |
| --- | --- |
| `RegisterProduct` | `warehouse.register-product.v1` |
| `ReceiveStock` | `warehouse.receive-stock.v1` |
| `GetStock` | `warehouse.get-stock.v1` |
| `ReserveStock` | `warehouse.reserve-stock.v1` |
| `ReleaseStock` | `warehouse.release-stock.v1` |

### Orders use cases

| Command | Input | Result | Purpose |
| --- | --- | --- | --- |
| `PlaceOrder` | order ID, product ID, quantity | order snapshot | Reserve stock, then store a placed order. |
| `GetOrder` | order ID | order snapshot | Demonstrate read-only Orders access. |
| `CancelOrder` | order ID | order snapshot | Mark cancelled and release stock. |

Proposed stable keys:

| Command | Key |
| --- | --- |
| `PlaceOrder` | `orders.place-order.v1` |
| `GetOrder` | `orders.get-order.v1` |
| `CancelOrder` | `orders.cancel-order.v1` |

### Events

| Event | Emitted by | Initial handler purpose |
| --- | --- | --- |
| `ProductRegistered` | product registration | Append an audit record. |
| `StockReceived` | stock receipt | Append a stock-movement record. |
| `StockReserved` | stock reservation | Append a stock-movement record. |
| `StockReleased` | release operation | Append a stock-movement record. |
| `OrderPlaced` | order placement | Append an order audit record. |
| `OrderCancelled` | cancellation | Append an order audit record. |

Events carry stable identifiers and the quantities necessary to explain the
fact. They should not expose repositories, sessions, UoWs, handlers, or
framework runtime objects.

## Request lifecycle

Both variants should define a small optional operation input:

| Field | Purpose |
| --- | --- |
| `actor_id` | Identifies the notebook user or calling process. |
| `correlation_id` | Groups visible logs and traces for one scenario. |

The lifecycle converts it into an immutable handler context. At least one
notebook call should omit input to demonstrate that Direttore passes `None` and
the lifecycle handles it explicitly.

The lifecycle should not open its own database transaction. It may inspect the
active holder and span, but resources remain owned by the execution slot.

## Resource and persistence model

The first implementation should use a session-shaped in-memory resource with
working state and committed state. It must expose observable commit, rollback,
and close operations so notebook readers can verify Direttore's behavior.

The resource will hold:

- products by product ID;
- orders by order ID;
- audit or movement records;
- an ordered transaction log used only for demonstration.

The concrete resource holder will register this resource as `primary`. Its
policy should:

- commit resources that were requested for writing;
- roll back resources used only for reading or when execution fails;
- close every created resource;
- mark the holder finalized after commit or rollback;
- permit the slot to reset holder state after close.

This design demonstrates holder mechanics. It is not intended to simulate all
database isolation behavior.

## Simple-service interpretation

The simple-service version combines Warehouse and Orders into:

- one use-case registry;
- one event registry;
- one root `ApplicationUnitOfWork`;
- one application dependency container;
- one `SimpleServiceSlotCreatorConfig`.

The Orders handler can depend on a normal application service that uses the
same UoW, or the single UoW can expose the repository operations needed by the
handler. The implementation should choose the smallest design that still keeps
domain decisions out of the notebook.

This version demonstrates how little configuration is needed when bounded
context routing is not required.

Its `application/architecture.py` owns the combined use-case and event
registries. `bootstrap/registries.py` explicitly imports the event and use-case
modules before exposing those populated registries to
`SimpleServiceHandlerConfig`. Domain entities stay under `domain/`, port types
under `application/ports/`, in-memory implementations under
`adapters/outbound/in_memory/`, and all final wiring under `bootstrap/`.

## Modular-monolith interpretation

The modular version preserves two explicit contexts.

Warehouse owns:

- the Warehouse message and result types;
- Warehouse handlers and registries;
- `WarehouseUnitOfWork` and its repository interface.

Orders owns:

- the Orders message and result types;
- Orders handlers and registries;
- `OrdersUnitOfWork` and its repository interface;
- a `WarehouseContextClient` outbound port used for reservation and release.

The composition root owns:

- the shared concrete resource holder;
- the coordinator registering both root UoWs;
- an execution dependency registry that creates an in-process
  `WarehouseContextClient` backed by the current modular runtime;
- the two `ModularMonolithDirettoreContext` values;
- the slot creator, provider, and application facade.

Each modular context follows the same internal shape:

```text
context_name/
  adapters/
  application/
    architecture.py
    events/
    ports/
    use_cases/
  domain/
  container.py
  context.py
```

`application/architecture.py` creates the context registries and handler
context aliases. Handler modules register against those objects. `context.py`
then imports the registration modules and exports the configured
`ModularMonolithDirettoreContext`. The context container binds ordinary
application-lifetime dependencies, while runtime-backed cross-context adapters
are assembled in `bootstrap/execution_dependencies.py`.

The implementation must not copy the reference project's legacy `queries/`
folders, query registries, query UoWs, or separate query resource holder.
`GetStock` and `GetOrder` are `UseCaseCommand` types, and their handlers access
the unified context UoW in read mode.

When `PlaceOrder` runs, the Orders handler asks its `WarehouseContextClient` to
reserve stock. The current in-process adapter invokes `ReserveStock` through
the runtime. The runtime resolves that nested command and routes it to
`WarehouseUnitOfWork`; it uses the active lifecycle context, event queue, and
shared holder. Only after reservation succeeds does the Orders handler store
the order.

This synchronous call is intentional: order placement needs an immediate
success or failure result. `OrderPlaced` remains an event for reactions that do
not decide whether the order can be accepted.

## Core notebook scenarios

### Scenario A: successful setup and order

Starting from empty state:

1. register product `P-100` named `Keyboard`;
2. receive 10 units;
3. place order `O-100` for 3 units;
4. execute `GetStock` for `P-100` and observe quantity 7;
5. execute `GetOrder` for `O-100` and observe status `placed`;
6. inspect audit records and transaction order.

### Scenario B: insufficient stock rollback

Starting with 7 units of `P-100`:

1. attempt to place `O-101` for 8 units;
2. catch and display the domain error;
3. verify product quantity remains 7;
4. verify `O-101` does not exist;
5. verify the failed execution rolled back and closed its resource.

### Scenario C: cancellation

Starting with placed order `O-100` and quantity 7:

1. cancel `O-100`;
2. release its 3 units;
3. observe quantity 10;
4. observe order status `cancelled`;
5. inspect `StockReleased` and `OrderCancelled` audit reactions.

Cancellation should use one local execution boundary. In modular mode, its
nested Warehouse call and Orders update share the same holder.

### Scenario D: explicit lease

Starting from empty state, use one lease transaction to:

1. register `P-200` named `Mouse`;
2. receive 5 units;
3. place `O-200` for 2 units;
4. verify that events drain after each lease operation;
5. verify business resources commit once when the transaction context exits.

This scenario must use sequential lease calls. It should not imply that one
lease supports concurrent notebook tasks.

### Scenario E: key and stored-operation execution

Use `handle_by_key` with `warehouse.receive-stock.v1` and a payload, then
configure an in-memory stored-operation loader and call `handle_operation` for
one prepared operation ID. Show that all three entry styles reach the same
registered behavior.

## Optional saga scenario

After the base example works, reservation may produce a compensation message
that releases exactly the reserved stock. The notebook can execute order work
with a saga ID, inspect the in-memory journal, and request compensation.

The example must make these limits explicit:

- compensation is executed in reverse entry order;
- compensation handlers are idempotent;
- the in-memory journal is demonstrative, not durable;
- compensation does not replace the transaction rollback used for an immediate
  failure inside one local execution.

## Comparison points to display

The notebooks should finish with a concise comparison:

| Concern | Simple service | Modular monolith |
| --- | --- | --- |
| Registries | One combined pair | One pair per context, merged by slot creator |
| Root UoWs | One | One per bounded context |
| Resource holder | One per slot | One per slot, shared by context UoWs |
| Handler routing | Direct to the service UoW | Handler type routes to context UoW |
| Cross-context call | Ordinary in-service collaboration | Interface plus runtime-backed execution override |
| Public facade | Simple-service facade | Modular-monolith facade |
| Lease semantics | Sequential, single commit | Same semantics across context work |

## Implemented verification scope

The example suite verifies that:

- both notebooks run from top to bottom in fresh kernels;
- both variants produce the same business results for the core scenarios;
- the simple-service notebook demonstrates direct, key-based, and
  stored-operation calls;
- the modular notebook demonstrates direct and nested cross-context calls;
- registry import locations are explicit;
- application validation succeeds before the first call;
- read calls do not request commit and write calls do;
- success commits and closes resources;
- failure rolls back and closes resources without state leakage;
- event ordering is visible and deterministic;
- the modular example visibly routes Warehouse and Orders handlers to their own
  UoWs over one holder;
- notebooks contain presentation logic while reusable code lives in modules;
- automated tests cover business invariants and transaction behavior outside
  the notebooks.

Transactional lease behavior is documented and tested in the framework's core
test suite; the example notebooks keep their main flow focused on composition,
resource reuse, rollback, events, and saga compensation.
