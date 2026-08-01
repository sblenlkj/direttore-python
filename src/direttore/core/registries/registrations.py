from __future__ import annotations

from dataclasses import dataclass, field

from direttore.core.contracts.handlers import (
    EventHandler,
    QueryHandler,
    QueryHandlerConfig,
    UseCaseHandler,
    UseCaseHandlerConfig,
    UseCaseHandlerExecutionMode,
    UseCaseEventDrainingMode,
)
from direttore.core.contracts.messages import (
    Event,
    Query,
    UseCaseCommand,
)
from direttore.core.contracts.lifecycle import UseCaseLifecycle, QueryLifecycle


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseHandlerRegistration:
    source_name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseKeyedHandlerRegistration(BaseHandlerRegistration):
    key: str | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class BaseSagaKeyedHandlerRegistration(BaseHandlerRegistration):
    saga_key: str | None = None

@dataclass(frozen=True, slots=True)
class UseCaseHandlerRegistration(BaseKeyedHandlerRegistration, BaseSagaKeyedHandlerRegistration):
    command_type: type[UseCaseCommand]
    handler_type: type[UseCaseHandler]
    lifecycle: UseCaseLifecycle
    config: UseCaseHandlerConfig
    execution_mode: UseCaseHandlerExecutionMode = (
        UseCaseHandlerExecutionMode.IN_TRANSACTION
    )
    event_draining_mode: UseCaseEventDrainingMode = (
        UseCaseEventDrainingMode.SEQUENTIAL
    )


@dataclass(frozen=True, slots=True)
class QueryHandlerRegistration(BaseKeyedHandlerRegistration):
    query_type: type[Query]
    handler_type: type[QueryHandler]
    lifecycle: QueryLifecycle
    config: QueryHandlerConfig


@dataclass(frozen=True, slots=True)
class EventHandlerRegistration(BaseSagaKeyedHandlerRegistration):
    event_type: type[Event]
    handler_type: type[EventHandler]
    is_ready: bool = True
