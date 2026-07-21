from __future__ import annotations

from typing import Any

from direttore.core.contracts.messages import Message


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