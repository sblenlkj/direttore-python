from __future__ import annotations

from dataclasses import dataclass

from direttore.core.contracts.handlers import (
    EventHandler,
    QueryHandler,
    QueryHandlerConfig,
    UseCaseEventDrainingMode,
    UseCaseHandler,
    UseCaseHandlerConfig,
    UseCaseHandlerExecutionMode,
)
from direttore.core.contracts.lifecycle import QueryLifecycle, UseCaseLifecycle
from direttore.core.contracts.messages import Event, Query, UseCaseCommand


@dataclass(frozen=True, slots=True)
class UseCaseHandlerRegistration:
    command_type: type[UseCaseCommand]
    handler_type: type[UseCaseHandler]
    lifecycle: UseCaseLifecycle
    config: UseCaseHandlerConfig
    key: str | None = None
    saga_key: str | None = None
    compensation_type: type[object] | None = None
    source_name: str | None = None
    execution_mode: UseCaseHandlerExecutionMode = (
        UseCaseHandlerExecutionMode.IN_TRANSACTION
    )
    event_draining_mode: UseCaseEventDrainingMode = UseCaseEventDrainingMode.SEQUENTIAL


@dataclass(frozen=True, slots=True)
class QueryHandlerRegistration:
    query_type: type[Query]
    handler_type: type[QueryHandler]
    lifecycle: QueryLifecycle
    config: QueryHandlerConfig
    key: str | None = None
    source_name: str | None = None


@dataclass(frozen=True, slots=True)
class EventHandlerRegistration:
    event_type: type[Event]
    handler_type: type[EventHandler]
    saga_key: str | None = None
    compensation_type: type[object] | None = None
    source_name: str | None = None
    is_ready: bool = True
