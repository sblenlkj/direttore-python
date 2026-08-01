import asyncio
from dataclasses import dataclass, field

import pytest

from direttore.core.primitives import (
    MultiResourceCommitError,
    ResourceHolder,
)


@dataclass
class Session:
    name: str
    fail_commit: bool = False
    calls: list[str] = field(default_factory=list)

    async def commit(self) -> None:
        self.calls.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def close(self) -> None:
        self.calls.append("close")


def run(coro):
    return asyncio.run(coro)


def test_named_resources_are_lazy_cached_and_commit_intent_is_monotonic() -> None:
    created: list[Session] = []

    def factory() -> Session:
        session = Session("primary")
        created.append(session)
        return session

    holder = ResourceHolder({"primary": factory})

    async def scenario() -> None:
        await holder.open()
        assert created == []
        first = await holder.get_session("primary", commit=False)
        second = await holder.get_session("primary", commit=True)
        third = await holder.get_session("primary", commit=False)
        assert first is second is third
        assert holder.commit_required == {"primary": True}
        await holder.rollback()
        await holder.close()

    run(scenario())


def test_success_commits_writes_and_rolls_back_reads_then_closes_all() -> None:
    primary = Session("primary")
    analytics = Session("analytics")
    holder = ResourceHolder(
        {"primary": lambda: primary, "analytics": lambda: analytics}
    )

    async def scenario() -> None:
        await holder.open()
        await holder.get_session("analytics", commit=False)
        await holder.get_session("primary", commit=True)
        await holder.commit()
        await holder.close()

    run(scenario())
    assert primary.calls == ["commit", "close"]
    assert analytics.calls == ["rollback", "close"]


def test_failure_rolls_back_every_opened_session_and_zero_session_is_noop() -> None:
    one = Session("one")
    two = Session("two")
    holder = ResourceHolder({"one": lambda: one, "two": lambda: two})

    async def scenario() -> None:
        await holder.open()
        await holder.get_session("one", commit=True)
        await holder.get_session("two", commit=False)
        await holder.rollback()
        await holder.close()
        await holder.open()
        await holder.commit()
        await holder.close()

    run(scenario())
    assert one.calls == ["rollback", "close"]
    assert two.calls == ["rollback", "close"]


def test_partial_commit_error_reports_deterministic_progress() -> None:
    orders = Session("orders")
    billing = Session("billing", fail_commit=True)
    analytics = Session("analytics")
    holder = ResourceHolder(
        {
            "orders": lambda: orders,
            "billing": lambda: billing,
            "analytics": lambda: analytics,
        }
    )

    async def scenario() -> MultiResourceCommitError:
        await holder.open()
        for name in ("orders", "billing", "analytics"):
            await holder.get_session(name, commit=True)
        with pytest.raises(MultiResourceCommitError) as captured:
            await holder.commit()
        await holder.close()
        return captured.value

    error = run(scenario())
    assert error.committed == ("orders",)
    assert error.failed == "billing"
    assert error.not_committed == ("analytics",)
    assert orders.calls == ["commit", "close"]
    assert billing.calls == ["commit", "rollback", "close"]
    assert analytics.calls == ["rollback", "close"]


def test_holder_is_reusable_after_close() -> None:
    created: list[Session] = []

    def factory() -> Session:
        result = Session(str(len(created)))
        created.append(result)
        return result

    holder = ResourceHolder({"primary": factory})

    async def scenario() -> None:
        for _ in range(2):
            await holder.open()
            await holder.get_session("primary", commit=False)
            await holder.commit()
            await holder.close()

    run(scenario())
    assert len(created) == 2
    assert all(session.calls == ["rollback", "close"] for session in created)
