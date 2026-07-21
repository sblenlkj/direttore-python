from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, Self


class Message:
    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        return cls(**payload)

    def to_payload(self) -> dict[str, Any]:
        if is_dataclass(self):
            return asdict(self)

        return dict(self.__dict__)


class ExecutionMessage(Message):
    pass


class UseCaseCommand(ExecutionMessage):
    pass


class Query(ExecutionMessage):
    pass


class Event(Message):
    pass