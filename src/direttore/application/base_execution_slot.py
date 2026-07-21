from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.messages import (
    Query,
    UseCaseCommand,
)


class BaseExecutionSlot(ABC):
    @abstractmethod
    def reset(self) -> None:
        """Reset slot execution state before returning it to the slot pool.

        Slot-owned long-lived objects should not be destroyed here.

        Typical reset work:

            - clear event queue;
            - clear runtime auth/trace/span state;
            - clear other per-execution metadata.

        Resource cleanup itself belongs to ResourceHolder lifecycle.
        """

        raise NotImplementedError

    def _build_command_from_payload(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        command_type: type[UseCaseCommand],
    ) -> UseCaseCommand:
        try:
            command = command_type.from_payload(payload)
        except Exception as exc:
            raise RuntimeError(
                "Failed to create use case command from payload. "
                f"Key={key!r}, "
                f"command_type="
                f"{command_type.__module__}.{command_type.__qualname__}, "
                f"payload={dict(payload)!r}."
            ) from exc

        if not isinstance(command, command_type):
            raise TypeError(
                "UseCaseCommand.from_payload(...) returned wrong command type. "
                f"Key={key!r}, "
                f"expected="
                f"{command_type.__module__}.{command_type.__qualname__}, "
                f"actual={type(command).__module__}."
                f"{type(command).__qualname__}."
            )

        return command

    def _build_query_from_payload(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        query_type: type[Query],
    ) -> Query:
        try:
            query = query_type.from_payload(payload)
        except Exception as exc:
            raise RuntimeError(
                "Failed to create query from payload. "
                f"Key={key!r}, "
                f"query_type={query_type.__module__}."
                f"{query_type.__qualname__}, "
                f"payload={dict(payload)!r}."
            ) from exc

        if not isinstance(query, query_type):
            raise TypeError(
                "Query.from_payload(...) returned wrong query type. "
                f"Key={key!r}, "
                f"expected={query_type.__module__}.{query_type.__qualname__}, "
                f"actual={type(query).__module__}."
                f"{type(query).__qualname__}."
            )

        return query