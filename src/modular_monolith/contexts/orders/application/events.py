from dataclasses import asdict, dataclass

from direttore import Event, EventHandler
from modular_monolith.contexts.orders.application.architecture import (
    OrdersEventContext,
    event_registry,
)


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


@event_registry.decorator_register(OrderPlaced)
class RecordOrderPlacedHandler(EventHandler):
    async def handle(
        self,
        event: OrderPlaced,
        context: OrdersEventContext,
    ) -> None:
        await context.uow.audits.record("order_placed", asdict(event))


@event_registry.decorator_register(OrderCancelled)
class RecordOrderCancelledHandler(EventHandler):
    async def handle(
        self,
        event: OrderCancelled,
        context: OrdersEventContext,
    ) -> None:
        await context.uow.audits.record("order_cancelled", asdict(event))

