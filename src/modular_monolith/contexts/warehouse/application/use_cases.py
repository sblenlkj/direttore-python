from dataclasses import dataclass

from direttore import (
    SagaUseCaseHandlerResult,
    UseCaseCommand,
    UseCaseCommandCompensation,
    UseCaseHandler,
    UseCaseHandlerResult,
)
from modular_monolith.contexts.warehouse.application.architecture import (
    WarehouseHandlerContext,
    WarehouseSagaContext,
    use_case_registry,
)
from modular_monolith.contexts.warehouse.application.events import StockReceived
from modular_monolith.contexts.warehouse.application.ports.clients import (
    StockReceiptClient,
)
from modular_monolith.contexts.warehouse.domain import Product


@dataclass(frozen=True, slots=True)
class RegisterProductCommand(UseCaseCommand):
    product_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ReceiveStockCommand(UseCaseCommand):
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class GetStockCommand(UseCaseCommand):
    product_id: str


@dataclass(frozen=True, slots=True)
class ReserveStockCommand(UseCaseCommand):
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class ReleaseStockCommand(UseCaseCommand):
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class ProductSnapshot(UseCaseHandlerResult):
    product_id: str
    name: str
    quantity: int


@dataclass(frozen=True, slots=True)
class StockBalance(UseCaseHandlerResult):
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class ReverseStockReceipt(UseCaseCommandCompensation):
    product_id: str
    quantity: int


@use_case_registry.decorator_register(
    RegisterProductCommand,
    key="warehouse.register-product.v1",
)
class RegisterProductHandler(UseCaseHandler):
    async def handle(
        self,
        command: RegisterProductCommand,
        context: WarehouseHandlerContext,
    ) -> ProductSnapshot:
        product = await context.uow.products.add(
            Product(product_id=command.product_id, name=command.name)
        )
        return ProductSnapshot(product.product_id, product.name, product.quantity)


@use_case_registry.decorator_register(
    ReceiveStockCommand,
    key="warehouse.receive-stock.v1",
    saga_key="warehouse.receive-stock.compensation.v1",
    compensation_type=ReverseStockReceipt,
)
class ReceiveStockHandler(UseCaseHandler):
    def __init__(self, client: StockReceiptClient) -> None:
        self._client = client

    async def handle(
        self,
        command: ReceiveStockCommand,
        context: WarehouseHandlerContext,
    ) -> SagaUseCaseHandlerResult:
        await self._client.validate_receipt(command.product_id, command.quantity)
        product = await context.uow.products.receive(
            command.product_id, command.quantity
        )
        context.queue.push(
            StockReceived(command.product_id, command.quantity, product.quantity)
        )
        return SagaUseCaseHandlerResult(
            result=StockBalance(product.product_id, product.quantity),
            compensation=ReverseStockReceipt(command.product_id, command.quantity),
        )

    async def compensate(
        self,
        compensation: ReverseStockReceipt,
        context: WarehouseSagaContext,
    ) -> None:
        await context.uow.products.reserve(
            compensation.product_id, compensation.quantity
        )


@use_case_registry.decorator_register(GetStockCommand, key="warehouse.get-stock.v1")
class GetStockHandler(UseCaseHandler):
    async def handle(
        self,
        command: GetStockCommand,
        context: WarehouseHandlerContext,
    ) -> StockBalance:
        product = await context.uow.products.get(command.product_id)
        return StockBalance(product.product_id, product.quantity)


@use_case_registry.decorator_register(
    ReserveStockCommand,
    key="warehouse.reserve-stock.v1",
)
class ReserveStockHandler(UseCaseHandler):
    async def handle(
        self,
        command: ReserveStockCommand,
        context: WarehouseHandlerContext,
    ) -> StockBalance:
        product = await context.uow.products.reserve(
            command.product_id, command.quantity
        )
        return StockBalance(product.product_id, product.quantity)


@use_case_registry.decorator_register(
    ReleaseStockCommand,
    key="warehouse.release-stock.v1",
)
class ReleaseStockHandler(UseCaseHandler):
    async def handle(
        self,
        command: ReleaseStockCommand,
        context: WarehouseHandlerContext,
    ) -> StockBalance:
        product = await context.uow.products.release(
            command.product_id, command.quantity
        )
        return StockBalance(product.product_id, product.quantity)

