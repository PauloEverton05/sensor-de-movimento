"""Gera o instalador Windows 11 (Inno Setup) a partir de dist/sentinel-agent/.

Uso: uv run python scripts/build_agent.py && uv run python scripts/build_installer.py
Requer o Inno Setup 6 (no CI: `choco install innosetup`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import sentinel

ROOT = Path(__file__).resolve().parent.parent


def find_iscc() -> Path | None:
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    if found:
        return Path(found)
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")):
        if base and (p := Path(base) / "Inno Setup 6" / "ISCC.exe").exists():
            return p
    return None


def main() -> int:
    if sys.platform != "win32":
        print("o instalador é só para Windows", file=sys.stderr)
        return 1
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup 6 não encontrado (ISCC.exe)", file=sys.stderr)
        return 1
    if not (ROOT / "dist" / "sentinel-agent" / "sentinel-agent.exe").exists():
        print("rode scripts/build_agent.py antes", file=sys.stderr)
        return 1
    rc = subprocess.call(
        [
            str(iscc),
            f"/DAppVersion={sentinel.__version__}",
            "/Q",
            str(ROOT / "packaging" / "windows" / "sentinel.iss"),
        ]
    )
    if rc == 0:
        print(f"OK: {next((ROOT / 'dist' / 'installer').glob('*.exe'))}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
