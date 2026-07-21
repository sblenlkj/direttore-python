from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from direttore.core.contracts.messages import Query
from direttore.core.primitives.uow import BaseUnitOfWork


@dataclass(frozen=True, slots=True)
class QueryHandlerResult:
    pass


@dataclass(slots=True)
class QueryHandlerContext[UnitOfWorkT: BaseUnitOfWork, AuthT, TraceT]:
    uow: UnitOfWorkT
    auth: AuthT | None = None
    tracer: TraceT | None = None


@dataclass(frozen=True, slots=True)
class QueryHandlerConfig:
    allowed_access_tags: frozenset[str] | None = None


class QueryHandler(ABC):
    @abstractmethod
    async def __call__(
        self,
        query: Query,
        context: QueryHandlerContext[BaseUnitOfWork, Any, Any],
    ) -> QueryHandlerResult:
        raise NotImplementedError