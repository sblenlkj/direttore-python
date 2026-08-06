from direttore import ResourceHolder
from simple_service.adapters.outbound.in_memory.repositories import (
    InMemoryMovementRepository,
    InMemoryOrderRepository,
    InMemoryProductRepository,
)
from simple_service.application.ports.unit_of_work import ApplicationUnitOfWork


class InMemoryApplicationUnitOfWork(ApplicationUnitOfWork):
    def __init__(self, resources: ResourceHolder) -> None:
        super().__init__(resources)
        self.products = InMemoryProductRepository(resources)
        self.orders = InMemoryOrderRepository(resources)
        self.movements = InMemoryMovementRepository(resources)

