from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class TraceResolver[TraceInputT, TraceT](ABC):
    """Application-specific trace resolver contract.

    Trace resolution converts external trace input into an application-specific
    trace object.

    The application layer calls this before passing trace into engines,
    dispatchers, or other orchestration runtime objects.

    Examples of trace input:

    - HTTP headers with distributed tracing context;
    - OpenTelemetry context extracted by an adapter;
    - request id;
    - existing in-memory trace object in tests;
    - None, when execution starts without upstream trace context.

    The framework does not define the shape of trace input or resolved trace.
    """

    @abstractmethod
    def resolve_trace(
        self,
        trace_input: TraceInputT | None,
    ) -> TraceT | None:
        raise NotImplementedError


class TraceSpan(ABC):
    """Tracing span contract.

    A span represents one measured execution block.

    The framework can use spans around engine execution, handler execution,
    event dispatching, resolver work, or other orchestration operations.

    Spans may be nested. A child span should be started with `parent_span`
    pointing to the currently active parent operation span.

    Implementations may send data to OpenTelemetry, LangFuse, Phoenix,
    structured logs, or any other tracing backend.

    Implementations should return `False` from `__aexit__` unless they
    intentionally want to suppress exceptions.
    """

    @abstractmethod
    async def __aenter__(self) -> TraceSpan:
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_event(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError


class Tracer[TraceT](ABC):
    """Application-specific tracer contract.

    The engine receives a resolved request/runtime `trace` object and uses
    `Tracer` to create spans around orchestration operations.

    The framework does not define the shape of `TraceT`.

    `TraceT` may be:

    - a trace id;
    - an OpenTelemetry context;
    - a LangFuse trace/client object;
    - a Phoenix trace object;
    - a custom application trace object;
    - `None` when tracing is disabled.

    `parent_span` may be passed when the new span should be nested under an
    existing operation span. This allows engines to create a root execution span
    and dispatchers/repositories to create child spans inside that execution.

    Implementations should create and return an async context manager span.
    """

    @abstractmethod
    def start_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_span: TraceSpan | None = None,
    ) -> TraceSpan:
        raise NotImplementedError