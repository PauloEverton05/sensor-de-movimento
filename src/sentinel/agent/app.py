"""Processo do agente: inicialização, métodos IPC e encerramento limpo.

Fase 3: câmeras (cadastro, descoberta) e captura diagnóstica com supervisor,
reconexão, saúde por câmera, inibição de sono e sonda de evidências.
A vigilância propriamente dita (state machine + gravação) entra na Fase 4:
até lá, `surveillance_state` permanece STOPPED mesmo com a captura ativa,
pois câmera capturando NÃO significa vídeo sendo gravado (§18).
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import FrameType
from typing import Any

import sentinel
from sentinel.agent.capture import devices
from sentinel.agent.capture.source import build_source
from sentinel.agent.capture.supervisor import CameraSupervisor
from sentinel.agent.diagnostics import CaptureProbe
from sentinel.agent.instance_lock import AlreadyRunningError, InstanceLock
from sentinel.agent.power import PowerManager
from sentinel.common.config import load_bootstrap_config
from sentinel.common.logging import setup_logging
from sentinel.common.paths import AppPaths
from sentinel.domain.camera import CameraConfig, CameraKind
from sentinel.domain.surveillance import SurveillanceState
from sentinel.ipc import transport
from sentinel.ipc.protocol import PROTOCOL_VERSION, ErrorCode, RpcCallError
from sentinel.ipc.server import RpcServer
from sentinel.persistence import db
from sentinel.persistence.cameras import CameraRepository
from sentinel.security.secrets import SecretStore, SecretStoreError, default_secret_store

log = logging.getLogger("sentinel.agent")

HEARTBEAT_INTERVAL_S = 5.0
EXIT_OK = 0
EXIT_ALREADY_RUNNING = 3
EXIT_STARTUP_FAILURE = 4


def _now_ms() -> int:
    return int(time.time() * 1000)


def _invalid(message: str) -> RpcCallError:
    return RpcCallError(ErrorCode.INVALID_PARAMS, message)


class Agent:
    def __init__(self, paths: AppPaths, secrets: SecretStore | None = None) -> None:
        self.paths = paths
        self.started_at_ms = _now_ms()
        self._started_monotonic = time.monotonic()
        self._stop = threading.Event()
        self._db_lock = threading.Lock()
        self._capture_lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._server: RpcServer | None = None
        self._cameras: CameraRepository | None = None
        self._secrets = secrets or default_secret_store()
        self._power = PowerManager()
        self._supervisor = CameraSupervisor(self._source_for)
        self._probe: CaptureProbe | None = None
        self.state = SurveillanceState.STOPPED
        self.previous_shutdown_clean = True

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self._conn = db.connect(self.paths.database_file)
        version = db.migrate(self._conn)
        self._cameras = CameraRepository(self._conn, self._db_lock)
        self._mark_started()
        log.info(
            "agente iniciado",
            extra={"pid": os.getpid(), "schema_version": version, "version": sentinel.__version__},
        )

        token = transport.generate_token()
        transport.write_token(self.paths.token_file, token)
        server = RpcServer(self.paths.ipc_address, token)
        methods = {
            "system.hello": self._rpc_hello,
            "system.ping": lambda _p: {"pong": True, "ts_ms": _now_ms()},
            "system.status": lambda _p: self.status(),
            "system.shutdown": self._rpc_shutdown,
            "devices.discover": self._rpc_discover,
            "cameras.list": lambda _p: [self._public(c) for c in self._repo().list()],
            "cameras.add": self._rpc_camera_add,
            "cameras.remove": self._rpc_camera_remove,
            "capture.start": self._rpc_capture_start,
            "capture.stop": lambda _p: self.stop_capture(),
            "capture.health": lambda _p: self._capture_status(),
            "capture.snapshot": self._rpc_snapshot,
        }
        for name, fn in methods.items():
            server.register(name, fn)
        self._server = server
        server.start()

    def run_until_stopped(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_S):
            self._heartbeat()

    def request_stop(self) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        log.info("encerrando agente")
        self.stop_capture()
        if self._server is not None:
            self._server.stop()
        try:
            self.paths.token_file.unlink(missing_ok=True)
        except OSError:
            log.warning("não foi possível remover o arquivo de token")
        if self._conn is not None:
            with self._db_lock:
                self._conn.execute(
                    "UPDATE agent_state SET clean_shutdown = 1, last_heartbeat_at_ms = ? "
                    "WHERE id = 1",
                    (_now_ms(),),
                )
                self._conn.close()
            self._conn = None
        log.info("agente encerrado de forma limpa")

    # ------------------------------------------------------------------ estado
    def _repo(self) -> CameraRepository:
        assert self._cameras is not None
        return self._cameras

    def _mark_started(self) -> None:
        assert self._conn is not None
        with self._db_lock:
            row = self._conn.execute(
                "SELECT clean_shutdown FROM agent_state WHERE id = 1"
            ).fetchone()
            self.previous_shutdown_clean = bool(row["clean_shutdown"])
            if not self.previous_shutdown_clean:
                log.warning("a execução anterior do agente não terminou de forma limpa")
            self._conn.execute(
                "UPDATE agent_state SET clean_shutdown = 0, last_started_at_ms = ?, "
                "last_heartbeat_at_ms = ?, agent_version = ? WHERE id = 1",
                (self.started_at_ms, self.started_at_ms, sentinel.__version__),
            )

    def _heartbeat(self) -> None:
        if self._conn is None:
            return
        with self._db_lock:
            self._conn.execute(
                "UPDATE agent_state SET last_heartbeat_at_ms = ? WHERE id = 1", (_now_ms(),)
            )

    def status(self) -> dict[str, Any]:
        assert self._conn is not None
        with self._db_lock:
            schema = db.schema_version(self._conn)
        return {
            "agent_version": sentinel.__version__,
            "protocol_version": PROTOCOL_VERSION,
            "pid": os.getpid(),
            "platform": sys.platform,
            "started_at_ms": self.started_at_ms,
            "uptime_s": round(time.monotonic() - self._started_monotonic, 1),
            "surveillance_state": self.state.value,
            "recording": False,  # gravação entra na Fase 4
            "capture_active": self._supervisor.active,
            "previous_shutdown_clean": self.previous_shutdown_clean,
            "schema_version": schema,
            "data_dir": str(self.paths.data_dir),
        }

    # ------------------------------------------------------------------ câmeras
    @staticmethod
    def _public(cfg: CameraConfig) -> dict[str, Any]:
        """Representação para a interface: nunca inclui credenciais."""
        return {
            "id": cfg.id,
            "name": cfg.name,
            "kind": cfg.kind.value,
            "device_index": cfg.device_index,
            "url": cfg.url,
            "path": cfg.path,
            "has_credentials": cfg.secret_ref is not None,
            "width": cfg.width,
            "height": cfg.height,
            "fps": cfg.fps,
            "enabled": cfg.enabled,
        }

    def _source_for(self, cfg: CameraConfig) -> Any:
        creds = None
        if cfg.secret_ref:
            try:
                creds = self._secrets.get(cfg.secret_ref)
            except SecretStoreError:
                log.exception(
                    "não foi possível ler a credencial da câmera", extra={"camera_id": cfg.id}
                )
        return build_source(cfg, creds)

    def _rpc_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._supervisor.active:
            raise RpcCallError(ErrorCode.INVALID_STATE, "pare a captura antes de procurar câmeras")
        max_index = int(params.get("max_index", 4))
        if not 0 <= max_index <= 16:
            raise _invalid("max_index deve estar entre 0 e 16")
        return devices.discover(max_index)

    def _rpc_camera_add(self, params: dict[str, Any]) -> dict[str, Any]:
        kind = CameraKind(params.get("kind", ""))
        name = str(params.get("name") or "").strip()
        if not name:
            raise _invalid("informe um nome para a câmera")
        username = params.get("username")
        password = params.get("password")
        secret_ref = None
        if kind in (CameraKind.RTSP, CameraKind.ONVIF) and (username or password):
            try:
                secret_ref = self._secrets.put(str(username or ""), str(password or ""))
            except SecretStoreError as exc:
                raise RpcCallError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc
        path = params.get("path")
        if kind is CameraKind.FILE and path and not Path(str(path)).is_file():
            raise _invalid("arquivo de vídeo não encontrado")
        try:
            cfg = CameraConfig(
                id=CameraRepository.new_id(),
                name=name,
                kind=kind,
                device_index=params.get("device_index"),
                url=params.get("url"),
                path=str(Path(str(path)).resolve()) if path else None,
                secret_ref=secret_ref,
                width=params.get("width"),
                height=params.get("height"),
                fps=params.get("fps"),
            )
            self._repo().add(cfg)
        except Exception:
            if secret_ref:
                self._secrets.delete(secret_ref)
            raise
        return self._public(cfg)

    def _rpc_camera_remove(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._supervisor.active:
            raise RpcCallError(ErrorCode.INVALID_STATE, "pare a captura antes de remover câmeras")
        camera_id = str(params.get("camera_id", ""))
        cfg = self._repo().get(camera_id)
        if cfg is None:
            raise _invalid("câmera não encontrada")
        self._repo().remove(camera_id)
        if cfg.secret_ref:
            self._secrets.delete(cfg.secret_ref)
        return {"removed": camera_id}

    # ------------------------------------------------------------------ captura
    def _rpc_capture_start(self, params: dict[str, Any]) -> dict[str, Any]:
        cameras = [c for c in self._repo().list() if c.enabled]
        wanted = params.get("camera_ids")
        if wanted:
            cameras = [c for c in cameras if c.id in set(wanted)]
        if not cameras:
            raise RpcCallError(ErrorCode.INVALID_STATE, "nenhuma câmera habilitada cadastrada")
        with self._capture_lock:
            if self._supervisor.active:
                raise RpcCallError(ErrorCode.INVALID_STATE, "a captura já está ativa")
            keep_display_on = bool(params.get("keep_display_on", False))
            power_ok = False
            if params.get("inhibit_sleep", True):
                try:
                    power_ok = self._power.acquire(keep_display_on=keep_display_on)
                except OSError:
                    log.exception("falha ao inibir o sono")
            if params.get("probe", False):
                probe = CaptureProbe(
                    self.paths.data_dir / "diagnostics",
                    self._supervisor,
                    self._power,
                    snapshot_interval_s=float(params.get("snapshot_interval_s", 10)),
                )
                self._supervisor.subscribe(probe.on_frame)
                probe.start(
                    {
                        "cameras": [self._public(c) for c in cameras],
                        "inhibit_sleep": power_ok,
                        "keep_display_on": keep_display_on,
                    }
                )
                self._probe = probe
            self._supervisor.start(cameras)
        return self._capture_status()

    def stop_capture(self) -> dict[str, Any]:
        with self._capture_lock:
            probe_dir = str(self._probe.dir) if self._probe else None
            if self._probe is not None:
                self._probe.stop()
                self._probe = None
            self._supervisor.stop()
            self._power.release()
        return {"stopped": True, "probe_dir": probe_dir}

    def _capture_status(self) -> dict[str, Any]:
        return {
            "active": self._supervisor.active,
            "power": self._power.status(),
            "probe_dir": str(self._probe.dir) if self._probe else None,
            "cameras": self._supervisor.health(),
        }

    def _rpc_snapshot(self, params: dict[str, Any]) -> dict[str, Any]:
        camera_id = params.get("camera_id")
        ids = self._supervisor.camera_ids()
        if not ids:
            raise RpcCallError(ErrorCode.INVALID_STATE, "a captura não está ativa")
        camera_id = str(camera_id) if camera_id else ids[0]
        jpeg = self._supervisor.snapshot_jpeg(camera_id)
        if jpeg is None:
            raise RpcCallError(ErrorCode.INVALID_STATE, "ainda não há frame desta câmera")
        return {"camera_id": camera_id, "jpeg_b64": base64.b64encode(jpeg).decode("ascii")}

    # ------------------------------------------------------------------ sistema
    def _rpc_hello(self, params: dict[str, Any]) -> dict[str, Any]:
        client_version = params.get("protocol_version")
        if client_version != PROTOCOL_VERSION:
            raise RpcCallError(
                ErrorCode.PROTOCOL_MISMATCH,
                "versão de protocolo incompatível",
                {"agent": PROTOCOL_VERSION, "client": client_version},
            )
        return {"protocol_version": PROTOCOL_VERSION, "agent_version": sentinel.__version__}

    def _rpc_shutdown(self, _params: dict[str, Any]) -> dict[str, Any]:
        # Com vigilância ativa (Fase 4+) o encerramento exigirá a parada explícita.
        if self.state is not SurveillanceState.STOPPED:
            raise RpcCallError(
                ErrorCode.INVALID_STATE, "pare a vigilância antes de encerrar o agente"
            )
        self.request_stop()
        return {"stopping": True}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sentinel-agent", description="Agente Sentinel AI")
    parser.add_argument("--data-dir", type=Path, default=None, help="diretório de dados")
    parser.add_argument("--console-log", action="store_true", help="também loga no stderr")
    parser.add_argument("--version", action="version", version=sentinel.__version__)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = AppPaths.resolve(args.data_dir)
    paths.ensure()
    config = load_bootstrap_config(paths.bootstrap_config_file)
    setup_logging(
        paths.logs_dir,
        level=config.log_level,
        retention_days=config.log_retention_days,
        console=args.console_log,
    )

    lock = InstanceLock(paths.lock_file)
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        log.error(str(exc))
        print(f"sentinel-agent: {exc}", file=sys.stderr)
        return EXIT_ALREADY_RUNNING

    agent = Agent(paths)

    def _on_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("sinal recebido", extra={"signal": signum})
        agent.request_stop()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _on_signal)

    try:
        agent.start()
    except Exception:
        log.exception("falha na inicialização do agente")
        agent.shutdown()
        lock.release()
        return EXIT_STARTUP_FAILURE

    try:
        agent.run_until_stopped()
    finally:
        agent.shutdown()
        lock.release()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
