import asyncio
from dataclasses import dataclass, field

import pytest

from direttore.core.primitives import ResourceFinalizedError, ResourceHolder
from tests.helpers import SessionResourceHolder


@dataclass
class Session:
    name: str
    calls: list[str] = field(default_factory=list)

    async def commit(self) -> None:
        self.calls.append("commit")

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def close(self) -> None:
        self.calls.append("close")


def run(coro):
    return asyncio.run(coro)


def test_resource_holder_requires_programmer_finalization_policy() -> None:
    with pytest.raises(TypeError):
        ResourceHolder()


def test_named_resources_are_lazy_cached_and_commit_intent_is_monotonic() -> None:
    created: list[Session] = []

    def factory() -> Session:
        session = Session("primary")
        created.append(session)
        return session

    holder = SessionResourceHolder({"primary": factory})

    async def scenario() -> None:
        assert created == []
        first = await holder.get_session("primary", commit=False)
        second = await holder.get_session("primary", commit=True)
        third = await holder.get_session("primary", commit=False)
        assert first is second is third
        assert holder.commit_required == {"primary": True}
        await holder.rollback()
        with pytest.raises(ResourceFinalizedError):
            await holder.get_session("primary")
        await holder.close()
        holder.reset()

    run(scenario())


def test_programmer_policy_commits_writes_and_rolls_back_reads() -> None:
    primary = Session("primary")
    analytics = Session("analytics")
    holder = SessionResourceHolder(
        {"primary": lambda: primary, "analytics": lambda: analytics}
    )

    async def scenario() -> None:
        await holder.get_session("analytics", commit=False)
        await holder.get_session("primary", commit=True)
        await holder.commit()
        await holder.close()

    run(scenario())
    assert primary.calls == ["commit", "close"]
    assert analytics.calls == ["rollback", "close"]


def test_programmer_policy_rolls_back_and_closes_resources() -> None:
    one = Session("one")
    two = Session("two")
    holder = SessionResourceHolder({"one": lambda: one, "two": lambda: two})

    async def scenario() -> None:
        await holder.get_session("one", commit=True)
        await holder.get_session("two", commit=False)
        await holder.rollback()
        await holder.close()

    run(scenario())
    assert one.calls == ["rollback", "close"]
    assert two.calls == ["rollback", "close"]


def test_holder_is_reusable_after_close_and_reset() -> None:
    created: list[Session] = []

    def factory() -> Session:
        result = Session(str(len(created)))
        created.append(result)
        return result

    holder = SessionResourceHolder({"primary": factory})

    async def scenario() -> None:
        for index in range(2):
            holder.saga_id = f"saga-{index}"
            await holder.get_session("primary", commit=False)
            await holder.commit()
            assert holder.saga_id == f"saga-{index}"
            await holder.close()
            assert holder.saga_id == f"saga-{index}"
            holder.reset()
            assert holder.saga_id is None

    run(scenario())
    assert len(created) == 2
    assert all(session.calls == ["rollback", "close"] for session in created)
