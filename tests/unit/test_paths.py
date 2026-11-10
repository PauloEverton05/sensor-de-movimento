import sys
from pathlib import Path

import pytest

from sentinel.common.paths import AppPaths


def test_distinct_data_dirs_get_distinct_ipc_addresses(tmp_path: Path) -> None:
    a = AppPaths.resolve(tmp_path / "a")
    b = AppPaths.resolve(tmp_path / "b")
    assert a.ipc_address != b.ipc_address
    assert a.runtime_dir != b.runtime_dir


def test_same_data_dir_is_stable(tmp_path: Path) -> None:
    assert AppPaths.resolve(tmp_path).ipc_address == AppPaths.resolve(tmp_path).ipc_address


def test_ensure_creates_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINEL_RUNTIME_DIR", str(tmp_path / "rt"))
    p = AppPaths.resolve(tmp_path / "data")
    p.ensure()
    for d in (p.database_dir, p.logs_dir, p.configuration_dir, p.backups_dir, p.runtime_dir):
        assert d.is_dir()
    if sys.platform != "win32":
        assert (p.runtime_dir.stat().st_mode & 0o777) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="limite de caminho de AF_UNIX")
def test_unix_socket_path_fits_sun_path_limit(tmp_path: Path) -> None:
    # macOS limita sun_path a 104 bytes; Linux a 108.
    p = AppPaths.resolve(tmp_path)
    if "SENTINEL_RUNTIME_DIR" not in __import__("os").environ:
        assert len(p.ipc_address.encode()) < 104
