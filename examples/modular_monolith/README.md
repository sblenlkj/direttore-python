# Modular-monolith warehouse example

This project implements the Warehouse and Orders domain as two bounded
contexts. Each context owns its registries, handlers, ports, concrete in-memory
Unit of Work, and `context.py` composition point. Both contexts share one
execution resource through Direttore's modular Unit of Work coordinator.

Open `demo.ipynb` to run the example. The notebook shows that an Orders handler
receives a `WarehouseContextClient` port in its constructor and that its
`InProcessWarehouseContextClient` adapter invokes the Warehouse context with
the active runtime. Repositories are created inside the concrete UoWs and
never registered in either container.
Reusable code lives in
[`src/modular_monolith`](../../src/modular_monolith); this examples directory
contains presentation material only.
