from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from direttore.core.contracts.messages import Query
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.tracing import Span


@dataclass(frozen=True, slots=True)
class QueryHandlerResult:
    pass


@dataclass(slots=True)
class QueryHandlerContext[
    UnitOfWorkT: BaseUnitOfWork,
    LifecycleContextT,
    SpanT: Span,
]:
    uow: UnitOfWorkT
    lifecycle_context: LifecycleContextT | None
    span: SpanT | None


@dataclass(frozen=True, slots=True)
class QueryHandlerConfig:
    allowed_access_tags: frozenset[str] | None = None


class QueryHandler(ABC):
    @abstractmethod
    async def handle(
        self,
        query: Query,
        context: QueryHandlerContext[BaseUnitOfWork, object, Span],
    ) -> QueryHandlerResult:
        raise NotImplementedError
