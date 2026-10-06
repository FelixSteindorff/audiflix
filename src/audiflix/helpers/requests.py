"""Generation tokens for results that may arrive out of order."""

from __future__ import annotations


class RequestGate:
    """Used on the UI thread, both when starting and delivering a request."""

    def __init__(self) -> None:
        self._generations: dict[str, int] = {}

    def issue(self, key: str) -> tuple[str, int]:
        generation = self._generations.get(key, 0) + 1
        self._generations[key] = generation
        return key, generation

    def current(self, token: tuple[str, int]) -> bool:
        key, generation = token
        return self._generations.get(key) == generation

    def invalidate(self, prefix: str) -> None:
        for key in list(self._generations):
            if key.startswith(prefix):
                self.issue(key)
