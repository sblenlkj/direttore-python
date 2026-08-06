# Warehouse examples

The same Warehouse and Orders domain is implemented with both Direttore
application variants. The examples use normal Python packages for all business
and bootstrap code; the notebooks focus on calling the applications and
inspecting their behavior.

## Run the notebooks

From the repository root:

```bash
uv sync --group examples
uv run --group examples jupyter lab examples
```

Open either:

- `simple_service/demo.ipynb` for one registry set and one root Unit of Work;
- `modular_monolith/demo.ipynb` for separate Warehouse and Orders contexts,
  registries, and UoWs over one shared resource boundary.

Both notebooks are deterministic and require no network service or external
database. Restart the kernel and run all cells to reset their state.

## Domain

Warehouse owns products with a product ID, name, and available quantity.
Orders owns placed or cancelled orders. Placing an order reserves Warehouse
stock; cancelling releases it. The complete shared contract is in
[`warehouse-domain.md`](warehouse-domain.md).

The scenarios cover:

- typed command execution;
- stable-key and stored-operation execution;
- lifecycle input;
- event dispatch;
- adapter injection through application ports;
- Unit of Work-owned repositories;
- one lazily-created session reused through an operation;
- commit, rollback, and close behavior;
- pool provider statistics;
- typed saga compensation;
- modular in-process cross-context invocation.

## Structure

```text
src/
  direttore/
  simple_service/
    adapters/outbound/in_memory/
    application/
      architecture.py
      inventory.py
      orders.py
      events.py
      ports/
    domain/
    shared/
    bootstrap/
  modular_monolith/
    contexts/
      warehouse/
        adapters/
        application/
        domain/
        container.py
        context.py
      orders/
        adapters/
        application/
        domain/
        container.py
        context.py
    shared/
    bootstrap/

examples/
  README.md
  warehouse-domain.md
  simple_service/
    README.md
    demo.ipynb
  modular_monolith/
    README.md
    demo.ipynb
```

In each application or bounded context, `application/architecture.py` owns the
typed context aliases and registries. Registration modules decorate handlers,
then `bootstrap/registries.py` or each context's `context.py` imports those
modules before exporting populated registries.

Repositories are never dependency-container entries. A concrete UoW constructs
its repository adapters over the slot's `ResourceHolder`. Containers map
application port types to reusable adapter objects, such as the receipt client.
The modular execution-dependency registry separately creates the runtime-backed
Warehouse port required by Orders for each execution runtime.

For framework details, continue with the [core guide](../docs/README.md), the
[simple-service guide](../docs/simple-service.md), and the
[modular-monolith guide](../docs/modular-monolith.md).
