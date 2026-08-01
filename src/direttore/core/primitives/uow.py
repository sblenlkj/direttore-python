from direttore.core.primitives.resource_holder import ResourceHolder


class BaseUnitOfWork:
    """Typed access facade over the slot's single resource holder.

    The UoW owns no resource cache and no transaction state. Repositories may
    retain the UoW or holder, but must resolve live sessions lazily.
    """

    __slots__ = ("_resources",)

    def __init__(self, resources: ResourceHolder) -> None:
        self._resources = resources

    @property
    def resources(self) -> ResourceHolder:
        return self._resources

    async def read_session(self, name: str = "primary") -> object:
        return await self._resources.get_session(name, commit=False)

    async def write_session(self, name: str = "primary") -> object:
        return await self._resources.get_session(name, commit=True)
