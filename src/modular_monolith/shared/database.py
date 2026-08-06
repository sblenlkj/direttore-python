from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InMemoryDatabase:
    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    audits: list[dict[str, Any]] = field(default_factory=list)
    transaction_log: list[tuple[str, int]] = field(default_factory=list)
    access_log: list[tuple[str, int]] = field(default_factory=list)
    _next_session_id: int = 1

    def create_session(self) -> InMemorySession:
        session = InMemorySession(self, self._next_session_id)
        self._next_session_id += 1
        return session


class InMemorySession:
    def __init__(self, database: InMemoryDatabase, session_id: int) -> None:
        self.database = database
        self.session_id = session_id
        self.products = deepcopy(database.products)
        self.orders = deepcopy(database.orders)
        self.audits = deepcopy(database.audits)

    def record_access(self, operation: str) -> None:
        self.database.access_log.append((operation, self.session_id))

    async def commit(self) -> None:
        self.database.products = deepcopy(self.products)
        self.database.orders = deepcopy(self.orders)
        self.database.audits = deepcopy(self.audits)
        self.database.transaction_log.append(("commit", self.session_id))

    async def rollback(self) -> None:
        self.database.transaction_log.append(("rollback", self.session_id))

    async def close(self) -> None:
        self.database.transaction_log.append(("close", self.session_id))

