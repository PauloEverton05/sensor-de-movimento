"""Repositório de câmeras."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid

from sentinel.domain.camera import CameraConfig, CameraKind


def _now_ms() -> int:
    return int(time.time() * 1000)


def _device_ref(cfg: CameraConfig) -> str | None:
    if cfg.kind is CameraKind.LOCAL:
        return f"index:{cfg.device_index}"
    if cfg.kind in (CameraKind.RTSP, CameraKind.ONVIF):
        return cfg.url
    if cfg.kind is CameraKind.FILE:
        return cfg.path
    return None


def _from_row(row: sqlite3.Row) -> CameraConfig:
    kind = CameraKind(row["kind"])
    ref = row["device_ref"]
    return CameraConfig(
        id=row["id"],
        name=row["name"],
        kind=kind,
        device_index=int(ref.split(":", 1)[1]) if kind is CameraKind.LOCAL else None,
        url=ref if kind in (CameraKind.RTSP, CameraKind.ONVIF) else None,
        path=ref if kind is CameraKind.FILE else None,
        secret_ref=row["secret_ref"],
        width=row["width"],
        height=row["height"],
        fps=row["fps"],
        enabled=bool(row["enabled"]),
    )


class CameraRepository:
    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = conn
        self._lock = lock

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def add(self, cfg: CameraConfig) -> CameraConfig:
        now = _now_ms()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "INSERT INTO cameras(id, name, kind, device_ref, secret_ref, enabled, width, "
                    "height, fps, created_at_ms, updated_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        cfg.id,
                        cfg.name,
                        cfg.kind.value,
                        _device_ref(cfg),
                        cfg.secret_ref,
                        int(cfg.enabled),
                        cfg.width,
                        cfg.height,
                        cfg.fps,
                        now,
                        now,
                    ),
                )
                self._conn.execute("INSERT INTO camera_settings(camera_id) VALUES (?)", (cfg.id,))
                self._log("camera.add", cfg.id, now)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return cfg

    def list(self) -> list[CameraConfig]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM cameras ORDER BY created_at_ms, id").fetchall()
        return [_from_row(r) for r in rows]

    def get(self, camera_id: str) -> CameraConfig | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        return _from_row(row) if row else None

    def remove(self, camera_id: str) -> bool:
        now = _now_ms()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = self._conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
                if cur.rowcount:
                    self._log("camera.remove", camera_id, now)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return bool(cur.rowcount)

    def _log(self, action: str, target: str, now: int) -> None:
        self._conn.execute(
            "INSERT INTO operation_log(ts_ms, actor, action, target) VALUES (?, 'user', ?, ?)",
            (now, action, target),
        )
