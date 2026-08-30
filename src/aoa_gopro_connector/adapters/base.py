"""Read-only adapter protocol."""

from __future__ import annotations

from typing import Any, Protocol


ALLOWED_READ_PATHS = (
    "/gopro/camera/info",
    "/gopro/camera/state",
    "/gopro/media/list",
)


class ReadAdapter(Protocol):
    def get_json(self, path: str) -> dict[str, Any]: ...
