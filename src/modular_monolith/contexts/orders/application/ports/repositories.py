from typing import Protocol

from modular_monolith.contexts.orders.domain import Order


class OrderRepository(Protocol):
    async def add(self, order: Order) -> Order: ...

    async def get(self, order_id: str) -> Order: ...

    async def cancel(self, order_id: str) -> Order: ...


class OrderAuditRepository(Protocol):
    async def record(self, kind: str, values: dict[str, object]) -> None: ...

