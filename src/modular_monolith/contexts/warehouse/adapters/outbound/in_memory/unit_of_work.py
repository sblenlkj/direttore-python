from direttore import ResourceHolder
from modular_monolith.contexts.warehouse.adapters.outbound.in_memory.repositories import (
    InMemoryProductRepository,
    InMemoryWarehouseAuditRepository,
)
from modular_monolith.contexts.warehouse.application.ports.unit_of_work import (
    WarehouseUnitOfWork,
)


class InMemoryWarehouseUnitOfWork(WarehouseUnitOfWork):
    def __init__(self, resources: ResourceHolder) -> None:
        super().__init__(resources)
        self.products = InMemoryProductRepository(resources)
        self.audits = InMemoryWarehouseAuditRepository(resources)

