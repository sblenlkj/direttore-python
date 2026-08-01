import asyncio
from dataclasses import dataclass

import pytest

from direttore.application.simple_service import (
    SimpleServiceDirettoreApplication,
    SimpleServiceDirettoreConfig,
    SimpleServiceHandlerConfig,
    SimpleServiceSlotConfig,
)
from direttore.core.contracts.handlers import EventHandler, UseCaseHandler
from direttore.core.contracts.messages import Event, UseCaseCommand
from direttore.core.primitives import BaseUnitOfWork, Container, ResourceHolder
from direttore.core.registries import EventHandlerRegistry, UseCaseHandlerRegistry
from direttore.core.saga import (
    InMemorySagaJournal,
    SagaHandlerResult,
    SagaRecord,
)
from direttore.core.tracing import Span, SpanFactory


@dataclass
class Happened(Event):
    value: int


@dataclass
class Execute(UseCaseCommand):
    value: int


@dataclass
class Compensation:
    value: int

    def to_payload(self):
        return {"value": self.value}

    @classmethod
    def from_payload(cls, payload):
        return cls(payload["value"])


class CommandHandler(UseCaseHandler):
    async def handle(self, command, context):
        session = await context.uow.write_session()
        session.log.append("handler")
        context.queue.push(Happened(command.value))
        return SagaHandlerResult(command.value, Compensation(command.value))

    async def compensate(self, compensation, context):
        return None


class HappenedHandler(EventHandler):
    async def handle(self, event, context):
        session = await context.uow.write_session()
        session.log.append("event")


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

    async def save(self, record: SagaRecord, resource: object) -> None:
        self.log.append("save_saga")
        await super().save(record, resource)


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
    use_cases = UseCaseHandlerRegistry()
    use_cases.register(
        Execute,
        CommandHandler,
        saga_key="execute.v1",
        compensation_type=Compensation,
        execution_mode=mode,
    )
    events = EventHandlerRegistry()
    events.register(Happened, HappenedHandler)
    spans = CapturingSpanFactory() if tracing else None
    journal = RecordingJournal(log)
    app = SimpleServiceDirettoreApplication(
        config=SimpleServiceDirettoreConfig(
            slot=SimpleServiceSlotConfig(
                resource_holder_factory=lambda: ResourceHolder(
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
        initial_slot_count=1,
        max_slot_count=1,
    )
    return app, log, spans, journal


def run(coro):
    return asyncio.run(coro)


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


def test_lease_trace_is_one_root_with_one_child_per_operation_and_closes_last():
    from direttore.core.contracts.handlers import UseCaseHandlerExecutionMode

    app, _, spans, _ = build(UseCaseHandlerExecutionMode.IN_TRANSACTION, tracing=True)

    async def scenario():
        async with app.slot() as lease:
            await lease.handle(Execute(1), input=None)
            await lease.handle(Execute(2), input=None)
            assert spans.roots[0].finished is False
            await lease.commit()

    run(scenario())
    assert len(spans.roots) == 1
    assert len(spans.roots[0].children) == 2
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
        await journal.save(record, object())
        payload["nested"]["value"] = 2
        first = await journal.load("copy", object())
        first.entries[0].payload["nested"]["value"] = 3
        return await journal.load("copy", object())

    loaded = run(scenario())
    assert loaded.entries[0].payload == {"nested": {"value": 1}}
