"""Agente real como subprocesso + IPC real (Named Pipe / Unix socket)."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from sentinel.ipc.client import AgentClient, AgentUnavailableError
from sentinel.ipc.protocol import ErrorCode, RpcCallError
from tests.conftest import RunningAgent, agent_command, start_agent

pytestmark = pytest.mark.integration


def test_status_reports_real_state(agent: RunningAgent) -> None:
    with agent.client() as c:
        status = c.call("system.status")
    assert status["surveillance_state"] == "STOPPED"
    assert status["protocol_version"] == 1
    # No Windows o python.exe do venv é um lançador: o PID do agente é o do processo filho.
    assert isinstance(status["pid"], int) and status["pid"] > 0
    assert status["schema_version"] >= 1
    assert status["previous_shutdown_clean"] is True


def test_unknown_method(agent: RunningAgent) -> None:
    with agent.client() as c, pytest.raises(RpcCallError) as exc:
        c.call("does.not.exist")
    assert exc.value.code == ErrorCode.METHOD_NOT_FOUND


def test_wrong_token_is_rejected(agent: RunningAgent) -> None:
    bad = AgentClient(agent.paths.ipc_address, b"\x00" * 32, timeout_s=2)
    with pytest.raises(AgentUnavailableError, match="autenticação"):
        bad.connect()
    # o agente continua atendendo clientes legítimos
    with agent.client() as c:
        assert c.call("system.ping")["pong"] is True


def test_multiple_concurrent_clients(agent: RunningAgent) -> None:
    clients = [agent.client().connect() for _ in range(3)]
    try:
        for c in clients:
            assert c.call("system.ping")["pong"] is True
    finally:
        for c in clients:
            c.close()


def test_second_instance_refused(agent: RunningAgent) -> None:
    proc = subprocess.run(
        [*agent_command(), "--data-dir", str(agent.paths.data_dir)],
        env=agent.env,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 3, proc.stderr


def test_clean_shutdown_via_rpc(agent: RunningAgent) -> None:
    with agent.client() as c:
        assert c.call("system.shutdown") == {"stopping": True}
    assert agent.proc.wait(timeout=15) == 0
    assert not agent.paths.token_file.exists()
    conn = sqlite3.connect(agent.paths.database_file)
    assert conn.execute("SELECT clean_shutdown FROM agent_state").fetchone()[0] == 1
    conn.close()


def test_client_reports_unavailable_when_agent_dies(agent: RunningAgent) -> None:
    c = agent.client().connect()
    agent.proc.kill()
    agent.proc.wait()
    with pytest.raises(AgentUnavailableError):
        c.call("system.ping")


def test_crash_is_detected_on_next_start(tmp_path: Path, runtime_dir: Path) -> None:
    first = start_agent(tmp_path / "data", runtime_dir)
    first.proc.kill()  # simula queda (sem encerramento limpo)
    first.proc.wait()

    second = start_agent(tmp_path / "data", runtime_dir)
    try:
        with second.client() as c:
            assert c.call("system.status")["previous_shutdown_clean"] is False
            c.call("system.shutdown")
        assert second.proc.wait(timeout=15) == 0
    finally:
        if second.proc.poll() is None:
            second.proc.kill()
