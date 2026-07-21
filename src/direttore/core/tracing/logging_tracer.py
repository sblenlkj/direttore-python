from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from direttore.core.tracing.tracer import (
    TraceSpan,
    Tracer,
)


@dataclass(slots=True)
class LoggingTraceSpan(TraceSpan):
    logger: logging.Logger
    name: str
    trace: object | None = None
    attributes: Mapping[str, Any] | None = None
    parent_span: TraceSpan | None = None
    level: int = logging.DEBUG

    _started_at: float | None = field(default=None, init=False)

    async def __aenter__(self) -> LoggingTraceSpan:
        self._started_at = perf_counter()

        self.logger.log(
            self.level,
            "Trace span started: %s | parent=%s | trace=%r | attributes=%r",
            self.name,
            self._get_parent_span_name(),
            self.trace,
            dict(self.attributes or {}),
        )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        elapsed_ms = self._get_elapsed_ms()

        if exc_type is None:
            self.logger.log(
                self.level,
                "Trace span finished: %s | parent=%s | elapsed_ms=%.3f",
                self.name,
                self._get_parent_span_name(),
                elapsed_ms,
            )
        else:
            self.logger.exception(
                "Trace span failed: %s | parent=%s | elapsed_ms=%.3f | "
                "error=%r",
                self.name,
                self._get_parent_span_name(),
                elapsed_ms,
                exc_value,
            )

        return False

    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.logger.log(
            self.level,
            "Trace span attribute: %s | parent=%s | %s=%r",
            self.name,
            self._get_parent_span_name(),
            key,
            value,
        )

    def add_event(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self.logger.log(
            self.level,
            "Trace span event: %s | parent=%s | event=%s | attributes=%r",
            self.name,
            self._get_parent_span_name(),
            name,
            dict(attributes or {}),
        )

    def _get_elapsed_ms(self) -> float:
        if self._started_at is None:
            return 0.0

        return (perf_counter() - self._started_at) * 1000

    def _get_parent_span_name(self) -> str | None:
        if self.parent_span is None:
            return None

        return getattr(self.parent_span, "name", None) or (
            f"{type(self.parent_span).__module__}."
            f"{type(self.parent_span).__qualname__}"
        )


@dataclass(frozen=True, slots=True)
class LoggingTracer(Tracer[object]):
    """Default tracer implementation backed by Python logging.

    This tracer does not export real distributed traces.

    It is useful as a development/default implementation because it shows when
    orchestration spans are opened, closed, enriched with attributes, enriched
    with events, and nested under parent spans.
    """

    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(
            "direttore.tracing"
        )
    )
    level: int = logging.DEBUG

    def start_span(
        self,
        *,
        trace: object | None,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_span: TraceSpan | None = None,
    ) -> TraceSpan:
        return LoggingTraceSpan(
            logger=self.logger,
            name=name,
            trace=trace,
            attributes=attributes,
            parent_span=parent_span,
            level=self.level,
        )