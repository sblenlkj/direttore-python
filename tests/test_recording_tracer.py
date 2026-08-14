import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import pytest

from direttore.core.tracing import RecordingSpanFactory, SpanNode, render_trace


def run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coroutine)


def test_recording_tracer_publishes_complete_tree_once_on_root_exit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    callback_traces: list[SpanNode] = []
    factory: RecordingSpanFactory[dict[str, str]] = RecordingSpanFactory(
        on_trace_complete=callback_traces.append,
    )

    async def scenario() -> None:
        span = factory.create_span(
            trace={"trace_id": "trace-100"},
            name="root",
            attributes={"message.kind": "command"},
        )
        assert factory.completed_traces == []

        async with span as root:
            root.set_attribute("handler", "ReceiveStockHandler")
            root.add_event("handler.started", {"attempt": 1})
            async with root.child(
                name="event-handler",
                attributes={"event": "StockReceived"},
            ):
                assert factory.completed_traces == []

        assert len(factory.completed_traces) == 1

    with caplog.at_level(logging.DEBUG, logger="direttore.tracing"):
        run(scenario())

    root = factory.completed_traces[0]
    assert callback_traces == [root]
    assert root.trace == {"trace_id": "trace-100"}
    assert root.status == "OK"
    assert root.attributes == {
        "message.kind": "command",
        "handler": "ReceiveStockHandler",
    }
    assert root.events[0].name == "handler.started"
    assert root.events[0].attributes == {"attempt": 1}
    assert root.children[0].status == "OK"
    assert root.children[0].attributes == {"event": "StockReceived"}
    assert sum("Trace [OK]" in record.message for record in caplog.records) == 1

    rendered = render_trace(root)
    assert "trace={'trace_id': 'trace-100'}" in rendered
    assert "handler.started" in rendered
    assert "event-handler [OK]" in rendered


def test_recording_tracer_marks_failed_root() -> None:
    factory: RecordingSpanFactory[None] = RecordingSpanFactory(log_on_exit=False)

    async def scenario() -> None:
        with pytest.raises(ValueError, match="failure"):
            async with factory.create_span(trace=None, name="root"):
                raise ValueError("failure")

    run(scenario())

    assert len(factory.completed_traces) == 1
    assert factory.completed_traces[0].status == "FAILED"
    assert factory.completed_traces[0].error == "ValueError"
