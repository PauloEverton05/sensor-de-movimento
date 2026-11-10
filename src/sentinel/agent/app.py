"""Processo do agente: inicialização, métodos IPC de sistema e encerramento limpo.

Fase 2: o agente sobe, aplica migrações, detecta parada não limpa, publica o
servidor IPC e responde a system.hello/ping/status/shutdown. Câmeras e gravação
entram nas Fases 3 e 4.
"""

from __future__ import annotations

import argparse
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
from sentinel.agent.instance_lock import AlreadyRunningError, InstanceLock
from sentinel.common.config import load_bootstrap_config
from sentinel.common.logging import setup_logging
from sentinel.common.paths import AppPaths
from sentinel.domain.surveillance import SurveillanceState
from sentinel.ipc import transport
from sentinel.ipc.protocol import PROTOCOL_VERSION, ErrorCode, RpcCallError
from sentinel.ipc.server import RpcServer
from sentinel.persistence import db

log = logging.getLogger("sentinel.agent")

HEARTBEAT_INTERVAL_S = 5.0
EXIT_OK = 0
EXIT_ALREADY_RUNNING = 3
EXIT_STARTUP_FAILURE = 4


def _now_ms() -> int:
    return int(time.time() * 1000)


class Agent:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.started_at_ms = _now_ms()
        self._started_monotonic = time.monotonic()
        self._stop = threading.Event()
        self._db_lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._server: RpcServer | None = None
        self.state = SurveillanceState.STOPPED
        self.previous_shutdown_clean = True

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self._conn = db.connect(self.paths.database_file)
        version = db.migrate(self._conn)
        self._mark_started()
        log.info(
            "agente iniciado",
            extra={"pid": os.getpid(), "schema_version": version, "version": sentinel.__version__},
        )

        token = transport.generate_token()
        transport.write_token(self.paths.token_file, token)
        self._server = RpcServer(self.paths.ipc_address, token)
        self._server.register("system.hello", self._rpc_hello)
        self._server.register("system.ping", lambda _p: {"pong": True, "ts_ms": _now_ms()})
        self._server.register("system.status", lambda _p: self.status())
        self._server.register("system.shutdown", self._rpc_shutdown)
        self._server.start()

    def run_until_stopped(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_S):
            self._heartbeat()

    def request_stop(self) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        log.info("encerrando agente")
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
            "previous_shutdown_clean": self.previous_shutdown_clean,
            "schema_version": schema,
            "data_dir": str(self.paths.data_dir),
        }

    # ------------------------------------------------------------------ métodos IPC
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
        # Encerrar o agente com vigilância ativa só será permitido pelo fluxo de parada
        # explícita (Fase 4+). Na Fase 2 o estado é sempre STOPPED.
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
