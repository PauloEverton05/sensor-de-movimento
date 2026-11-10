"""Teste de fumaça dos executáveis empacotados.

1. Roda a suíte de integração contra o sentinel-agent empacotado.
2. Sobe o agente empacotado e exercita o sentinel-ctl empacotado (status + shutdown).

Critério da Fase 2: o agente empacotado inicia e responde a `status` via socket local,
em cada SO. Uso: uv run python scripts/smoke_packaged_agent.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIX = ".exe" if sys.platform == "win32" else ""
OUT = ROOT / "dist" / "sentinel-agent"


def _ctl_roundtrip(agent: Path, ctl: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="snt-") as tmp:
        env = {**os.environ, "SENTINEL_RUNTIME_DIR": str(Path(tmp) / "rt")}
        data = str(Path(tmp) / "data")
        proc = subprocess.Popen([str(agent), "--data-dir", data], env=env)
        try:
            deadline = time.monotonic() + 30
            while True:
                r = subprocess.run(
                    [str(ctl), "status", "--data-dir", data],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if r.returncode == 0:
                    break
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise RuntimeError(f"sentinel-ctl status falhou: {r.stderr}")
                time.sleep(0.3)
            status = json.loads(r.stdout)
            assert status["surveillance_state"] == "STOPPED", status
            print(f"sentinel-ctl status OK: {status['agent_version']} / {status['platform']}")
            r = subprocess.run(
                [str(ctl), "shutdown", "--data-dir", data], env=env, check=True, capture_output=True
            )
            assert proc.wait(timeout=20) == 0, "agente não encerrou com código 0"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()  # libera os arquivos antes de apagar o diretório temporário


def main() -> int:
    agent = OUT / f"sentinel-agent{SUFFIX}"
    ctl = OUT / f"sentinel-ctl{SUFFIX}"
    for exe in (agent, ctl):
        if not exe.exists():
            print(f"binário não encontrado: {exe} — rode scripts/build_agent.py", file=sys.stderr)
            return 1
    env = {**os.environ, "SENTINEL_AGENT_EXE": str(agent)}
    rc = subprocess.call(
        [sys.executable, "-m", "pytest", "-q", "tests/integration"], cwd=ROOT, env=env
    )
    if rc != 0:
        return rc
    _ctl_roundtrip(agent, ctl)
    print("FUMAÇA OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
