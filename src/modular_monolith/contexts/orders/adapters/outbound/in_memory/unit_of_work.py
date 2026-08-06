from direttore import ResourceHolder
from modular_monolith.contexts.orders.adapters.outbound.in_memory.repositories import (
    InMemoryOrderAuditRepository,
    InMemoryOrderRepository,
)
from modular_monolith.contexts.orders.application.ports.unit_of_work import (
    OrdersUnitOfWork,
)


class InMemoryOrdersUnitOfWork(OrdersUnitOfWork):
    def __init__(self, resources: ResourceHolder) -> None:
        super().__init__(resources)
        self.orders = InMemoryOrderRepository(resources)
        self.audits = InMemoryOrderAuditRepository(resources)

