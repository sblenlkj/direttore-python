from direttore.core.contracts.handlers.use_case_handler import UseCaseHandlerConfig
from direttore.core.primitives.uow import BaseUnitOfWork

class UseCaseLifecycle[InputT, LifecycleContextT, UowT: BaseUnitOfWork]:
    async def create_context(
        self,
        input: InputT,
        config: UseCaseHandlerConfig,
        uow: UowT,
    ) -> LifecycleContextT:
        raise NotImplementedError


class DefaultUseCaseLifecycle(
    UseCaseLifecycle[object, None, BaseUnitOfWork],
):
    async def create_context(
        self,
        input: object,
        config: UseCaseHandlerConfig,
        uow: BaseUnitOfWork,
    ) -> None:
        return None
