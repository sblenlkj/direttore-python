from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from direttore.core.contracts.messages import Event

class EventQueue:
    """
    Queue for post-command event orchestration.
    """
    def __init__(self) -> None:
        self._queue = deque()

    def push(self, message: object) -> None:
        self._queue.append(message)

    def push_many(self, messages: Iterable[object]) -> None:
        self._queue.extend(messages)

    def pop(self) -> Event:
        if self.is_empty:
            raise ValueError("Queue is empty")
        return self._queue.popleft()

    @property
    def is_empty(self) -> bool:
        return not self._queue

    def clear(self) -> None:
        self._queue.clear()
