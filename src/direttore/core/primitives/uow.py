from direttore.core.primitives.resource_holder import BaseResourceHolder


class BaseUnitOfWork:
    """
    Base access object for execution-scoped resources.

    A Unit of Work is created once for an execution slot and keeps a stable
    reference to that slot's ResourceHolder. The ResourceHolder owns the real
    execution-scoped resources, such as a SQLAlchemy AsyncSession, Redis
    connection, HTTP client, or broker channel.

    The Unit of Work itself does not create, commit, roll back, close, or reset
    resources. Those lifecycle operations belong to the ResourceHolder and are
    controlled by the orchestration engine.

    Subclasses should call ``super().__init__(resources)`` from their
    constructor before creating repositories or other access objects.

    Example with SQLAlchemy:

        class SQLAlchemyUserUnitOfWork(UserUnitOfWork):
            def __init__(
                self,
                resources: SQLAlchemyUseCaseResourceHolder,
            ) -> None:
                super().__init__(resources)

                self.users = SQLAlchemyUserRepository(resources)

    Repositories should keep a reference to the same ResourceHolder, or to a
    narrow protocol implemented by that holder, rather than storing an
    execution-scoped SQLAlchemy session directly:

        class SQLAlchemySessionProvider(Protocol):
            async def get_session(self) -> AsyncSession:
                ...

        class SQLAlchemyUserRepository:
            def __init__(
                self,
                resources: SQLAlchemySessionProvider,
            ) -> None:
                self._resources = resources

            async def add(self, user: User) -> None:
                session = await self._resources.get_session()
                session.add(UserModel.from_entity(user))

    This arrangement is important because Unit of Work and repository objects
    may be reused between executions, while the underlying session must be
    created separately for each execution. The stable ResourceHolder reference
    allows those long-lived objects to resolve the current execution resource
    lazily.

    The ``resources`` property is intentionally read-only. A Unit of Work must
    remain attached to the ResourceHolder it received during slot construction.
    Replacing the holder later could leave the Unit of Work and its repositories
    pointing to different execution scopes.

    Subclasses may add typed repository attributes, typed resource accessors,
    or context-specific helper methods. They should not duplicate transaction
    lifecycle logic that already belongs to the ResourceHolder.
    """

    __slots__ = ("_resources",)

    def __init__(
        self,
        resources: BaseResourceHolder,
    ) -> None:
        """
        Attach the Unit of Work to a stable ResourceHolder.

        Subclasses must pass their ResourceHolder to this constructor using
        ``super().__init__(resources)``.
        """
        self._resources = resources

    @property
    def resources(self) -> BaseResourceHolder:
        """
        Return the ResourceHolder associated with this Unit of Work.

        The returned holder is stable for the lifetime of the Unit of Work.
        Concrete repositories normally receive the same holder during Unit of
        Work construction and use it to resolve execution-scoped resources
        lazily.
        """
        return self._resources