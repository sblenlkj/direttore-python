from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from direttore.core.contracts.messages import Event
from direttore.core.primitives.uow import BaseUnitOfWork


@dataclass(slots=True)
class EventHandlerContext[UnitOfWorkT: BaseUnitOfWork]:
    uow: UnitOfWorkT


class EventHandler(ABC):
    @abstractmethod
    async def __call__(
        self,
        event: Event,
        context: EventHandlerContext[BaseUnitOfWork],
    ) -> None:
        raise NotImplementedError