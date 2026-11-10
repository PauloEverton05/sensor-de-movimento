"""Fase 3 ponta a ponta: agente real + IPC + câmera de arquivo + sonda + analisador."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sentinel.ipc.protocol import ErrorCode, RpcCallError
from tests.conftest import RunningAgent

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def _wait_streaming(c: object, timeout: float = 15) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        h = c.call("capture.health")  # type: ignore[attr-defined]
        if h["cameras"] and all(cam["state"] == "STREAMING" for cam in h["cameras"]):
            return h  # type: ignore[no-any-return]
        time.sleep(0.2)
    raise AssertionError(f"câmeras não chegaram a STREAMING: {h}")


def test_camera_crud_and_capture_with_probe(agent: RunningAgent, sample_video: Path) -> None:
    with agent.client() as c:
        cam = c.call(
            "cameras.add", {"kind": "file", "name": "Teste", "path": str(sample_video), "fps": 20}
        )
        assert c.call("cameras.list")[0]["id"] == cam["id"]

        started = c.call("capture.start", {"probe": True, "snapshot_interval_s": 1})
        assert started["active"] is True
        h = _wait_streaming(c)
        assert h["cameras"][0]["connected"] is True

        status = c.call("system.status")
        # câmera capturando NÃO é vigilância nem gravação (§18)
        assert status["capture_active"] is True
        assert status["surveillance_state"] == "STOPPED"
        assert status["recording"] is False

        snap = c.call("capture.snapshot", {})
        assert base64.b64decode(snap["jpeg_b64"])[:2] == b"\xff\xd8"

        with pytest.raises(RpcCallError) as exc:
            c.call("cameras.remove", {"camera_id": cam["id"]})
        assert exc.value.code == ErrorCode.INVALID_STATE

        time.sleep(3.5)
        stopped = c.call("capture.stop")
        assert c.call("capture.health")["active"] is False
        assert c.call("cameras.remove", {"camera_id": cam["id"]}) == {"removed": cam["id"]}

    probe = Path(stopped["probe_dir"])
    lines = [json.loads(x) for x in (probe / "timeline.jsonl").read_text("utf-8").splitlines()]
    assert len(lines) >= 3
    assert any(ln["cameras"][cam["id"]]["frames"] > 0 for ln in lines)
    assert list((probe / "snapshots").rglob("*.jpg"))

    # O analisador roda; sem bloqueio de 15 min o veredito é FALHOU por definição.
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "analyze_probe.py"), str(probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(r.stdout)
    assert report["verdict"] == "FALHOU"
    assert any("bloqueio contínuo" in x for x in report["reasons"])
    assert report["cameras"]["Teste"]["gaps_over_2s"] == []  # relatório usa o nome da câmera


def test_rtsp_credentials_never_exposed(agent: RunningAgent) -> None:
    with agent.client() as c:
        cam = c.call(
            "cameras.add",
            {
                "kind": "rtsp",
                "name": "IP",
                "url": "rtsp://127.0.0.1:1/x",
                "username": "admin",
                "password": "segredo-123",
            },
        )
        listed = c.call("cameras.list")
    assert cam["has_credentials"] is True
    blob = json.dumps(listed)
    assert "segredo-123" not in blob and "admin" not in blob
    db_bytes = agent.paths.database_file.read_bytes()
    wal = agent.paths.database_file.with_name("sentinel.db-wal")
    if wal.exists():
        db_bytes += wal.read_bytes()
    assert b"segredo-123" not in db_bytes
    logs = b"".join(p.read_bytes() for p in agent.paths.logs_dir.glob("*"))
    assert b"segredo-123" not in logs


def test_invalid_camera_params(agent: RunningAgent) -> None:
    with agent.client() as c:
        for params in (
            {"kind": "rtsp", "name": "x", "url": "rtsp://u:p@h/s"},
            {"kind": "local", "name": "x"},
            {"kind": "banana", "name": "x"},
            {"kind": "file", "name": "x", "path": "nao-existe.avi"},
        ):
            with pytest.raises(RpcCallError) as exc:
                c.call("cameras.add", params)
            assert exc.value.code == ErrorCode.INVALID_PARAMS, params


def test_capture_start_without_cameras(agent: RunningAgent) -> None:
    with agent.client() as c, pytest.raises(RpcCallError) as exc:
        c.call("capture.start", {})
    assert exc.value.code == ErrorCode.INVALID_STATE
