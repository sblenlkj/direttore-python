from direttore.core.contracts.handlers.query_handler import QueryHandlerConfig
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)


class ModularQueryLifecycle[InputT, LifecycleContextT]:
    async def create_context(
        self,
        input: InputT,
        config: QueryHandlerConfig,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> LifecycleContextT:
        raise NotImplementedError


class DefaultModularQueryLifecycle(ModularQueryLifecycle[object, None]):
    async def create_context(
        self,
        input: object,
        config: QueryHandlerConfig,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> None:
        return None
