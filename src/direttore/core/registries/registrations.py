from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from direttore.core.contracts.handlers import (
    EventHandler,
    UseCaseEventDrainingMode,
    UseCaseHandler,
    UseCaseHandlerConfig,
    UseCaseHandlerExecutionMode,
)
from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.messages import (
    Event,
    EventCompensation,
    UseCaseCommand,
    UseCaseCommandCompensation,
)


@dataclass(frozen=True, slots=True)
class UseCaseHandlerRegistration[LifecycleT: Lifecycle[Any, Any]]:
    command_type: type[UseCaseCommand]
    handler_type: type[UseCaseHandler]
    lifecycle: LifecycleT | None
    config: UseCaseHandlerConfig
    key: str | None = None
    saga_key: str | None = None
    compensation_type: type[UseCaseCommandCompensation] | None = None
    source_name: str | None = None
    execution_mode: UseCaseHandlerExecutionMode = (
        UseCaseHandlerExecutionMode.IN_TRANSACTION
    )
    event_draining_mode: UseCaseEventDrainingMode = UseCaseEventDrainingMode.SEQUENTIAL


@dataclass(frozen=True, slots=True)
class EventHandlerRegistration:
    event_type: type[Event]
    handler_type: type[EventHandler]
    saga_key: str | None = None
    compensation_type: type[EventCompensation] | None = None
    source_name: str | None = None
    is_ready: bool = True
