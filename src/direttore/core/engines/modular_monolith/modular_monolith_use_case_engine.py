from __future__ import annotations

from direttore.application.modular_monolith.config import (
    ModularMonolithAuthConfig,
    ModularMonolithSessionAuthConfig,
)
from direttore.core.contracts.handlers import (
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
from direttore.core.engines.modular_monolith.base_modular_monolith_engine import (
    BaseModularMonolithEngine,
)
from direttore.core.event_dispatchers.modular_monolith_event_dispatcher import (
    ModularMonolithEventDispatcher,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.modules.auth import (
    ContextAuthenticator,
    ModularAuthorizationLocationKind,
    ModularAuthorizer,
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


type ModularMonolithApplicationAuthConfig[AuthInputT, AuthT] = (
    ModularMonolithAuthConfig[AuthInputT, AuthT]
    | ModularMonolithSessionAuthConfig[AuthInputT, AuthT]
    | None
)


class ModularMonolithUseCaseEngine[AuthInputT, AuthT, TraceT](
    BaseModularMonolithEngine[AuthInputT, AuthT, TraceT],
):
    def __init__(
        self,
        *,
        resolver: UseCaseHandlerResolver,
        use_case_uow_routing: UseCaseUowRoutingRegistry,
        event_dispatcher: ModularMonolithEventDispatcher[TraceT] | None = None,
        config: UseCaseEngineConfig | None = None,
    ) -> None:
        super().__init__()
        self.resolver = resolver
        self.use_case_uow_routing = use_case_uow_routing
        self.event_dispatcher = event_dispatcher
        self.config = config or UseCaseEngineConfig()

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        resource_holder: AbstractUseCaseResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        event_queue: EventQueue,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        event_queue.clear()

        runtime.set_trace(trace)
        runtime.clear_auth()
        runtime.clear_parent_span()

        try:
            resolved = self.resolver.resolve(
                type(command),
                overrides=runtime.dependency_overrides,
            )
            handler_config = resolved.registration.config

            if isinstance(
                auth_config,
                ModularMonolithSessionAuthConfig,
            ):
                return await self._handle_with_context_authentication(
                    command=command,
                    resolved=resolved,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    event_queue=event_queue,
                    auth_config=auth_config,
                    auth_input=auth_input,
                    allowed_access_tags=handler_config.allowed_access_tags,
                    execution_mode=handler_config.execution_mode,
                    trace=trace,
                    tracer=tracer,
                )

            auth = await self._authenticate_without_context(
                authenticator=(
                    None
                    if auth_config is None
                    else auth_config.authenticator
                ),
                auth_input=auth_input,
            )

            runtime.set_auth(auth)

            self._authorize_user_request(
                allowed_access_tags=handler_config.allowed_access_tags,
                auth=auth,
                authorizer=(
                    None
                    if auth_config is None
                    else auth_config.authorizer
                ),
            )

            return await self._handle_with_resolved_auth(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                auth=auth,
                execution_mode=handler_config.execution_mode,
                trace=trace,
                tracer=tracer,
            )
        finally:
            runtime.clear_auth()
            runtime.clear_trace()
            runtime.clear_parent_span()
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
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        event_queue: EventQueue,
        auth_config: ModularMonolithSessionAuthConfig[
            AuthInputT,
            AuthT,
        ],
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
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                auth_config=auth_config,
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
                operation="modular.use_case.handle",
                message=command,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("modular.use_case.execution.started")

            result = await self._execute_with_context_authentication(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                auth_config=auth_config,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                execution_mode=execution_mode,
                trace=trace,
                tracer=tracer,
                parent_span=span,
            )

            span.add_event("modular.use_case.execution.finished")

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
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
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
                coordinator=coordinator,
                runtime=runtime,
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
                operation="modular.use_case.handle",
                message=command,
            ),
            attributes=self._build_span_attributes(
                message=command,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("modular.use_case.execution.started")

            result = await self._execute_with_resolved_auth(
                command=command,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                event_queue=event_queue,
                auth=auth,
                execution_mode=execution_mode,
                trace=trace,
                tracer=tracer,
                parent_span=span,
            )

            span.add_event("modular.use_case.execution.finished")

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
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        event_queue: EventQueue,
        auth_config: ModularMonolithSessionAuthConfig[
            AuthInputT,
            AuthT,
        ],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> UseCaseHandlerResult:
        root_uow = self._get_root_uow(
            resolved=resolved,
            coordinator=coordinator,
        )

        auth_uow_type = auth_config.use_case_uow_type
        auth_uow = coordinator.get_use_case_uow(auth_uow_type)

        async with resource_holder:
            auth = await self._authenticate_with_context(
                authenticator=auth_config.authenticator,
                auth_input=auth_input,
                uow=auth_uow,
            )

            runtime.set_auth(auth)
            runtime.set_parent_span(parent_span)

            self._authorize_user_request(
                allowed_access_tags=allowed_access_tags,
                auth=auth,
                authorizer=auth_config.authorizer,
            )

            result = await self._call_handler(
                command=command,
                resolved=resolved,
                uow=root_uow,
                event_queue=event_queue,
                auth=auth,
                trace=trace,
            )

            if execution_mode == UseCaseHandlerExecutionMode.IN_TRANSACTION:
                await self._drain_events(
                    event_queue=event_queue,
                    coordinator=coordinator,
                    runtime=runtime,
                    trace=trace,
                    tracer=tracer,
                    parent_span=parent_span,
                )

                return result

        if execution_mode == UseCaseHandlerExecutionMode.AFTER_TRANSACTION:
            await self._drain_events(
                event_queue=event_queue,
                coordinator=coordinator,
                runtime=runtime,
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
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        event_queue: EventQueue,
        auth: AuthT | None,
        execution_mode: UseCaseHandlerExecutionMode,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> UseCaseHandlerResult:
        root_uow = self._get_root_uow(
            resolved=resolved,
            coordinator=coordinator,
        )

        async with resource_holder:
            runtime.set_auth(auth)
            runtime.set_parent_span(parent_span)

            result = await self._call_handler(
                command=command,
                resolved=resolved,
                uow=root_uow,
                event_queue=event_queue,
                auth=auth,
                trace=trace,
            )

            if execution_mode == UseCaseHandlerExecutionMode.IN_TRANSACTION:
                await self._drain_events(
                    event_queue=event_queue,
                    coordinator=coordinator,
                    runtime=runtime,
                    trace=trace,
                    tracer=tracer,
                    parent_span=parent_span,
                )

                return result

        if execution_mode == UseCaseHandlerExecutionMode.AFTER_TRANSACTION:
            await self._drain_events(
                event_queue=event_queue,
                coordinator=coordinator,
                runtime=runtime,
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
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
        parent_span: TraceSpan | None,
    ) -> None:
        if self.event_dispatcher is None:
            return

        processed_events = 0

        while not event_queue.is_empty:
            if processed_events >= self.config.max_processed_events:
                raise EngineEventLimitExceededError(
                    "Modular use case event processing limit exceeded. "
                    f"Limit={self.config.max_processed_events}."
                )

            event = event_queue.pop()

            await self.event_dispatcher.dispatch(
                event=event,
                coordinator=coordinator,
                overrides=runtime.dependency_overrides,
                trace=trace,
                tracer=tracer,
                parent_span=parent_span,
            )

            processed_events += 1

    def _get_root_uow(
        self,
        *,
        resolved: ResolvedHandler[
            UseCaseHandler,
            UseCaseHandlerRegistration,
        ],
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> BaseUnitOfWork:
        root_uow_type = self.use_case_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type,
        )

        return coordinator.get_use_case_uow(root_uow_type)

    def _authorize_user_request(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
        authorizer: ModularAuthorizer[AuthT] | None,
    ) -> None:
        if authorizer is None:
            return

        authorizer.authorize(
            allowed_access_tags=allowed_access_tags,
            auth=auth,
            location_kind=ModularAuthorizationLocationKind.USER_REQUEST,
        )