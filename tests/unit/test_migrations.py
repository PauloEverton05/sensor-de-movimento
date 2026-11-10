import sqlite3
from pathlib import Path

import pytest

from sentinel.persistence import db


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_migrations_are_sequential() -> None:
    migrations = db.load_migrations()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))


def test_migrate_from_empty_and_idempotent(conn: sqlite3.Connection) -> None:
    latest = db.load_migrations()[-1].version
    assert db.migrate(conn) == latest
    assert db.migrate(conn) == latest
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    assert [r[0] for r in rows] == list(range(1, latest + 1))


def test_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_expected_tables_exist(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "cameras",
        "camera_settings",
        "settings",
        "retention_policies",
        "people",
        "consents",
        "person_references",
        "events",
        "event_segments",
        "detections",
        "recordings",
        "segments",
        "surveillance_sessions",
        "session_cameras",
        "operation_log",
        "match_reviews",
        "agent_state",
    } <= tables


def test_failed_migration_rolls_back(conn: sqlite3.Connection) -> None:
    good = db.load_migrations()
    bad = [
        *good,
        db.Migration(
            version=len(good) + 1, name="bad", sql="CREATE TABLE x(a); INSERT INTO nope VALUES (1);"
        ),
    ]
    with pytest.raises(db.MigrationError):
        db.migrate(conn, bad)
    assert db.schema_version(conn) == len(good)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "x" not in names


def test_refuses_newer_database(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    conn.execute("PRAGMA user_version = 999")
    with pytest.raises(db.MigrationError, match="mais nova"):
        db.migrate(conn)


def _camera(conn: sqlite3.Connection, cid: str = "cam1") -> None:
    conn.execute(
        "INSERT INTO cameras(id, name, kind, created_at_ms, updated_at_ms) "
        "VALUES (?, 'Webcam', 'local', 0, 0)",
        (cid,),
    )


def test_foreign_keys_enforced(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO events(id, camera_id, type, started_at_ms) VALUES ('e1', 'missing', 'MOTION', 0)"
        )


def test_only_one_open_session(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    sql = (
        "INSERT INTO surveillance_sessions(id, started_at_ms, desired_state, observed_state) "
        "VALUES (?, 0, 'ACTIVE', 'ACTIVE')"
    )
    conn.execute(sql, ("s1",))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("s2",))
    conn.execute("UPDATE surveillance_sessions SET ended_at_ms = 1 WHERE id = 's1'")
    conn.execute(sql, ("s2",))


def test_deleting_person_keeps_event_anonymous(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    _camera(conn)
    conn.execute("INSERT INTO people(id, name_enc, created_at_ms) VALUES ('p1', x'00', 0)")
    conn.execute(
        "INSERT INTO person_references(id, person_id, image_rel, created_at_ms) "
        "VALUES ('r1', 'p1', 'people/p1/r1.jpg.enc', 0)"
    )
    conn.execute(
        "INSERT INTO events(id, camera_id, type, started_at_ms, person_id) "
        "VALUES ('e1', 'cam1', 'PERSON', 0, 'p1')"
    )
    conn.execute("DELETE FROM people WHERE id = 'p1'")
    assert conn.execute("SELECT person_id FROM events WHERE id='e1'").fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM person_references").fetchone()[0] == 0


def test_invalid_enum_rejected(conn: sqlite3.Connection) -> None:
    db.migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cameras(id, name, kind, created_at_ms, updated_at_ms) "
            "VALUES ('c', 'n', 'webcam', 0, 0)"
        )
