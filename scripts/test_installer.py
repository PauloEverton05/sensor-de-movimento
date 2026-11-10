"""Testa o instalador de ponta a ponta: instala em silêncio numa pasta temporária,
roda o teste de fumaça contra os executáveis INSTALADOS e desinstala.

Uso: uv run python scripts/test_installer.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    setup = next((ROOT / "dist" / "installer").glob("*-setup.exe"), None)
    if setup is None:
        print("instalador não encontrado; rode scripts/build_installer.py", file=sys.stderr)
        return 1
    target = Path(tempfile.mkdtemp(prefix="snt-install-")) / "SentinelAI"
    print(f"instalando {setup.name} em {target}")
    rc = subprocess.call(
        [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={target}"]
    )
    if rc != 0:
        print(f"instalação falhou: código {rc}", file=sys.stderr)
        return rc
    for exe in ("sentinel-agent.exe", "sentinel-ctl.exe", "COMO-TESTAR.txt", "unins000.exe"):
        if not (target / exe).exists():
            print(f"arquivo ausente após instalar: {exe}", file=sys.stderr)
            return 1

    env = {**os.environ, "SENTINEL_DIST_DIR": str(target)}
    rc = subprocess.call(
        [sys.executable, str(ROOT / "scripts" / "smoke_packaged_agent.py")], env=env
    )
    if rc != 0:
        return rc

    print("desinstalando")
    rc = subprocess.call(
        [str(target / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    )
    deadline = time.monotonic() + 60  # o desinstalador termina num processo filho
    while (target / "sentinel-agent.exe").exists() and time.monotonic() < deadline:
        time.sleep(1)
    if (target / "sentinel-agent.exe").exists():
        print("desinstalação não removeu os arquivos", file=sys.stderr)
        return 1
    print("INSTALADOR OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
