from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from direttore.core.contracts.messages import Event
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.tracing import Span


@dataclass(slots=True)
class EventHandlerContext[UnitOfWorkT: BaseUnitOfWork, SpanT: Span]:
    uow: UnitOfWorkT
    span: SpanT | None


class EventHandler(ABC):
    @abstractmethod
    async def handle(
        self,
        event: Event,
        context: EventHandlerContext[BaseUnitOfWork, Span],
    ) -> None:
        raise NotImplementedError
