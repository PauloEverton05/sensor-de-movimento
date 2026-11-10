"""Empacota sentinel-agent e sentinel-ctl com PyInstaller em dist/sentinel-agent/.

Uso: uv run python scripts/build_agent.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""


def main() -> int:
    dist = ROOT / "dist"
    shutil.rmtree(dist / "sentinel-agent", ignore_errors=True)
    PyInstaller.__main__.run(
        [
            str(ROOT / "packaging" / "sentinel.spec"),
            "--noconfirm",
            "--clean",
            f"--distpath={dist}",
            f"--workpath={ROOT / 'build'}",
        ]
    )
    out = dist / "sentinel-agent"
    missing = [
        n for n in ("sentinel-agent", "sentinel-ctl") if not (out / f"{n}{EXE_SUFFIX}").exists()
    ]
    if missing:
        print(f"executáveis não encontrados: {missing}", file=sys.stderr)
        return 1
    print(f"OK: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
