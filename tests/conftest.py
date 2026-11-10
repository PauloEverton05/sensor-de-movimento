"""Fixtures compartilhadas."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from sentinel.common.paths import AppPaths
from sentinel.ipc.client import AgentClient, AgentUnavailableError


@dataclass
class RunningAgent:
    proc: subprocess.Popen[bytes]
    paths: AppPaths
    env: dict[str, str]

    def client(self, timeout_s: float = 5.0) -> AgentClient:
        return AgentClient.from_runtime(
            self.paths.ipc_address, self.paths.token_file, timeout_s=timeout_s
        )


def agent_command() -> list[str]:
    """Por padrão roda o agente do código-fonte; SENTINEL_AGENT_EXE testa o binário empacotado."""
    exe = os.environ.get("SENTINEL_AGENT_EXE")
    if exe:
        return [exe]
    return [sys.executable, "-m", "sentinel.agent.app"]


def _short_runtime_dir() -> Path:
    # Diretório curto para caber no limite de caminho de AF_UNIX (macOS: 104 bytes).
    return Path(tempfile.mkdtemp(prefix="snt-"))


def start_agent(data_dir: Path, runtime_dir: Path, timeout_s: float = 20.0) -> RunningAgent:
    # O fixture runtime_dir já exportou SENTINEL_RUNTIME_DIR (via monkeypatch) para este processo.
    assert os.environ.get("SENTINEL_RUNTIME_DIR") == str(runtime_dir)
    env = dict(os.environ)
    paths = AppPaths.resolve(data_dir)
    proc = subprocess.Popen(
        [*agent_command(), "--data-dir", str(data_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _out, err = proc.communicate()
            raise RuntimeError(
                f"agente saiu com código {proc.returncode}: {err.decode(errors='replace')}"
            )
        if paths.token_file.exists():
            try:
                with AgentClient.from_runtime(
                    paths.ipc_address, paths.token_file, timeout_s=2
                ) as c:
                    c.call("system.ping")
                return RunningAgent(proc=proc, paths=paths, env=env)
            except AgentUnavailableError:
                pass
        time.sleep(0.1)
    proc.kill()
    raise TimeoutError("agente não ficou pronto a tempo")


@pytest.fixture
def runtime_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    d = _short_runtime_dir()
    monkeypatch.setenv("SENTINEL_RUNTIME_DIR", str(d))
    yield d


@pytest.fixture
def agent(tmp_path: Path, runtime_dir: Path) -> Iterator[RunningAgent]:
    running = start_agent(tmp_path / "data", runtime_dir)
    yield running
    if running.proc.poll() is None:
        try:
            with running.client() as c:
                c.call("system.shutdown")
            running.proc.wait(timeout=10)
        except (AgentUnavailableError, subprocess.TimeoutExpired):
            running.proc.kill()
            running.proc.wait()
