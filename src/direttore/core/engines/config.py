from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaseEngineConfig:
    pass


@dataclass(frozen=True, slots=True)
class QueryEngineConfig(BaseEngineConfig):
    pass


@dataclass(frozen=True, slots=True)
class UseCaseEngineConfig(BaseEngineConfig):
    max_processed_events: int = 100