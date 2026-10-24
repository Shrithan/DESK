"""Send DESK agent-to-agent messages straight over localhost; everything else
(ASI:One users, other agents) resolves normally through the Almanac."""

from __future__ import annotations

from uagents.resolver import GlobalResolver, Resolver


class LocalFirstResolver(Resolver):
    def __init__(self, local: dict[str, str]) -> None:
        self._local = local
        self._fallback = GlobalResolver()

    async def resolve(self, destination: str) -> tuple[str | None, list[str]]:
        addr = destination.split("://")[-1]
        if addr in self._local:
            return addr, [self._local[addr]]
        return await self._fallback.resolve(destination)
