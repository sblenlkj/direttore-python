from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import perf_counter
from types import TracebackType
from typing import Any

from direttore.core.tracing.tracer import Span, SpanFactory


@dataclass(slots=True)
class SpanNode:
    name: str
    children: list[SpanNode] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None

        return (self.finished_at - self.started_at) * 1000

    @property
    def status(self) -> str:
        if self.finished_at is None:
            return "RUNNING"

        if self.error is not None:
            return "FAILED"

        return "OK"


class RecordingSpan(Span):
    def __init__(
        self,
        *,
        node: SpanNode,
        on_root_exit: Callable[[], None] | None = None,
    ) -> None:
        self._node = node
        self._on_root_exit = on_root_exit
        self._entered = False
        self._finished = False

    def child(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Span:
        self._ensure_active()

        child_node = SpanNode(
            name=name,
        )
        self._node.children.append(child_node)

        return RecordingSpan(
            node=child_node,
        )

    async def __aenter__(self) -> RecordingSpan:
        if self._entered:
            raise RuntimeError(
                f"Span {self._node.name!r} has already been entered."
            )

        self._entered = True
        self._node.started_at = perf_counter()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if not self._entered:
            raise RuntimeError(
                f"Span {self._node.name!r} was not entered."
            )

        if self._finished:
            raise RuntimeError(
                f"Span {self._node.name!r} has already been finished."
            )

        if exc_type is not None:
            self._node.error = exc_type.__qualname__

        self._node.finished_at = perf_counter()
        self._finished = True

        if self._on_root_exit is not None:
            self._on_root_exit()

        return False

    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        self._ensure_active()

    def add_event(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        self._ensure_active()

    def _ensure_active(self) -> None:
        if not self._entered:
            raise RuntimeError(
                f"Span {self._node.name!r} has not been entered."
            )

        if self._finished:
            raise RuntimeError(
                f"Span {self._node.name!r} has already been finished."
            )


@dataclass(frozen=True, slots=True)
class RecordingSpanFactory[TraceT](SpanFactory[TraceT]):
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger(
            "direttore.tracing"
        )
    )
    level: int = logging.DEBUG
    log_on_exit: bool = True

    def create_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Span:
        root = SpanNode(
            name=name,
        )

        def log_trace() -> None:
            if not self.log_on_exit:
                return

            self.logger.log(
                self.level,
                "%s",
                render_trace(root),
            )

        return RecordingSpan(
            node=root,
            on_root_exit=log_trace,
        )


def render_trace(
    root: SpanNode,
) -> str:
    lines = [
        (
            f"Trace [{root.status}] "
            f"{_format_duration(root.duration_ms)}"
        )
    ]

    _render_node(
        node=root,
        lines=lines,
        prefix="",
        connector="└──",
    )

    return "\n".join(lines)


def _render_node(
    *,
    node: SpanNode,
    lines: list[str],
    prefix: str,
    connector: str,
) -> None:
    line = (
        f"{prefix}{connector} "
        f"{node.name} [{node.status}] "
        f"{_format_duration(node.duration_ms)}"
    )

    if node.error is not None:
        line = f"{line} error={node.error}"

    lines.append(line)

    child_prefix = (
        f"{prefix}{'    ' if connector == '└──' else '│   '}"
    )
    last_index = len(node.children) - 1

    for index, child in enumerate(node.children):
        _render_node(
            node=child,
            lines=lines,
            prefix=child_prefix,
            connector="└──" if index == last_index else "├──",
        )


def _format_duration(
    duration_ms: float | None,
) -> str:
    if duration_ms is None:
        return "-"

    return f"{duration_ms:.3f} ms"
