from direttore import BaseUnitOfWork
from simple_service.application.ports.repositories import (
    MovementRepository,
    OrderRepository,
    ProductRepository,
)


class ApplicationUnitOfWork(BaseUnitOfWork):
    products: ProductRepository
    orders: OrderRepository
    movements: MovementRepository

