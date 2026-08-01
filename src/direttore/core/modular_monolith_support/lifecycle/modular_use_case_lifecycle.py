from direttore.core.contracts.handlers.use_case_handler import UseCaseHandlerConfig
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)


class ModularUseCaseLifecycle[InputT, LifecycleContextT]:
    async def create_context(
        self,
        input: InputT,
        config: UseCaseHandlerConfig,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> LifecycleContextT:
        raise NotImplementedError


class DefaultModularUseCaseLifecycle(
    ModularUseCaseLifecycle[object, None],
):
    async def create_context(
        self,
        input: object,
        config: UseCaseHandlerConfig,
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> None:
        return None
