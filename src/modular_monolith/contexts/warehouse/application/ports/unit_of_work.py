from direttore import BaseUnitOfWork
from modular_monolith.contexts.warehouse.application.ports.repositories import (
    ProductRepository,
    WarehouseAuditRepository,
)


class WarehouseUnitOfWork(BaseUnitOfWork):
    products: ProductRepository
    audits: WarehouseAuditRepository

