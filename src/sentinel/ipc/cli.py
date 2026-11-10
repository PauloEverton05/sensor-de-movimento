"""sentinel-ctl: utilitário de linha de comando para falar com o agente."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
import time
from pathlib import Path
from typing import Any

from sentinel.common.paths import AppPaths
from sentinel.ipc.client import AgentClient, AgentUnavailableError
from sentinel.ipc.protocol import RpcCallError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sentinel-ctl", description="Controle do agente Sentinel AI")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--timeout", type=float, default=10.0)
    # As opções globais também valem depois do subcomando (`sentinel-ctl status --data-dir X`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS)
    _sub = p.add_subparsers(dest="cmd", required=True)

    class _Sub:
        @staticmethod
        def add_parser(name: str, **kw: Any) -> argparse.ArgumentParser:
            return _sub.add_parser(name, parents=[common], **kw)

    sub = _Sub()

    sub.add_parser("status", help="estado do agente")
    sub.add_parser("ping", help="verifica se o agente responde")
    sub.add_parser("shutdown", help="encerra o agente")

    d = sub.add_parser("discover", help="procura webcams locais (acende o LED por instantes)")
    d.add_argument("--max-index", type=int, default=4)

    sub.add_parser("cameras", help="lista as câmeras cadastradas")

    a = sub.add_parser("add-local", help="cadastra uma webcam local")
    a.add_argument("--index", type=int, default=0)
    a.add_argument("--name", default="Webcam")
    a.add_argument("--width", type=int)
    a.add_argument("--height", type=int)
    a.add_argument("--fps", type=float)

    r = sub.add_parser("add-rtsp", help="cadastra uma câmera IP (a senha é pedida no terminal)")
    r.add_argument("--url", required=True, help="rtsp://host:porta/caminho, SEM usuário/senha")
    r.add_argument("--name", default="Câmera IP")
    r.add_argument("--user", help="usuário da câmera (opcional)")

    f = sub.add_parser("add-file", help="cadastra um arquivo de vídeo como câmera (teste)")
    f.add_argument("--path", required=True)
    f.add_argument("--name", default="Arquivo de teste")
    f.add_argument("--fps", type=float)

    rm = sub.add_parser("remove", help="remove uma câmera")
    rm.add_argument("camera_id")

    s = sub.add_parser("capture-start", help="inicia a captura (diagnóstico, sem gravação)")
    s.add_argument(
        "--probe", action="store_true", help="grava evidências (teste de tela bloqueada)"
    )
    s.add_argument("--snapshot-interval", type=float, default=10.0)
    s.add_argument("--keep-display-on", action="store_true", help="mantém a tela ligada")
    s.add_argument(
        "--allow-sleep", action="store_true", help="NÃO inibe o sono (teste de controle)"
    )

    sub.add_parser("capture-stop", help="para a captura")

    h = sub.add_parser("health", help="saúde da captura por câmera")
    h.add_argument("--watch", action="store_true", help="atualiza a cada 2 s (Ctrl+C para sair)")

    sn = sub.add_parser("snapshot", help="salva o frame mais recente em JPEG")
    sn.add_argument("--camera-id")
    sn.add_argument("--out", type=Path, default=Path("snapshot.jpg"))
    return p


def _call(args: argparse.Namespace, c: AgentClient) -> Any:
    cmd = args.cmd
    if cmd in ("status", "ping", "shutdown"):
        return c.call(f"system.{cmd}")
    if cmd == "discover":
        return c.call("devices.discover", {"max_index": args.max_index})
    if cmd == "cameras":
        return c.call("cameras.list")
    if cmd == "add-local":
        return c.call(
            "cameras.add",
            {
                "kind": "local",
                "name": args.name,
                "device_index": args.index,
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
            },
        )
    if cmd == "add-rtsp":
        params: dict[str, Any] = {"kind": "rtsp", "name": args.name, "url": args.url}
        if args.user:
            params["username"] = args.user
            params["password"] = getpass.getpass(f"Senha de {args.user}: ")
        return c.call("cameras.add", params)
    if cmd == "add-file":
        return c.call(
            "cameras.add",
            {"kind": "file", "name": args.name, "path": str(args.path.resolve()), "fps": args.fps},
        )
    if cmd == "remove":
        return c.call("cameras.remove", {"camera_id": args.camera_id})
    if cmd == "capture-start":
        return c.call(
            "capture.start",
            {
                "probe": args.probe,
                "snapshot_interval_s": args.snapshot_interval,
                "keep_display_on": args.keep_display_on,
                "inhibit_sleep": not args.allow_sleep,
            },
        )
    if cmd == "capture-stop":
        return c.call("capture.stop")
    if cmd == "health":
        if not args.watch:
            return c.call("capture.health")
        try:
            while True:
                h = c.call("capture.health")
                line = (
                    " | ".join(
                        f"{cam['name']}: {cam['state']} {cam['fps_in']:.1f} fps "
                        f"(reconexões {cam['reconnects']})"
                        for cam in h["cameras"]
                    )
                    or "captura parada"
                )
                print(time.strftime("%H:%M:%S"), line, flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            return None
    if cmd == "snapshot":
        res = c.call("capture.snapshot", {"camera_id": args.camera_id})
        args.out.write_bytes(base64.b64decode(res["jpeg_b64"]))
        return {"saved": str(args.out.resolve()), "camera_id": res["camera_id"]}
    raise AssertionError(cmd)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = AppPaths.resolve(args.data_dir)
    try:
        client = AgentClient.from_runtime(
            paths.ipc_address, paths.token_file, timeout_s=args.timeout
        )
        with client as c:
            result = _call(args, c)
    except AgentUnavailableError as exc:
        print(f"AGENTE INACESSÍVEL: {exc}", file=sys.stderr)
        return 2
    except RpcCallError as exc:
        print(f"erro: {exc.message}", file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
