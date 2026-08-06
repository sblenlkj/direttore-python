from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from direttore.core.contracts.messages import (
    UseCaseCommand,
    UseCaseCommandCompensation,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.tracing import Span


@dataclass(frozen=True, slots=True)
class UseCaseHandlerResult:
    pass


@dataclass(frozen=True, slots=True)
class SagaUseCaseHandlerResult:
    result: UseCaseHandlerResult
    compensation: UseCaseCommandCompensation


@dataclass(slots=True)
class UseCaseHandlerContext[
    UnitOfWorkT: BaseUnitOfWork,
    LifecycleContextT,
    SpanT: Span,
]:
    uow: UnitOfWorkT
    queue: EventQueue
    lifecycle_context: LifecycleContextT | None
    span: SpanT | None


class UseCaseHandlerExecutionMode(StrEnum):
    IN_TRANSACTION = "in_transaction"
    AFTER_TRANSACTION = "after_transaction"


class UseCaseEventDrainingMode(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


@dataclass(frozen=True, slots=True)
class UseCaseHandlerConfig:
    allowed_access_tags: frozenset[str] | None = None


class UseCaseHandler(ABC):
    @abstractmethod
    async def handle(
        self,
        command: UseCaseCommand,
        context: UseCaseHandlerContext[BaseUnitOfWork, object, Span],
    ) -> UseCaseHandlerResult | SagaUseCaseHandlerResult:
        raise NotImplementedError
