from direttore import ModularMonolithExecutionRuntime
from direttore.core.tracing import Span
from modular_monolith.contexts.warehouse.application.use_cases import (
    ReleaseStockCommand,
    ReserveStockCommand,
    StockBalance,
)


class InProcessWarehouseContextClient:
    def __init__(self, runtime: ModularMonolithExecutionRuntime) -> None:
        self._runtime = runtime

    async def reserve(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        result = await self._runtime.invoke(
            ReserveStockCommand(product_id, quantity),
            span=span,
        )
        if not isinstance(result, StockBalance):
            raise TypeError("ReserveStock must return StockBalance")
        return result.quantity

    async def release(
        self,
        product_id: str,
        quantity: int,
        *,
        span: Span | None = None,
    ) -> int:
        result = await self._runtime.invoke(
            ReleaseStockCommand(product_id, quantity),
            span=span,
        )
        if not isinstance(result, StockBalance):
            raise TypeError("ReleaseStock must return StockBalance")
        return result.quantity
