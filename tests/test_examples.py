import asyncio
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from direttore.core.tracing import SpanNode

EXAMPLE_SOURCE_ROOT = (
    Path(__file__).parents[2] / "python_direttore_example" / "src"
)
sys.path.insert(0, str(EXAMPLE_SOURCE_ROOT))

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


def trace_names(root: SpanNode) -> list[str]:
    return [
        root.name,
        *(name for child in root.children for name in trace_names(child)),
    ]


def test_simple_service_validation_writes_handler_resolution_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "simple_validation_results.md"

    build_simple_application().application.validate(report_path)

    report = report_path.read_text(encoding="utf-8")
    assert report.startswith("# Context: simple_service\n")
    assert "## Use case handlers" in report
    assert "2. Handler: simple_service.application.inventory.ReceiveStockHandler" in report
    assert "Registered by key: warehouse.receive-stock.v1" in report
    assert (
        "Registered by saga key: warehouse.receive-stock.compensation.v1"
        in report
    )
    assert "client: simple_service.application.ports.clients.StockReceiptClient" in report
    assert "Source: container" in report
    assert (
        "Implementation: "
        "simple_service.adapters.outbound.clients.RecordingStockReceiptClient"
        in report
    )
    assert "## Event handlers" in report
    assert "1. Handler: simple_service.application.events.RecordStockReceivedHandler" in report
    assert "Cache: application (cached)" in report
    assert "Kind:" not in report


def test_modular_validation_reports_execution_override_and_cache_policy(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "modular_validation_results.md"

    build_modular_application().application.validate(report_path)

    report = report_path.read_text(encoding="utf-8")
    assert report.startswith("# Context: warehouse\n")
    assert "\n# Context: orders\n" in report
    assert "## Use case handlers" in report
    assert "1. Handler: modular_monolith.contexts.orders.application.use_cases.PlaceOrderHandler" in report
    assert "Registered by key: orders.place-order.v1" in report
    assert (
        "warehouse: modular_monolith.contexts.orders.application.ports."
        "warehouse_context_client.WarehouseContextClient"
        in report
    )
    assert "Source: execution override" in report
    assert (
        "Implementation: modular_monolith.contexts.orders.adapters."
        "in_process_warehouse_context_client.InProcessWarehouseContextClient"
        in report
    )
    assert "Cache: execution (not cached)" in report
    assert (
        "1. Handler: modular_monolith.contexts.orders.application.events."
        "RecordOrderPlacedHandler"
        in report
    )
    assert "## Event handlers" in report
    assert "Kind:" not in report


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
        order = await example.application.handle_operation(
            "place-100",
            trace={"trace_id": "simple-place-100"},
        )

        assert order.status == "placed"
        operation_accesses = example.database.access_log[access_start:]
        assert len({session_id for _, session_id in operation_accesses}) == 1
        operation_trace = example.tracer.completed_traces[-1]
        assert operation_trace.trace == {"trace_id": "simple-place-100"}
        assert operation_trace.status == "OK"
        assert any(
            "RecordOrderPlacedHandler" in name
            for name in trace_names(operation_trace)
        )
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
            ModularPlaceOrderCommand("O-100", "P-100", 3),
            trace={"trace_id": "modular-place-100"},
        )
        assert order.status == "placed"

        operation_accesses = example.database.access_log[access_start:]
        operation_names = {name for name, _ in operation_accesses}
        assert "warehouse.products.reserve" in operation_names
        assert "orders.orders.add" in operation_names
        assert len({session_id for _, session_id in operation_accesses}) == 1
        operation_trace = example.tracer.completed_traces[-1]
        assert operation_trace.trace == {"trace_id": "modular-place-100"}
        assert operation_trace.status == "OK"
        assert any("runtime.invoke" in name for name in trace_names(operation_trace))
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
