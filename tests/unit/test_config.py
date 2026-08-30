from __future__ import annotations

from pathlib import Path

from aoa_gopro_connector.config import ROOT_ENV, resolve_storage_roots


def test_instance_root_expands_all_storage_classes(monkeypatch, tmp_path: Path) -> None:
    for env_name in ROOT_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("AOA_GOPRO_INSTANCE_ROOT", str(tmp_path))
    roots = resolve_storage_roots()
    assert roots.source == "instance-root"
    assert roots.data == tmp_path / "data"
    assert roots.media == tmp_path / "media"


def test_explicit_root_overrides_one_class(monkeypatch, tmp_path: Path) -> None:
    for env_name in ROOT_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("AOA_GOPRO_INSTANCE_ROOT", str(tmp_path / "instance"))
    monkeypatch.setenv("AOA_GOPRO_MEDIA_ROOT", str(tmp_path / "operator-media"))
    roots = resolve_storage_roots()
    assert roots.source == "explicit-roots"
    assert roots.media == tmp_path / "operator-media"
    assert roots.data == tmp_path / "instance" / "data"
