"""sentinel-ctl: utilitário de linha de comando para falar com o agente."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentinel.common.paths import AppPaths
from sentinel.ipc.client import AgentClient, AgentUnavailableError
from sentinel.ipc.protocol import RpcCallError

_COMMANDS = {
    "status": "system.status",
    "ping": "system.ping",
    "shutdown": "system.shutdown",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sentinel-ctl", description="Controle do agente Sentinel AI"
    )
    parser.add_argument("command", choices=sorted(_COMMANDS))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    paths = AppPaths.resolve(args.data_dir)
    try:
        with AgentClient.from_runtime(
            paths.ipc_address, paths.token_file, timeout_s=args.timeout
        ) as c:
            result = c.call(_COMMANDS[args.command])
    except AgentUnavailableError as exc:
        print(f"AGENTE INACESSÍVEL: {exc}", file=sys.stderr)
        return 2
    except RpcCallError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
