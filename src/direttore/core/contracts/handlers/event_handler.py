from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from direttore.core.contracts.messages import Event, EventCompensation
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.tracing import Span


@dataclass(slots=True)
class EventHandlerContext[UnitOfWorkT: BaseUnitOfWork, SpanT: Span]:
    uow: UnitOfWorkT
    span: SpanT | None


@dataclass(frozen=True, slots=True)
class SagaEventHandlerResult:
    compensation: EventCompensation


class EventHandler(ABC):
    @abstractmethod
    async def handle(
        self,
        event: Event,
        context: EventHandlerContext[BaseUnitOfWork, Span],
    ) -> SagaEventHandlerResult | None:
        raise NotImplementedError
