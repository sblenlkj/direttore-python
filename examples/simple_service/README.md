# Warehouse simple-service example

This project implements Warehouse and Orders behind one Direttore registry set
and one root unit of work. Run `demo.ipynb` after installing the `examples`
dependency group with `uv sync --group examples`.

The implementation lives in [`src/simple_service`](../../src/simple_service).
Repositories are assembled by `InMemoryApplicationUnitOfWork`; the dependency
container holds only the `StockReceiptClient` port adapter.
