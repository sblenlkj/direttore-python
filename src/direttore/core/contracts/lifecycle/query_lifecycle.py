from direttore.core.contracts.handlers.query_handler import QueryHandlerConfig
from direttore.core.primitives.uow import BaseUnitOfWork


class QueryLifecycle[InputT, LifecycleContextT, UowT: BaseUnitOfWork]:
    async def create_context(
        self,
        input: InputT,
        config: QueryHandlerConfig,
        uow: UowT,
    ) -> LifecycleContextT:
        raise NotImplementedError


class DefaultQueryLifecycle(
    QueryLifecycle[object, None, BaseUnitOfWork],
):
    async def create_context(
        self,
        input: object,
        config: QueryHandlerConfig,
        uow: BaseUnitOfWork,
    ) -> None:
        return None
