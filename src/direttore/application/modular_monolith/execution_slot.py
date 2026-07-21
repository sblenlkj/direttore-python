from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.base_execution_slot import (
    BaseExecutionSlot,
)
from direttore.application.modular_monolith.config import (
    ModularMonolithAuthConfig,
    ModularMonolithSessionAuthConfig,
    ModularMonolithSlotConfig,
)
from direttore.core.contracts.handlers import (
    QueryHandlerResult,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import (
    Query,
    UseCaseCommand,
)
from direttore.core.engines.modular_monolith.modular_monolith_query_engine import (
    ModularMonolithQueryEngine,
)
from direttore.core.engines.modular_monolith.modular_monolith_use_case_engine import (
    ModularMonolithUseCaseEngine,
)
from direttore.core.modular_monolith_support.execution_dependencies import (
    ModularMonolithExecutionDependencyContext,
    ModularMonolithExecutionDependencyRegistry,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modules.auth import (
    ModularAuthorizer,
)
from direttore.core.tracing import Tracer
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)


type ModularMonolithApplicationAuthConfig[AuthInputT, AuthT] = (
    ModularMonolithAuthConfig[AuthInputT, AuthT]
    | ModularMonolithSessionAuthConfig[AuthInputT, AuthT]
    | None
)


class ModularMonolithExecutionSlot[
    AuthInputT,
    AuthT,
    TraceT,
](BaseExecutionSlot):
    def __init__(
        self,
        *,
        slot_config: ModularMonolithSlotConfig,
        use_case_engine: ModularMonolithUseCaseEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ],
        query_engine: ModularMonolithQueryEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ]
        | None = None,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        tracer: Tracer[TraceT] | None = None,
        dependency_registry: (
            ModularMonolithExecutionDependencyRegistry | None
        ) = None,
    ) -> None:
        self.use_case_engine = use_case_engine
        self.query_engine = query_engine
        self.auth_config = auth_config

        self.use_case_resource_holder: AbstractUseCaseResourceHolder = (
            slot_config.use_case_resource_holder_factory()
        )

        self.query_resource_holder: QueryResourceHolder | None = None

        if slot_config.query_resource_holder_factory is not None:
            self.query_resource_holder = (
                slot_config.query_resource_holder_factory()
            )

        self.coordinator = slot_config.coordinator_factory(
            self.use_case_resource_holder,
            self.query_resource_holder,
        )

        self.event_queue: EventQueue = EventQueue()

        self.runtime = ModularMonolithExecutionRuntime[AuthT, TraceT](
            coordinator=self.coordinator,
            event_queue=self.event_queue,
            use_case_resolver=self.use_case_engine.resolver,
            use_case_uow_routing=self.use_case_engine.use_case_uow_routing,
            query_resolver=(
                None if self.query_engine is None else self.query_engine.resolver
            ),
            query_uow_routing=(
                None
                if self.query_engine is None
                else self.query_engine.query_uow_routing
            ),
            authorizer=self._get_authorizer(),
            tracer=tracer,
        )

        if dependency_registry is not None:
            overrides = dependency_registry.build_overrides(
                context=ModularMonolithExecutionDependencyContext(
                    runtime=self.runtime,
                ),
            )
            self.runtime.set_dependency_overrides(
                dict(overrides),
            )

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        return await self.use_case_engine.handle(
            command=command,
            resource_holder=self.use_case_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            event_queue=self.event_queue,
            auth_config=auth_config,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> UseCaseHandlerResult:
        resolved = self.use_case_engine.resolver.resolve_by_key(
            key,
            overrides=self.runtime.dependency_overrides,
        )

        command = self._build_command_from_payload(
            key=key,
            payload=payload,
            command_type=resolved.registration.command_type,
        )

        return await self.handle(
            command=command,
            auth_config=auth_config,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_query(
        self,
        *,
        query: Query,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        if self.query_resource_holder is None:
            raise RuntimeError(
                "Modular monolith query resource holder is not configured."
            )

        return await self.query_engine.handle(
            query=query,
            resource_holder=self.query_resource_holder,
            coordinator=self.coordinator,
            runtime=self.runtime,
            auth_config=auth_config,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_config: ModularMonolithApplicationAuthConfig[
            AuthInputT,
            AuthT,
        ] = None,
        auth_input: AuthInputT | None = None,
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        resolved = self.query_engine.resolver.resolve_by_key(
            key,
            overrides=self.runtime.dependency_overrides,
        )

        query = self._build_query_from_payload(
            key=key,
            payload=payload,
            query_type=resolved.registration.query_type,
        )

        return await self.handle_query(
            query=query,
            auth_config=auth_config,
            auth_input=auth_input,
            trace=trace,
            tracer=tracer,
        )

    def reset(self) -> None:
        self.event_queue.clear()
        self.runtime.clear_auth()
        self.runtime.clear_trace()
        self.runtime.clear_parent_span()
        self.coordinator.reset()

    def _get_authorizer(
        self,
    ) -> ModularAuthorizer[AuthT] | None:
        if self.auth_config is None:
            return None

        return self.auth_config.authorizer