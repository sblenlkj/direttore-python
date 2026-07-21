from __future__ import annotations

from direttore.application.modular_monolith.config import (
    ModularMonolithAuthConfig,
    ModularMonolithSessionAuthConfig,
)
from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerContext,
    QueryHandlerResult,
)
from direttore.core.contracts.messages import Query
from direttore.core.engines.modular_monolith.base_modular_monolith_engine import (
    BaseModularMonolithEngine,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.modules.auth import (
    ContextAuthenticator,
    ModularAuthorizationLocationKind,
    ModularAuthorizer,
)
from direttore.core.tracing import TraceSpan, Tracer
from direttore.core.primitives.resource_holder import (
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
)
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)


type ModularMonolithApplicationAuthConfig[AuthInputT, AuthT] = (
    ModularMonolithAuthConfig[AuthInputT, AuthT]
    | ModularMonolithSessionAuthConfig[AuthInputT, AuthT]
    | None
)


class ModularMonolithQueryEngine[AuthInputT, AuthT, TraceT](
    BaseModularMonolithEngine[AuthInputT, AuthT, TraceT],
):
    def __init__(
        self,
        *,
        resolver: QueryHandlerResolver,
        query_uow_routing: QueryUowRoutingRegistry,
    ) -> None:
        super().__init__()
        self.resolver = resolver
        self.query_uow_routing = query_uow_routing

    async def handle(
        self,
        *,
        query: Query,
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        runtime.set_trace(trace)
        runtime.clear_auth()
        runtime.clear_parent_span()

        try:
            resolved = self.resolver.resolve(
                type(query),
                overrides=runtime.dependency_overrides,
            )
            handler_config = resolved.registration.config

            if isinstance(
                auth_config,
                ModularMonolithSessionAuthConfig,
            ):
                return await self._handle_with_context_authentication(
                    query=query,
                    resolved=resolved,
                    resource_holder=resource_holder,
                    coordinator=coordinator,
                    runtime=runtime,
                    auth_config=auth_config,
                    auth_input=auth_input,
                    allowed_access_tags=handler_config.allowed_access_tags,
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
                query=query,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                auth=auth,
                trace=trace,
                tracer=tracer,
            )
        finally:
            runtime.clear_auth()
            runtime.clear_trace()
            runtime.clear_parent_span()

    async def _handle_with_context_authentication(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        auth_config: ModularMonolithSessionAuthConfig[
            AuthInputT,
            AuthT,
        ],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> QueryHandlerResult:
        if tracer is None:
            return await self._execute_with_context_authentication(
                query=query,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                auth_config=auth_config,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                trace=trace,
                parent_span=None,
            )

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="modular.query.handle",
                message=query,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("modular.query.execution.started")

            result = await self._execute_with_context_authentication(
                query=query,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                auth_config=auth_config,
                auth_input=auth_input,
                allowed_access_tags=allowed_access_tags,
                trace=trace,
                parent_span=span,
            )

            span.add_event("modular.query.execution.finished")

        return result

    async def _handle_with_resolved_auth(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        auth: AuthT | None,
        trace: TraceT | None,
        tracer: Tracer[TraceT] | None,
    ) -> QueryHandlerResult:
        if tracer is None:
            return await self._execute_with_resolved_auth(
                query=query,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                auth=auth,
                trace=trace,
                parent_span=None,
            )

        async with tracer.start_span(
            trace=trace,
            name=self._build_span_name(
                operation="modular.query.handle",
                message=query,
            ),
            attributes=self._build_span_attributes(
                message=query,
                handler_type=resolved.handler_type,
                source_name=resolved.registration.source_name,
                key=resolved.registration.key,
            ),
        ) as span:
            span.add_event("modular.query.execution.started")

            result = await self._execute_with_resolved_auth(
                query=query,
                resolved=resolved,
                resource_holder=resource_holder,
                coordinator=coordinator,
                runtime=runtime,
                auth=auth,
                trace=trace,
                parent_span=span,
            )

            span.add_event("modular.query.execution.finished")

        return result

    async def _execute_with_context_authentication(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        auth_config: ModularMonolithSessionAuthConfig[
            AuthInputT,
            AuthT,
        ],
        auth_input: AuthInputT | None,
        allowed_access_tags: frozenset[str] | None,
        trace: TraceT | None,
        parent_span: TraceSpan | None,
    ) -> QueryHandlerResult:
        root_uow = self._get_root_uow(
            resolved=resolved,
            coordinator=coordinator,
        )

        auth_uow_type = auth_config.query_uow_type
        if auth_uow_type is None:
            raise RuntimeError(
                "Context authentication for query execution requires "
                "query_uow_type."
            )

        auth_uow = coordinator.get_query_uow(auth_uow_type)

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
                query=query,
                resolved=resolved,
                uow=root_uow,
                auth=auth,
                trace=trace,
            )

        return result

    async def _execute_with_resolved_auth(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        resource_holder: QueryResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        auth: AuthT | None,
        trace: TraceT | None,
        parent_span: TraceSpan | None,
    ) -> QueryHandlerResult:
        root_uow = self._get_root_uow(
            resolved=resolved,
            coordinator=coordinator,
        )

        async with resource_holder:
            runtime.set_auth(auth)
            runtime.set_parent_span(parent_span)

            result = await self._call_handler(
                query=query,
                resolved=resolved,
                uow=root_uow,
                auth=auth,
                trace=trace,
            )

        return result

    async def _call_handler(
        self,
        *,
        query: Query,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        uow: BaseUnitOfWork,
        auth: AuthT | None,
        trace: TraceT | None,
    ) -> QueryHandlerResult:
        context = QueryHandlerContext(
            uow=uow,
            auth=auth,
            tracer=trace,
        )

        return await resolved.handler(
            query,
            context,
        )

    def _get_root_uow(
        self,
        *,
        resolved: ResolvedHandler[
            QueryHandler,
            QueryHandlerRegistration,
        ],
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> BaseUnitOfWork:
        root_uow_type = self.query_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type,
        )

        return coordinator.get_query_uow(root_uow_type)

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