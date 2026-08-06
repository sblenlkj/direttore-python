from __future__ import annotations

from inspect import isawaitable

from direttore.core.primitives import ResourceHolder


class SessionResourceHolder(ResourceHolder):
    """Test application policy for session-like named resources."""

    async def commit(self) -> None:
        self._ensure_not_finalized()
        for name, resource in self._resources.items():
            method_name = "commit" if self._commit_required[name] else "rollback"
            await self._call(resource, method_name)
        self._mark_finalized()

    async def rollback(self) -> None:
        if self.is_finalized:
            return
        for resource in self._resources.values():
            await self._call(resource, "rollback")
        self._mark_finalized()

    async def close(self) -> None:
        first_error: BaseException | None = None
        for resource in reversed(tuple(self._resources.values())):
            try:
                await self._call(resource, "close")
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    @staticmethod
    async def _call(resource: object, method_name: str) -> None:
        method = getattr(resource, method_name, None)
        if method is None:
            return
        result = method()
        if isawaitable(result):
            await result
