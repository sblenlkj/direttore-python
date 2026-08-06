from direttore import BaseUnitOfWork
from modular_monolith.contexts.orders.application.ports.repositories import (
    OrderAuditRepository,
    OrderRepository,
)


class OrdersUnitOfWork(BaseUnitOfWork):
    orders: OrderRepository
    audits: OrderAuditRepository

