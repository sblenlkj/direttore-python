import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

from direttore.application.simple_service import (
    SimpleServiceDirettoreApplication,
    SimpleServiceHandlerConfig,
    SimpleServiceSlotConfig,
    SimpleServiceSlotCreator,
    SimpleServiceSlotCreatorConfig,
)
from direttore.application.slot_provider import PoolExecutionSlotProvider
from direttore.core.contracts.handlers import (
    EventHandler,
    SagaEventHandlerResult,
    SagaUseCaseHandlerResult,
    UseCaseHandler,
    UseCaseHandlerResult,
)
from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.messages import (
    Event,
    EventCompensation,
    UseCaseCommand,
    UseCaseCommandCompensation,
)
from direttore.core.primitives import BaseUnitOfWork, Container
from direttore.core.registries import EventHandlerRegistry, UseCaseHandlerRegistry
from direttore.core.saga import (
    InMemorySagaJournal,
    SagaRecord,
)
from direttore.core.tracing import Span, SpanFactory
from tests.helpers import SessionResourceHolder


@dataclass
class Happened(Event):
    value: int


@dataclass
class Execute(UseCaseCommand):
    value: int


@dataclass(frozen=True)
class Result(UseCaseHandlerResult):
    value: int


@dataclass
class Compensation(UseCaseCommandCompensation):
    value: int

    def to_payload(self):
        return {"value": self.value}

    @classmethod
    def from_payload(cls, payload):
        return cls(payload["value"])


@dataclass
class HappenedCompensation(EventCompensation):
    value: int

    def to_payload(self):
        return {"value": self.value}

    @classmethod
    def from_payload(cls, payload):
        return cls(payload["value"])


class CommandHandler(UseCaseHandler):
    lifecycle_contexts: ClassVar[list[object | None]] = []

    async def handle(self, command, context):
        self.lifecycle_contexts.append(context.lifecycle_context)
        session = await context.uow.write_session()
        session.log.append("handler")
        context.queue.push(Happened(command.value))
        return SagaUseCaseHandlerResult(
            Result(command.value),
            Compensation(command.value),
        )

    async def compensate(self, compensation, context):
        return None


class HappenedHandler(EventHandler):
    emit_saga_result: ClassVar[bool] = False

    async def handle(self, event, context):
        session = await context.uow.write_session()
        session.log.append("event")
        if self.emit_saga_result:
            return SagaEventHandlerResult(HappenedCompensation(event.value))
        return None


class Session:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")

    async def close(self):
        self.log.append("close")


class RecordingJournal(InMemorySagaJournal):
    def __init__(self, log):
        super().__init__()
        self.log = log
        self.saved_spans = []
        self.loaded_spans = []

    async def save(self, record: SagaRecord, resource: object, span) -> None:
        self.log.append("save_saga")
        self.saved_spans.append(span)
        await super().save(record, resource, span)

    async def load(self, saga_id, resource, span):
        self.loaded_spans.append(span)
        return await super().load(saga_id, resource, span)


class CapturingSpan(Span):
    def __init__(self, name, roots, parent=None):
        self.name = name
        self.roots = roots
        self.parent = parent
        self.children = []
        self.finished = False

    def child(self, *, name, attributes=None):
        child = CapturingSpan(name, self.roots, self)
        self.children.append(child)
        return child

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.finished = True
        return False

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, attributes=None):
        pass


class CapturingSpanFactory(SpanFactory):
    def __init__(self):
        self.roots = []

    def create_span(self, *, trace, name, attributes=None):
        root = CapturingSpan(name, self.roots)
        self.roots.append(root)
        return root


def build(mode, *, tracing=False):
    log = []
    use_cases = UseCaseHandlerRegistry[Lifecycle]()
    use_cases.register(
        Execute,
        CommandHandler,
        saga_key="execute.v1",
        compensation_type=Compensation,
        execution_mode=mode,
    )
    events = EventHandlerRegistry()
    events.register(
        Happened,
        HappenedHandler,
        saga_key="happened.v1",
        compensation_type=HappenedCompensation,
    )
    spans = CapturingSpanFactory() if tracing else None
    journal = RecordingJournal(log)
    slot_creator = SimpleServiceSlotCreator(
        config=SimpleServiceSlotCreatorConfig(
            slot=SimpleServiceSlotConfig(
                resource_holder_factory=lambda: SessionResourceHolder(
                    {"primary": lambda: Session(log)}
                ),
                uow_factory=BaseUnitOfWork,
            ),
            handlers=SimpleServiceHandlerConfig(
                use_case_registry=use_cases,
                event_registry=events,
            ),
            saga_journal=journal,
            span_factory=spans,
        ),
        container=Container(),
    )
    app = SimpleServiceDirettoreApplication(
        slot_provider=PoolExecutionSlotProvider(
            slot_creator=slot_creator,
            initial_slot_count=1,
            max_slot_count=1,
        ),
    )
    return app, log, spans, journal


def run(coro):
    return asyncio.run(coro)


def test_validation_report_includes_use_case_and_event_saga_keys(
    tmp_path: Path,
) -> None:
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, _, _, _ = build(UseCaseHandlerExecutionMode.IN_TRANSACTION)
    report_path = tmp_path / "validation_results.md"

    app.validate(report_path)

    report = report_path.read_text(encoding="utf-8")
    assert "Registered by saga key: execute.v1" in report
    assert "Registered by saga key: happened.v1" in report


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "in_transaction",
            ["handler", "event", "save_saga", "commit", "close"],
        ),
        (
            "after_transaction",
            [
                "handler",
                "save_saga",
                "commit",
                "close",
                "event",
                "commit",
                "close",
            ],
        ),
    ],
)
def test_event_timing_and_saga_persistence_precede_commit(mode, expected):
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, log, _, _ = build(UseCaseHandlerExecutionMode(mode))
    run(app.handle(Execute(1), input=None, saga_id="saga"))
    assert log == expected
    assert CommandHandler.lifecycle_contexts[-1] is None


@pytest.mark.parametrize("mode", ["in_transaction", "after_transaction"])
def test_lease_drains_every_handle_without_committing_each_handle(mode):
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, log, _, _ = build(UseCaseHandlerExecutionMode(mode))

    async def scenario():
        async with app.slot(saga_id="lease-saga") as lease:
            async with lease.transaction():
                await lease.handle(Execute(1), input=None)
                await lease.handle(Execute(2), input=None)

    run(scenario())
    assert log == [
        "handler",
        "event",
        "handler",
        "event",
        "save_saga",
        "commit",
        "close",
    ]


def test_event_saga_result_records_event_compensation() -> None:
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode
    from direttore.core.saga import SagaHandlerKind

    app, _, _, journal = build(UseCaseHandlerExecutionMode.IN_TRANSACTION)
    HappenedHandler.emit_saga_result = True

    async def scenario():
        try:
            await app.handle(Execute(1), input=None, saga_id="event-saga")
            return await journal.load("event-saga", object(), None)
        finally:
            HappenedHandler.emit_saga_result = False

    record = run(scenario())
    assert [entry.kind for entry in record.entries] == [
        SagaHandlerKind.USE_CASE,
        SagaHandlerKind.EVENT,
    ]


def test_saga_journal_receives_active_save_and_load_spans() -> None:
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, _, spans, journal = build(
        UseCaseHandlerExecutionMode.IN_TRANSACTION,
        tracing=True,
    )

    async def scenario():
        await app.handle(Execute(1), saga_id="traced-saga")
        await app.compensate_saga("traced-saga")

    run(scenario())
    assert journal.saved_spans[-1] is spans.roots[0]
    assert journal.loaded_spans[-1] is spans.roots[1]


def test_lease_replaces_cached_span_for_each_normal_operation():
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, _, spans, _ = build(UseCaseHandlerExecutionMode.IN_TRANSACTION, tracing=True)

    async def scenario():
        async with app.slot() as lease:
            await lease.handle(Execute(1), input=None)
            assert len(spans.roots) == 1
            assert spans.roots[0].finished is False
            await lease.handle(Execute(2), input=None)
            assert len(spans.roots) == 2
            assert spans.roots[0].finished is True
            assert spans.roots[1].finished is False
            await lease.commit()

    run(scenario())
    assert all(span.finished for span in spans.roots)


def test_lease_cache_reuses_one_operation_span_until_release():
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, _, spans, _ = build(UseCaseHandlerExecutionMode.IN_TRANSACTION, tracing=True)

    async def scenario():
        async with app.slot() as lease:
            async with lease.transaction():
                await lease.handle(Execute(1), trace="first")
                await lease.handle_cache(Execute(2))
                assert len(spans.roots) == 1
                assert spans.roots[0].finished is False

    run(scenario())
    assert spans.roots[0].finished is True


def test_in_memory_journal_deep_copies_payloads_on_save_and_load():
    journal = InMemorySagaJournal()
    from direttore.core.saga import SagaEntry, SagaHandlerKind

    payload = {"nested": {"value": 1}}
    record = SagaRecord(
        saga_id="copy",
        entries=(SagaEntry(SagaHandlerKind.USE_CASE, "key", payload),),
    )

    async def scenario():
        await journal.save(record, object(), None)
        payload["nested"]["value"] = 2
        first = await journal.load("copy", object(), None)
        first.entries[0].payload["nested"]["value"] = 3
        return await journal.load("copy", object(), None)

    loaded = run(scenario())
    assert loaded.entries[0].payload == {"nested": {"value": 1}}
