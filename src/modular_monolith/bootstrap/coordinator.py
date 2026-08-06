from direttore import ModularUnitOfWorkCoordinator
from modular_monolith.contexts.orders.adapters.outbound.in_memory.unit_of_work import (
    InMemoryOrdersUnitOfWork,
)
from modular_monolith.contexts.warehouse.adapters.outbound.in_memory.unit_of_work import (
    InMemoryWarehouseUnitOfWork,
)


class ApplicationCoordinator(ModularUnitOfWorkCoordinator):
    def register(self) -> None:
        self.register_use_case_uow(
            InMemoryWarehouseUnitOfWork(self.resource_holder)
        )
        self.register_use_case_uow(InMemoryOrdersUnitOfWork(self.resource_holder))

