from dataclasses import dataclass

from direttore import UseCaseCommand, UseCaseHandler, UseCaseHandlerResult
from modular_monolith.contexts.orders.application.architecture import (
    OrdersHandlerContext,
    use_case_registry,
)
from modular_monolith.contexts.orders.application.events import (
    OrderCancelled,
    OrderPlaced,
)
from modular_monolith.contexts.orders.application.ports.warehouse_context_client import (
    WarehouseContextClient,
)
from modular_monolith.contexts.orders.domain import Order, OrderStatus


@dataclass(frozen=True, slots=True)
class PlaceOrderCommand(UseCaseCommand):
    order_id: str
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class GetOrderCommand(UseCaseCommand):
    order_id: str


@dataclass(frozen=True, slots=True)
class CancelOrderCommand(UseCaseCommand):
    order_id: str


@dataclass(frozen=True, slots=True)
class OrderSnapshot(UseCaseHandlerResult):
    order_id: str
    product_id: str
    quantity: int
    status: str


def _snapshot(order: Order) -> OrderSnapshot:
    return OrderSnapshot(
        order.order_id,
        order.product_id,
        order.quantity,
        order.status.value,
    )


@use_case_registry.decorator_register(PlaceOrderCommand, key="orders.place-order.v1")
class PlaceOrderHandler(UseCaseHandler):
    def __init__(self, warehouse: WarehouseContextClient) -> None:
        self._warehouse = warehouse

    async def handle(
        self,
        command: PlaceOrderCommand,
        context: OrdersHandlerContext,
    ) -> OrderSnapshot:
        await self._warehouse.reserve(
            command.product_id,
            command.quantity,
            span=context.span,
        )
        order = await context.uow.orders.add(
            Order(command.order_id, command.product_id, command.quantity)
        )
        context.queue.push(
            OrderPlaced(order.order_id, order.product_id, order.quantity)
        )
        return _snapshot(order)


@use_case_registry.decorator_register(GetOrderCommand, key="orders.get-order.v1")
class GetOrderHandler(UseCaseHandler):
    async def handle(
        self,
        command: GetOrderCommand,
        context: OrdersHandlerContext,
    ) -> OrderSnapshot:
        return _snapshot(await context.uow.orders.get(command.order_id))


@use_case_registry.decorator_register(CancelOrderCommand, key="orders.cancel-order.v1")
class CancelOrderHandler(UseCaseHandler):
    def __init__(self, warehouse: WarehouseContextClient) -> None:
        self._warehouse = warehouse

    async def handle(
        self,
        command: CancelOrderCommand,
        context: OrdersHandlerContext,
    ) -> OrderSnapshot:
        current = await context.uow.orders.get(command.order_id)
        await self._warehouse.release(
            current.product_id,
            current.quantity,
            span=context.span,
        )
        order = await context.uow.orders.cancel(command.order_id)
        context.queue.push(
            OrderCancelled(order.order_id, order.product_id, order.quantity)
        )
        assert order.status is OrderStatus.CANCELLED
        return _snapshot(order)
