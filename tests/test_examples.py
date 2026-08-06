import asyncio
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

SOURCE_ROOT = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from modular_monolith.bootstrap.application import (  # noqa: E402
    build_application as build_modular_application,
)
from modular_monolith.contexts.orders.application.use_cases import (  # noqa: E402
    PlaceOrderCommand as ModularPlaceOrderCommand,
)
from modular_monolith.contexts.warehouse.application.errors import (  # noqa: E402
    InsufficientStockError as ModularInsufficientStockError,
)
from modular_monolith.contexts.warehouse.application.use_cases import (  # noqa: E402
    GetStockCommand as ModularGetStockCommand,
)
from modular_monolith.contexts.warehouse.application.use_cases import (  # noqa: E402
    ReceiveStockCommand as ModularReceiveStockCommand,
)
from modular_monolith.contexts.warehouse.application.use_cases import (  # noqa: E402
    RegisterProductCommand as ModularRegisterProductCommand,
)
from simple_service.application.errors import (  # noqa: E402
    InsufficientStockError,
)
from simple_service.application.inventory import (  # noqa: E402
    GetStockCommand,
    ReceiveStockCommand,
    RegisterProductCommand,
)
from simple_service.application.orders import PlaceOrderCommand  # noqa: E402
from simple_service.bootstrap.application import (  # noqa: E402
    build_application as build_simple_application,
)


def run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coroutine)


def test_simple_service_runs_direct_key_operation_and_saga_flows() -> None:
    example = build_simple_application()

    async def scenario() -> None:
        await example.application.handle(RegisterProductCommand("P-100", "Keyboard"))
        await example.application.handle_by_key(
            "warehouse.receive-stock.v1",
            {"product_id": "P-100", "quantity": 10},
        )

        example.database.operations["place-100"] = (
            "orders.place-order.v1",
            {"order_id": "O-100", "product_id": "P-100", "quantity": 3},
        )
        access_start = len(example.database.access_log)
        order = await example.application.handle_operation("place-100")

        assert order.status == "placed"
        operation_accesses = example.database.access_log[access_start:]
        assert len({session_id for _, session_id in operation_accesses}) == 1
        assert (await example.application.handle(GetStockCommand("P-100"))).quantity == 7

        with pytest.raises(InsufficientStockError):
            await example.application.handle(
                PlaceOrderCommand("O-101", "P-100", 8)
            )
        assert "O-101" not in example.database.orders
        assert example.database.products["P-100"]["quantity"] == 7

        await example.application.handle(
            ReceiveStockCommand("P-100", 2),
            saga_id="receipt-200",
        )
        assert example.database.products["P-100"]["quantity"] == 9
        await example.application.compensate_saga("receipt-200")
        assert example.database.products["P-100"]["quantity"] == 7

    run(scenario())

    assert example.receipt_client.calls == [("P-100", 10), ("P-100", 2)]
    assert example.database.transaction_log[-1][0] == "close"
    assert any(action == "rollback" for action, _ in example.database.transaction_log)


def test_modular_monolith_reuses_one_session_across_context_uows() -> None:
    example = build_modular_application()

    async def scenario() -> None:
        await example.application.handle(
            ModularRegisterProductCommand("P-100", "Keyboard")
        )
        await example.application.handle(
            ModularReceiveStockCommand("P-100", 10),
        )

        access_start = len(example.database.access_log)
        order = await example.application.handle(
            ModularPlaceOrderCommand("O-100", "P-100", 3)
        )
        assert order.status == "placed"

        operation_accesses = example.database.access_log[access_start:]
        operation_names = {name for name, _ in operation_accesses}
        assert "warehouse.products.reserve" in operation_names
        assert "orders.orders.add" in operation_names
        assert len({session_id for _, session_id in operation_accesses}) == 1
        assert (
            await example.application.handle(ModularGetStockCommand("P-100"))
        ).quantity == 7

        with pytest.raises(ModularInsufficientStockError):
            await example.application.handle(
                ModularPlaceOrderCommand("O-101", "P-100", 8)
            )
        assert "O-101" not in example.database.orders
        assert example.database.products["P-100"]["quantity"] == 7

        await example.application.handle(
            ModularRegisterProductCommand("P-200", "Mouse")
        )
        await example.application.handle(
            ModularReceiveStockCommand("P-200", 2),
            saga_id="receipt-200",
        )
        await example.application.compensate_saga("receipt-200")
        assert example.database.products["P-200"]["quantity"] == 0

    run(scenario())

    assert example.receipt_client.calls == [("P-100", 10), ("P-200", 2)]
    assert any(action == "rollback" for action, _ in example.database.transaction_log)
