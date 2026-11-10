import sqlite3
import threading
from pathlib import Path

import pytest

from sentinel.domain.camera import CameraConfig, CameraKind
from sentinel.persistence import db
from sentinel.persistence.cameras import CameraRepository


@pytest.fixture
def repo(tmp_path: Path) -> CameraRepository:
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn)
    return CameraRepository(conn, threading.Lock())


def test_roundtrip_each_kind(repo: CameraRepository) -> None:
    cams = [
        CameraConfig(id="a", name="Webcam", kind=CameraKind.LOCAL, device_index=1, fps=15),
        CameraConfig(id="b", name="IP", kind=CameraKind.RTSP, url="rtsp://h/s", secret_ref="ref"),
        CameraConfig(id="c", name="Arq", kind=CameraKind.FILE, path="/tmp/v.avi"),
    ]
    for c in cams:
        repo.add(c)
    assert repo.list() == cams
    assert repo.get("b") == cams[1]


def test_add_creates_settings_and_log(repo: CameraRepository) -> None:
    repo.add(CameraConfig(id="a", name="W", kind=CameraKind.LOCAL, device_index=0))
    conn = repo._conn
    assert (
        conn.execute("SELECT COUNT(*) FROM camera_settings WHERE camera_id='a'").fetchone()[0] == 1
    )
    assert conn.execute("SELECT action FROM operation_log").fetchone()[0] == "camera.add"


def test_remove(repo: CameraRepository) -> None:
    repo.add(CameraConfig(id="a", name="W", kind=CameraKind.LOCAL, device_index=0))
    assert repo.remove("a") is True
    assert repo.remove("a") is False
    assert repo.list() == []


def test_migration_0002_preserves_cameras_and_settings(tmp_path: Path) -> None:
    """Recriar a tabela cameras não pode apagar camera_settings em cascata."""
    conn = db.connect(tmp_path / "m.db")
    migrations = db.load_migrations()
    db.migrate(conn, migrations[:1])
    conn.execute(
        "INSERT INTO cameras(id, name, kind, device_ref, created_at_ms, updated_at_ms) "
        "VALUES ('a', 'W', 'local', 'index:0', 0, 0)"
    )
    conn.execute("INSERT INTO camera_settings(camera_id, motion_sensitivity) VALUES ('a', 7)")
    db.migrate(conn)
    assert conn.execute("SELECT motion_sensitivity FROM camera_settings").fetchone()[0] == 7
    assert conn.execute("SELECT name FROM cameras").fetchone()[0] == "W"
    conn.execute(
        "INSERT INTO cameras(id, name, kind, created_at_ms, updated_at_ms) "
        "VALUES ('f', 'F', 'file', 0, 0)"
    )
    # FKs voltaram a valer depois da migração
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO camera_settings(camera_id) VALUES ('nope')")
