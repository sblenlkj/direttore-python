from typing import Protocol

from modular_monolith.contexts.warehouse.domain import Product


class ProductRepository(Protocol):
    async def add(self, product: Product) -> Product: ...

    async def get(self, product_id: str) -> Product: ...

    async def receive(self, product_id: str, quantity: int) -> Product: ...

    async def reserve(self, product_id: str, quantity: int) -> Product: ...

    async def release(self, product_id: str, quantity: int) -> Product: ...


class WarehouseAuditRepository(Protocol):
    async def record(self, kind: str, values: dict[str, object]) -> None: ...

