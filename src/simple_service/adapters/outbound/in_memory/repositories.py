from typing import cast

from direttore import ResourceHolder
from simple_service.adapters.outbound.in_memory.database import InMemorySession
from simple_service.application.errors import (
    InsufficientStockError,
    OrderAlreadyCancelledError,
    OrderAlreadyExistsError,
    OrderNotFoundError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from simple_service.domain import Order, OrderStatus, Product


class _Repository:
    def __init__(self, resources: ResourceHolder) -> None:
        self._resources = resources

    async def _session(self, *, write: bool) -> InMemorySession:
        resource = await self._resources.get_session("primary", commit=write)
        return cast(InMemorySession, resource)


class InMemoryProductRepository(_Repository):
    async def add(self, product: Product) -> Product:
        session = await self._session(write=True)
        session.record_access("products.add")
        if product.product_id in session.products:
            raise ProductAlreadyExistsError(product.product_id)
        session.products[product.product_id] = {
            "product_id": product.product_id,
            "name": product.name,
            "quantity": product.quantity,
        }
        return product

    async def get(self, product_id: str) -> Product:
        session = await self._session(write=False)
        session.record_access("products.get")
        data = session.products.get(product_id)
        if data is None:
            raise ProductNotFoundError(product_id)
        return Product(**data)

    async def receive(self, product_id: str, quantity: int) -> Product:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        session = await self._session(write=True)
        session.record_access("products.receive")
        product = await self.get(product_id)
        updated = Product(product.product_id, product.name, product.quantity + quantity)
        session.products[product_id] = {
            "product_id": updated.product_id,
            "name": updated.name,
            "quantity": updated.quantity,
        }
        return updated

    async def reserve(self, product_id: str, quantity: int) -> Product:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        session = await self._session(write=True)
        session.record_access("products.reserve")
        product = await self.get(product_id)
        if product.quantity < quantity:
            raise InsufficientStockError(
                f"requested={quantity}, available={product.quantity}"
            )
        updated = Product(product.product_id, product.name, product.quantity - quantity)
        session.products[product_id]["quantity"] = updated.quantity
        return updated

    async def release(self, product_id: str, quantity: int) -> Product:
        return await self.receive(product_id, quantity)


class InMemoryOrderRepository(_Repository):
    async def add(self, order: Order) -> Order:
        session = await self._session(write=True)
        session.record_access("orders.add")
        if order.order_id in session.orders:
            raise OrderAlreadyExistsError(order.order_id)
        session.orders[order.order_id] = {
            "order_id": order.order_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "status": order.status.value,
        }
        return order

    async def get(self, order_id: str) -> Order:
        session = await self._session(write=False)
        session.record_access("orders.get")
        data = session.orders.get(order_id)
        if data is None:
            raise OrderNotFoundError(order_id)
        return Order(
            order_id=str(data["order_id"]),
            product_id=str(data["product_id"]),
            quantity=int(data["quantity"]),
            status=OrderStatus(str(data["status"])),
        )

    async def cancel(self, order_id: str) -> Order:
        session = await self._session(write=True)
        session.record_access("orders.cancel")
        order = await self.get(order_id)
        if order.status is OrderStatus.CANCELLED:
            raise OrderAlreadyCancelledError(order_id)
        session.orders[order_id]["status"] = OrderStatus.CANCELLED.value
        return Order(order.order_id, order.product_id, order.quantity, OrderStatus.CANCELLED)


class InMemoryMovementRepository(_Repository):
    async def record(self, kind: str, values: dict[str, object]) -> None:
        session = await self._session(write=True)
        session.record_access("movements.record")
        session.movements.append({"kind": kind, **values})

