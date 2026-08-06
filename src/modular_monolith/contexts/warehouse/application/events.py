from dataclasses import asdict, dataclass

from direttore import Event, EventHandler
from modular_monolith.contexts.warehouse.application.architecture import (
    WarehouseEventContext,
    event_registry,
)


@dataclass(frozen=True, slots=True)
class StockReceived(Event):
    product_id: str
    quantity: int
    new_balance: int


@event_registry.decorator_register(StockReceived)
class RecordStockReceivedHandler(EventHandler):
    async def handle(
        self,
        event: StockReceived,
        context: WarehouseEventContext,
    ) -> None:
        await context.uow.audits.record("stock_received", asdict(event))

