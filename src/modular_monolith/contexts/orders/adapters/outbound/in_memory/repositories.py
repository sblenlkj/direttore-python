from typing import cast

from direttore import ResourceHolder
from modular_monolith.contexts.orders.application.errors import (
    OrderAlreadyCancelledError,
    OrderAlreadyExistsError,
    OrderNotFoundError,
)
from modular_monolith.contexts.orders.domain import Order, OrderStatus
from modular_monolith.shared.database import InMemorySession


class _Repository:
    def __init__(self, resources: ResourceHolder) -> None:
        self._resources = resources

    async def _session(self, *, write: bool) -> InMemorySession:
        session = await self._resources.get_session("primary", commit=write)
        return cast(InMemorySession, session)


class InMemoryOrderRepository(_Repository):
    async def add(self, order: Order) -> Order:
        session = await self._session(write=True)
        session.record_access("orders.orders.add")
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
        session.record_access("orders.orders.get")
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
        session.record_access("orders.orders.cancel")
        order = await self.get(order_id)
        if order.status is OrderStatus.CANCELLED:
            raise OrderAlreadyCancelledError(order_id)
        session.orders[order_id]["status"] = OrderStatus.CANCELLED.value
        return Order(order.order_id, order.product_id, order.quantity, OrderStatus.CANCELLED)


class InMemoryOrderAuditRepository(_Repository):
    async def record(self, kind: str, values: dict[str, object]) -> None:
        session = await self._session(write=True)
        session.record_access("orders.audits.record")
        session.audits.append({"context": "orders", "kind": kind, **values})

