from typing import Protocol

from direttore.core.tracing import Span


class WarehouseContextClient(Protocol):
    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int: ...

    async def release(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int: ...
