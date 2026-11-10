"""Analisa uma sonda de captura (atalho para `sentinel-ctl analyze`).

Uso:
    uv run python scripts/analyze_probe.py <pasta probe-AAAAMMDD-HHMMSS>
    uv run python scripts/analyze_probe.py --latest
"""

from __future__ import annotations

import sys

from sentinel.ipc.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] != "--latest":
        raise SystemExit(main(["analyze", "--json", *args]))
    raise SystemExit(main(["analyze", "--json"]))
