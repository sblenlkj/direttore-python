from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.uow import BaseUnitOfWork


@dataclass(frozen=True, slots=True)
class UseCaseHandlerResult:
    pass


@dataclass(slots=True)
class UseCaseHandlerContext[UnitOfWorkT: BaseUnitOfWork, AuthT, TraceT]:
    uow: UnitOfWorkT
    queue: EventQueue
    auth: AuthT | None = None
    tracer: TraceT | None = None


class UseCaseHandlerExecutionMode(StrEnum):
    IN_TRANSACTION = "in_transaction"
    AFTER_TRANSACTION = "after_transaction"


@dataclass(frozen=True, slots=True)
class UseCaseHandlerConfig:
    execution_mode: UseCaseHandlerExecutionMode = (
        UseCaseHandlerExecutionMode.IN_TRANSACTION
    )
    allowed_access_tags: frozenset[str] | None = None


class UseCaseHandler(ABC):
    @abstractmethod
    async def __call__(
        self,
        command: UseCaseCommand,
        context: UseCaseHandlerContext[BaseUnitOfWork, Any, Any],
    ) -> UseCaseHandlerResult:
        raise NotImplementedError