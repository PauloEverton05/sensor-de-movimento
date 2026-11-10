"""Conexão SQLite e migrações versionadas.

- Modo WAL, foreign_keys=ON, um único escritor (o agente).
- Cada migração roda numa transação única: ou aplica inteira, ou nada.
- A versão fica em PRAGMA user_version e o histórico em schema_migrations.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: controlamos as transações explicitamente (BEGIN/COMMIT).
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def load_migrations() -> list[Migration]:
    pkg = resources.files("sentinel.persistence.migrations")
    found: list[Migration] = []
    for entry in pkg.iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append(
                Migration(
                    version=int(match["version"]),
                    name=match["name"],
                    sql=entry.read_text(encoding="utf-8"),
                )
            )
    found.sort(key=lambda m: m.version)
    expected = list(range(1, len(found) + 1))
    if [m.version for m in found] != expected:
        raise MigrationError(f"migrações fora de sequência: {[m.version for m in found]}")
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection, migrations: list[Migration] | None = None) -> int:
    """Aplica as migrações pendentes e devolve a versão final do esquema."""
    migrations = load_migrations() if migrations is None else migrations
    current = schema_version(conn)
    latest = migrations[-1].version if migrations else 0
    if current > latest:
        raise MigrationError(
            f"banco na versão {current}, mais nova que esta aplicação ({latest}); "
            "atualize o Sentinel AI antes de abrir este banco"
        )
    for m in migrations:
        if m.version <= current:
            continue
        log.info("aplicando migração", extra={"version": m.version, "migration": m.name})
        _apply(conn, m)
    return schema_version(conn)


def _apply(conn: sqlite3.Connection, m: Migration) -> None:
    # foreign_keys não pode mudar dentro de transação. Desligado, recriar uma tabela
    # (DROP + RENAME) não dispara ON DELETE CASCADE nas tabelas dependentes; a
    # integridade é conferida com foreign_key_check antes do COMMIT.
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        # executescript faria COMMIT implícito de uma transação aberta fora dele;
        # por isso o BEGIN vai dentro do próprio script.
        conn.executescript(f"BEGIN IMMEDIATE;\n{m.sql}\n;")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise MigrationError(
                f"migração {m.version}_{m.name} violaria integridade referencial: "
                f"{[tuple(v) for v in violations[:5]]}"
            )
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at_ms) VALUES (?, ?, ?)",
            (m.version, m.name, int(time.time() * 1000)),
        )
        conn.execute(f"PRAGMA user_version = {int(m.version)}")
        conn.execute("COMMIT")
    except (sqlite3.Error, MigrationError) as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"falha na migração {m.version}_{m.name}: {exc}") from exc
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
