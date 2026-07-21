from __future__ import annotations

from typing import Any

from direttore.core.contracts.messages import Event


class BaseEventDispatcher:
    def _build_span_name(
        self,
        *,
        event: Event,
        handler_type: type[Any],
    ) -> str:
        return (
            "event.dispatch "
            f"{type(event).__module__}.{type(event).__qualname__} "
            "-> "
            f"{handler_type.__module__}.{handler_type.__qualname__}"
        )

    def _build_span_attributes(
        self,
        *,
        event: Event,
        handler_type: type[Any],
        source_name: str | None,
    ) -> dict[str, Any]:
        return {
            "event.type": (
                f"{type(event).__module__}.{type(event).__qualname__}"
            ),
            "event.handler_type": (
                f"{handler_type.__module__}.{handler_type.__qualname__}"
            ),
            "event.source_name": source_name,
        }