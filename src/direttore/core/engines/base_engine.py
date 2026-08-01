from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import (
    UseCaseHandlerExecutionMode,
)
from direttore.core.contracts.messages import (
    Message,
    Query,
    UseCaseCommand,
)
from direttore.core.engines.engine_exceptions import (
    UnsupportedUseCaseExecutionModeError,
)


class BaseEngine:
    def _build_span_name(
        self,
        *,
        operation: str,
        message: Message,
    ) -> str:
        return (
            f"{operation} "
            f"{type(message).__module__}.{type(message).__qualname__}"
        )

    def _build_span_attributes(
        self,
        *,
        message: Message,
        handler_type: type[Any],
        source_name: str | None,
        key: str | None,
    ) -> dict[str, Any]:
        return {
            "message.type": (
                f"{type(message).__module__}.{type(message).__qualname__}"
            ),
            "handler.type": (
                f"{handler_type.__module__}.{handler_type.__qualname__}"
            ),
            "handler.source_name": source_name,
            "handler.key": key,
        }


class BaseUseCaseEngine(BaseEngine):
    def _validate_execution_mode(
        self,
        execution_mode: UseCaseHandlerExecutionMode,
    ) -> None:
        if execution_mode in (
            UseCaseHandlerExecutionMode.IN_TRANSACTION,
            UseCaseHandlerExecutionMode.AFTER_TRANSACTION,
        ):
            return

        raise UnsupportedUseCaseExecutionModeError(
            "Unsupported use case execution mode: "
            f"{execution_mode!r}."
        )

    def _build_command_from_payload(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        command_type: type[UseCaseCommand],
    ) -> UseCaseCommand:
        try:
            command = command_type.from_payload(
                payload,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to create use case command from payload. "
                f"Key={key!r}, "
                f"command_type="
                f"{command_type.__module__}."
                f"{command_type.__qualname__}, "
                f"payload={dict(payload)!r}."
            ) from exc

        if not isinstance(
            command,
            command_type,
        ):
            raise TypeError(
                "UseCaseCommand.from_payload(...) returned wrong "
                "command type. "
                f"Key={key!r}, "
                f"expected="
                f"{command_type.__module__}."
                f"{command_type.__qualname__}, "
                f"actual={type(command).__module__}."
                f"{type(command).__qualname__}."
            )

        return command


class BaseQueryEngine(BaseEngine):
    def _build_query_from_payload(
        self,
        *,
        key: str,
        payload: Mapping[str, Any],
        query_type: type[Query],
    ) -> Query:
        try:
            query = query_type.from_payload(
                payload,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to create query from payload. "
                f"Key={key!r}, "
                f"query_type="
                f"{query_type.__module__}."
                f"{query_type.__qualname__}, "
                f"payload={dict(payload)!r}."
            ) from exc

        if not isinstance(
            query,
            query_type,
        ):
            raise TypeError(
                "Query.from_payload(...) returned wrong query type. "
                f"Key={key!r}, "
                f"expected="
                f"{query_type.__module__}."
                f"{query_type.__qualname__}, "
                f"actual={type(query).__module__}."
                f"{type(query).__qualname__}."
            )

        return query
