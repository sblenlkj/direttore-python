from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import TracebackType
from typing import Any


type SpanAttributes = Mapping[str, Any]


class Span(ABC):
    """Active node in a trace tree.

    A span represents one traced operation. It contains the backend-specific
    state required to create child spans without receiving the original trace,
    span factory, or an explicit parent span.

    Child spans form the tracing tree:

        root span
        └── child span
            └── child span

    Entering the span starts the operation. Exiting it finishes the operation
    and records any exception raised inside the context.
    """

    @abstractmethod
    def child(
        self,
        *,
        name: str,
        attributes: SpanAttributes | None = None,
    ) -> Span:
        """Create a direct child of this span."""
        raise NotImplementedError

    @abstractmethod
    async def __aenter__(self) -> Span:
        """Start the span and return its active representation."""
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Finish the span and allow exceptions to propagate."""
        raise NotImplementedError

    @abstractmethod
    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        """Set or replace an attribute on this span."""
        raise NotImplementedError

    @abstractmethod
    def add_event(
        self,
        name: str,
        attributes: SpanAttributes | None = None,
    ) -> None:
        """Add a timestamped event to this span."""
        raise NotImplementedError


class SpanFactory[TraceT](ABC):
    """Creates root spans.

    A span factory is configured on an engine or another execution boundary.
    It converts an application-specific trace value into a root span.

    The framework intentionally does not define the structure of ``TraceT``.
    It may be a dictionary, trace identifier, OpenTelemetry context, custom
    application object, or any other backend-specific trace representation.

    After the root span has been created, the trace and span factory should not
    be propagated further. Child operations create spans through ``Span.child``.
    """

    @abstractmethod
    def create_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: SpanAttributes | None = None,
    ) -> Span:
        """Create a root span for a new or continued trace."""
        raise NotImplementedError