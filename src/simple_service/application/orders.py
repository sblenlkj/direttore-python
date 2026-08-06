from dataclasses import dataclass

from direttore import UseCaseCommand, UseCaseHandler, UseCaseHandlerResult
from simple_service.application.architecture import (
    ApplicationHandlerContext,
    use_case_registry,
)
from simple_service.application.events import OrderCancelled, OrderPlaced
from simple_service.domain import Order, OrderStatus


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
    async def handle(
        self,
        command: PlaceOrderCommand,
        context: ApplicationHandlerContext,
    ) -> OrderSnapshot:
        await context.uow.products.reserve(command.product_id, command.quantity)
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
        context: ApplicationHandlerContext,
    ) -> OrderSnapshot:
        return _snapshot(await context.uow.orders.get(command.order_id))


@use_case_registry.decorator_register(CancelOrderCommand, key="orders.cancel-order.v1")
class CancelOrderHandler(UseCaseHandler):
    async def handle(
        self,
        command: CancelOrderCommand,
        context: ApplicationHandlerContext,
    ) -> OrderSnapshot:
        current = await context.uow.orders.get(command.order_id)
        await context.uow.products.release(current.product_id, current.quantity)
        order = await context.uow.orders.cancel(command.order_id)
        context.queue.push(
            OrderCancelled(order.order_id, order.product_id, order.quantity)
        )
        assert order.status is OrderStatus.CANCELLED
        return _snapshot(order)
