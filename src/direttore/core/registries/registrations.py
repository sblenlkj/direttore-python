from __future__ import annotations

from dataclasses import dataclass, field

from direttore.core.contracts.handlers import (
    EventHandler,
    QueryHandler,
    QueryHandlerConfig,
    UseCaseHandler,
    UseCaseHandlerConfig,
)
from direttore.core.contracts.messages import (
    Event,
    Query,
    UseCaseCommand,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseHandlerRegistration:
    source_name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseKeyedHandlerRegistration(BaseHandlerRegistration):
    key: str | None = None


@dataclass(frozen=True, slots=True)
class UseCaseHandlerRegistration(BaseKeyedHandlerRegistration):
    command_type: type[UseCaseCommand]
    handler_type: type[UseCaseHandler]
    config: UseCaseHandlerConfig = field(
        default_factory=UseCaseHandlerConfig,
    )


@dataclass(frozen=True, slots=True)
class QueryHandlerRegistration(BaseKeyedHandlerRegistration):
    query_type: type[Query]
    handler_type: type[QueryHandler]
    config: QueryHandlerConfig = field(
        default_factory=QueryHandlerConfig,
    )


@dataclass(frozen=True, slots=True)
class EventHandlerRegistration(BaseHandlerRegistration):
    event_type: type[Event]
    handler_type: type[EventHandler]
    is_ready: bool = True