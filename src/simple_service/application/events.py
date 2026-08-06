from dataclasses import asdict, dataclass

from direttore import Event, EventHandler
from simple_service.application.architecture import (
    ApplicationEventContext,
    event_registry,
)


@dataclass(frozen=True, slots=True)
class StockReceived(Event):
    product_id: str
    quantity: int
    new_balance: int


@dataclass(frozen=True, slots=True)
class OrderPlaced(Event):
    order_id: str
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderCancelled(Event):
    order_id: str
    product_id: str
    quantity: int


@event_registry.decorator_register(StockReceived)
class RecordStockReceivedHandler(EventHandler):
    async def handle(
        self,
        event: StockReceived,
        context: ApplicationEventContext,
    ) -> None:
        await context.uow.movements.record("stock_received", asdict(event))


@event_registry.decorator_register(OrderPlaced)
class RecordOrderPlacedHandler(EventHandler):
    async def handle(
        self,
        event: OrderPlaced,
        context: ApplicationEventContext,
    ) -> None:
        await context.uow.movements.record("order_placed", asdict(event))


@event_registry.decorator_register(OrderCancelled)
class RecordOrderCancelledHandler(EventHandler):
    async def handle(
        self,
        event: OrderCancelled,
        context: ApplicationEventContext,
    ) -> None:
        await context.uow.movements.record("order_cancelled", asdict(event))

