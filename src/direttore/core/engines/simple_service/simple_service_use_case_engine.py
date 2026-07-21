from __future__ import annotations

from typing import Any

from direttore.core.contracts.handlers import (
    EventHandlerContext,
    UseCaseHandler,
    UseCaseHandlerContext,
    UseCaseHandlerExecutionMode,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.engines.config import UseCaseEngineConfig
from direttore.core.engines.engine_exceptions import (
    EngineEventLimitExceededError,
    UnsupportedUseCaseExecutionModeError,
)
from direttore.core.engines.simple_service.base_simple_service_engine import (
    BaseSimpleServiceEngine,
)
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.modules.auth import (
    Authenticator,
    Authorizer,
    ContextAuthenticator,
)
from direttore.core.tracing import TraceSpan, Tracer
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    UseCaseHandlerRegistration,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)


class SimpleServiceUseCaseEngine[AuthInputT, AuthT, TraceT](
    BaseSimpleServiceEngine[AuthInputT, AuthT],
):
    def __init__(
        self,
        *,
        resolver: UseCaseHandlerResolver,
        event_dispatcher: SimpleServiceEventDispatcher[TraceT] | None = None,
        authorizer: Authorizer[AuthT] | None = None,
        config: UseCaseEngineConfig | None = None,
    ) -> None:
        super().__init__(
            authorizer=authorizer,
        )
        self.resolver = resolver
        self.event_dispatcher = event_dispatcher
        self.config = config or UseCaseEngineConfig()

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ) = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        resolved = self.resolver.resolve(type(command))
        handler_config = resolved.registration.config

        event_queue.clear()

        try:
            if isinstance(authenticator, ContextAuthenticator):
                return await self._handle_with_context_authentication(
                    command=command,
                    resolved=resolved,
                    resource_holder=resource_holder,
                    uow=uow,
                    event_queue=event_queue,
                    authenticator=authenticator,
                    auth_input=auth_input,
                    allowed_access_tags=handler_config.allowed_access_tags,
                    execution_mode=handler_config.execution_mode,
                    trace=trace,
                    tracer=tracer,
                )

            auth = await self._authenticate_without_context(
                authenticator=authenticator,
                auth_input=auth_input,
            )

            self._authorize(
                allowed_access_tags=handler_config.allowed_access_tags,
                auth=auth,
            )

            return await self._handle_with_resolved_auth(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                auth=auth,
                execution_mode=handler_config.execution_mode,
                trace=trace,
                tracer=tracer,
            )
        finally:
            event_queue.clear()

    async def _handle_with_context_authentication(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        authenticator: ContextAuthenticator[AuthInputT, AuthT, Any],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> UseCaseHandlerResult:
        if tracer is None:
            return await self._execute_with_context_authentication(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                authenticator=authenticator,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                execution_mode=execution_mode,
                trace=trace,
                tracer=None,
                parent_span=None,
            )

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="use_case.handle",
                message=command,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("use_case.execution.started")

            result = await self._execute_with_context_authentication(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                authenticator=authenticator,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                execution_mode=execution_mode,
                trace=trace,
                tracer=tracer,
                parent_span=span,
            )

            span.add_event("use_case.execution.finished")

        return result

    async def _handle_with_resolved_auth(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        auth: AuthT | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> UseCaseHandlerResult:
        if tracer is None:
            return await self._execute_with_resolved_auth(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                auth=auth,
                execution_mode=execution_mode,
                trace=trace,
                tracer=None,
                parent_span=None,
            )

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="use_case.handle",
                message=command,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("use_case.execution.started")

            result = await self._execute_with_resolved_auth(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                uow=uow,
                event_queue=event_queue,
                auth=auth,
                execution_mode=execution_mode,
                trace=trace,
                tracer=tracer,
                parent_span=span,
            )

            span.add_event("use_case.execution.finished")

        return result

    async def _execute_with_context_authentication(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        authenticator: ContextAuthenticator[AuthInputT, AuthT, Any],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> UseCaseHandlerResult:
        async with resource_holder:
            auth = await self._authenticate_with_context(
                authenticator=authenticator,
                auth_input=auth_input,
                uow=uow,
            )

            self._authorize(
                allowed_access_tags=allowed_access_tags,
                auth=auth,
            )

            result = await self._call_handler(
                command=command,
                resolved=resolved,
                uow=uow,
                event_queue=event_queue,
                auth=auth,
                trace=trace,
            )

            if execution_mode == UseCaseHandlerExecutionMode.IN_TRANSACTION:
                await self._drain_events(
                    event_queue=event_queue,
                    uow=uow,
                    trace=trace,
                    tracer=tracer,
                    parent_span=parent_span,
                )

                return result

        if execution_mode == UseCaseHandlerExecutionMode.AFTER_TRANSACTION:
            await self._drain_events(
                event_queue=event_queue,
                uow=uow,
                trace=trace,
                tracer=tracer,
                parent_span=parent_span,
            )

            return result

        raise UnsupportedUseCaseExecutionModeError(
            f"Unsupported use case execution mode: {execution_mode!r}."
        )

    async def _execute_with_resolved_auth(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        resource_holder: AbstractUseCaseResourceHolder,
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        auth: AuthT | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> UseCaseHandlerResult:
        async with resource_holder:
            result = await self._call_handler(
                command=command,
                resolved=resolved,
                uow=uow,
                event_queue=event_queue,
                auth=auth,
                trace=trace,
            )

            if execution_mode == UseCaseHandlerExecutionMode.IN_TRANSACTION:
                await self._drain_events(
                    event_queue=event_queue,
                    uow=uow,
                    trace=trace,
                    tracer=tracer,
                    parent_span=parent_span,
                )

                return result

        if execution_mode == UseCaseHandlerExecutionMode.AFTER_TRANSACTION:
            await self._drain_events(
                event_queue=event_queue,
                uow=uow,
                trace=trace,
                tracer=tracer,
                parent_span=parent_span,
            )

            return result

        raise UnsupportedUseCaseExecutionModeError(
            f"Unsupported use case execution mode: {execution_mode!r}."
        )

    async def _call_handler(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        uow: BaseUnitOfWork,
        event_queue: EventQueue,
        auth: AuthT | None,
        trace: TraceT | None,
    ) -> UseCaseHandlerResult:
        context = UseCaseHandlerContext(
            uow=uow,
            queue=event_queue,
            auth=auth,
            tracer=trace,
        )

        return await resolved.handler(
            command,
            context,
        )

    async def _drain_events(
        self,
        *,
        event_queue: EventQueue,
        uow: BaseUnitOfWork,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> None:
        if self.event_dispatcher is None:
            return

        processed_events = 0

        context = EventHandlerContext(
            uow=uow,
        )

        while not event_queue.is_empty:
            if processed_events >= self.config.max_processed_events:
                raise EngineEventLimitExceededError(
                    "Use case event processing limit exceeded. "
                    f"Limit={self.config.max_processed_events}."
                )

            event = event_queue.pop()

            await self.event_dispatcher.dispatch(
                event=event,
                context=context,
                trace=trace,
                tracer=tracer,
                parent_span=parent_span,
            )

            processed_events += 1