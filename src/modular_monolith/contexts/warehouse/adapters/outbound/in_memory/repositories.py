from typing import cast

from direttore import ResourceHolder
from modular_monolith.contexts.warehouse.application.errors import (
    InsufficientStockError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from modular_monolith.contexts.warehouse.domain import Product
from modular_monolith.shared.database import InMemorySession


class _Repository:
    def __init__(self, resources: ResourceHolder) -> None:
        self._resources = resources

    async def _session(self, *, write: bool) -> InMemorySession:
        session = await self._resources.get_session("primary", commit=write)
        return cast(InMemorySession, session)


class InMemoryProductRepository(_Repository):
    async def add(self, product: Product) -> Product:
        session = await self._session(write=True)
        session.record_access("warehouse.products.add")
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
        session.record_access("warehouse.products.get")
        data = session.products.get(product_id)
        if data is None:
            raise ProductNotFoundError(product_id)
        return Product(**data)

    async def receive(self, product_id: str, quantity: int) -> Product:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        session = await self._session(write=True)
        session.record_access("warehouse.products.receive")
        product = await self.get(product_id)
        updated = Product(product.product_id, product.name, product.quantity + quantity)
        session.products[product_id]["quantity"] = updated.quantity
        return updated

    async def reserve(self, product_id: str, quantity: int) -> Product:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        session = await self._session(write=True)
        session.record_access("warehouse.products.reserve")
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


class InMemoryWarehouseAuditRepository(_Repository):
    async def record(self, kind: str, values: dict[str, object]) -> None:
        session = await self._session(write=True)
        session.record_access("warehouse.audits.record")
        session.audits.append({"context": "warehouse", "kind": kind, **values})

