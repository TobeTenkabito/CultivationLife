"""Model-independent signature of the regional synchronization callback."""
from collections.abc import Collection
from typing import Protocol, TypeVar


StateT = TypeVar('StateT', contravariant=True)


class RegionSynchronizationPort(Protocol[StateT]):
    def __call__(
        self, game: StateT, targets: Collection[str], *, end: int | None = None,
        news: list[str] | None = None, _origin: bool = False,
    ) -> None: ...
