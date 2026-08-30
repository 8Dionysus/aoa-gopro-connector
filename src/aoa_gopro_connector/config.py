"""Portable storage-root resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_ENV = {
    "data": "AOA_GOPRO_DATA_ROOT",
    "cache": "AOA_GOPRO_CACHE_ROOT",
    "auth": "AOA_GOPRO_AUTH_ROOT",
    "artifacts": "AOA_GOPRO_ARTIFACT_ROOT",
    "media": "AOA_GOPRO_MEDIA_ROOT",
}


@dataclass(frozen=True, slots=True)
class StorageRoots:
    data: Path
    cache: Path
    auth: Path
    artifacts: Path
    media: Path
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "data": str(self.data),
            "cache": str(self.cache),
            "auth": str(self.auth),
            "artifacts": str(self.artifacts),
            "media": str(self.media),
            "source": self.source,
        }


def _source_checkout_state_root() -> Path:
    candidate = Path(__file__).resolve().parents[2] / ".connector-state"
    if candidate.is_dir():
        return candidate
    cwd_candidate = Path.cwd() / ".connector-state"
    return cwd_candidate


def resolve_storage_roots() -> StorageRoots:
    explicit = {
        name: os.environ.get(env_name) for name, env_name in ROOT_ENV.items()
    }
    if any(explicit.values()):
        instance = os.environ.get("AOA_GOPRO_INSTANCE_ROOT")
        fallback = Path(instance).expanduser() if instance else _source_checkout_state_root()
        values = {
            name: Path(value).expanduser() if value else fallback / name
            for name, value in explicit.items()
        }
        return StorageRoots(**values, source="explicit-roots")

    instance = os.environ.get("AOA_GOPRO_INSTANCE_ROOT")
    root = Path(instance).expanduser() if instance else _source_checkout_state_root()
    source = "instance-root" if instance else "repo-local-fixture-default"
    return StorageRoots(
        data=root / "data",
        cache=root / "cache",
        auth=root / "auth",
        artifacts=root / "artifacts",
        media=root / "media",
        source=source,
    )
