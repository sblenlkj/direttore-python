from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from types import TracebackType
from typing import Any
from uuid import uuid4

from direttore.core.tracing.tracer import (
    Span,
    SpanAttributes,
    SpanFactory,
)


@dataclass(slots=True)
class LoggingSpan(Span):
    logger: logging.Logger
    name: str
    trace_id: str
    span_id: str
    attributes: dict[str, Any]
    parent_span_id: str | None = None
    parent_span_name: str | None = None
    depth: int = 0
    level: int = logging.DEBUG

    _started_at: float | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _finished: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    def child(
        self,
        *,
        name: str,
        attributes: SpanAttributes | None = None,
    ) -> Span:
        return LoggingSpan(
            logger=self.logger,
            name=name,
            trace_id=self.trace_id,
            span_id=uuid4().hex,
            attributes=dict(attributes or {}),
            parent_span_id=self.span_id,
            parent_span_name=self.name,
            depth=self.depth + 1,
            level=self.level,
        )

    async def __aenter__(self) -> LoggingSpan:
        if self._started_at is not None:
            raise RuntimeError(
                f"Span {self.name!r} has already been started."
            )

        self._started_at = perf_counter()

        self.logger.log(
            self.level,
            (
                "Trace span started: %s | "
                "trace_id=%s | "
                "span_id=%s | "
                "parent_span_id=%s | "
                "parent_span_name=%s | "
                "depth=%d | "
                "attributes=%r"
            ),
            self.name,
            self.trace_id,
            self.span_id,
            self.parent_span_id,
            self.parent_span_name,
            self.depth,
            self.attributes,
        )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._started_at is None:
            raise RuntimeError(
                f"Span {self.name!r} has not been started."
            )

        if self._finished:
            raise RuntimeError(
                f"Span {self.name!r} has already been finished."
            )

        self._finished = True
        elapsed_ms = self._get_elapsed_ms()

        if exc_type is None:
            self.logger.log(
                self.level,
                (
                    "Trace span finished: %s | "
                    "trace_id=%s | "
                    "span_id=%s | "
                    "parent_span_id=%s | "
                    "depth=%d | "
                    "elapsed_ms=%.3f"
                ),
                self.name,
                self.trace_id,
                self.span_id,
                self.parent_span_id,
                self.depth,
                elapsed_ms,
            )
        else:
            self.logger.error(
                (
                    "Trace span failed: %s | "
                    "trace_id=%s | "
                    "span_id=%s | "
                    "parent_span_id=%s | "
                    "depth=%d | "
                    "elapsed_ms=%.3f | "
                    "error=%r"
                ),
                self.name,
                self.trace_id,
                self.span_id,
                self.parent_span_id,
                self.depth,
                elapsed_ms,
                exc_value,
            )

        return False

    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.attributes[key] = value

        self.logger.log(
            self.level,
            (
                "Trace span attribute: %s | "
                "trace_id=%s | "
                "span_id=%s | "
                "%s=%r"
            ),
            self.name,
            self.trace_id,
            self.span_id,
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
            (
                "Trace span event: %s | "
                "trace_id=%s | "
                "span_id=%s | "
                "event=%s | "
                "attributes=%r"
            ),
            self.name,
            self.trace_id,
            self.span_id,
            name,
            dict(attributes or {}),
        )

    def _get_elapsed_ms(self) -> float:
        if self._started_at is None:
            return 0.0

        return (perf_counter() - self._started_at) * 1000


@dataclass(frozen=True, slots=True)
class LoggingSpanFactory(SpanFactory[object]):
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(
            "direttore.tracing"
        )
    )
    level: int = logging.DEBUG

    def create_span(
        self,
        *,
        trace: object | None,
        name: str,
        attributes: SpanAttributes | None = None,
    ) -> Span:
        return LoggingSpan(
            logger=self.logger,
            name=name,
            trace_id=self._resolve_trace_id(trace),
            span_id=uuid4().hex,
            attributes=dict(attributes or {}),
            level=self.level,
        )

    @staticmethod
    def _resolve_trace_id(
        trace: object | None,
    ) -> str:
        if isinstance(trace, Mapping):
            trace_id = trace.get("trace_id")

            if trace_id is not None:
                return str(trace_id)

        trace_id = getattr(
            trace,
            "trace_id",
            None,
        )

        if trace_id is not None:
            return str(trace_id)

        return uuid4().hex