"""Testes guiados para o usuário final (sem terminal de desenvolvedor).

`sentinel-ctl webcam-test` e `sentinel-ctl lock-test` sobem o agente se ele não
estiver rodando, cadastram a webcam integrada se não houver nenhuma, conduzem o
teste com instruções na tela e imprimem o veredito.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sentinel.common.paths import AppPaths
from sentinel.ipc.client import AgentClient, AgentUnavailableError
from sentinel.tools.probe_report import analyze, format_report

AGENT_START_TIMEOUT_S = 30


def _agent_command(data_dir: Path | None) -> list[str]:
    if getattr(sys, "frozen", False):  # executável empacotado: o agente fica ao lado
        exe = Path(sys.executable).with_name(
            "sentinel-agent.exe" if sys.platform == "win32" else "sentinel-agent"
        )
        cmd = [str(exe)]
    else:
        cmd = [sys.executable, "-m", "sentinel.agent.app"]
    cmd.append("--console-log")
    if data_dir is not None:
        cmd += ["--data-dir", str(data_dir)]
    return cmd


def connect_or_start_agent(
    paths: AppPaths, data_dir: Path | None, timeout_s: float, say: Callable[[str], None]
) -> tuple[AgentClient, bool]:
    """Devolve (cliente conectado, se o agente foi iniciado por nós)."""
    try:
        return AgentClient.from_runtime(
            paths.ipc_address, paths.token_file, timeout_s=timeout_s
        ).connect(), False
    except AgentUnavailableError:
        pass
    say("Iniciando o agente do Sentinel AI (uma nova janela vai abrir; não a feche)...")
    # Janela própria no Windows: o usuário vê o agente rodando e os logs.
    flags: int = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(_agent_command(data_dir), creationflags=flags)  # noqa: S603
    deadline = time.monotonic() + AGENT_START_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            return AgentClient.from_runtime(
                paths.ipc_address, paths.token_file, timeout_s=timeout_s
            ).connect(), True
        except AgentUnavailableError:
            time.sleep(0.5)
    raise AgentUnavailableError("o agente não iniciou a tempo; veja a janela do agente")


def ensure_local_camera(
    c: AgentClient, say: Callable[[str], None], kinds: tuple[str, ...] = ("local",)
) -> list[dict[str, Any]]:
    """Câmeras do teste; cadastra a webcam #0 se não houver nenhuma do tipo pedido."""
    local = [cam for cam in c.call("cameras.list") if cam["kind"] in kinds and cam["enabled"]]
    if local:
        return local
    say("Nenhuma webcam cadastrada. Cadastrando a webcam #0 como 'Webcam integrada'...")
    return [c.call("cameras.add", {"kind": "local", "name": "Webcam integrada", "device_index": 0})]


def _wait_streaming(c: AgentClient, timeout_s: float = 30) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    h: dict[str, Any] = {}
    while time.monotonic() < deadline:
        h = c.call("capture.health")
        if h["cameras"] and all(cam["state"] == "STREAMING" for cam in h["cameras"]):
            return h
        time.sleep(0.5)
    errors = "; ".join(
        f"{cam['name']}: {cam['state']} ({cam['last_error']})" for cam in h.get("cameras", [])
    )
    raise RuntimeError(
        "a webcam não começou a enviar imagens em 30 s. "
        "Feche outros programas que usam a câmera (Teams, Zoom, Câmera do Windows) e confira "
        f"Configurações > Privacidade > Câmera. Detalhes: {errors or 'sem informação'}"
    )


def _guard_not_capturing(c: AgentClient) -> None:
    if c.call("capture.health")["active"]:
        raise RuntimeError("já existe uma captura em andamento; rode `sentinel-ctl capture-stop`")


def webcam_test(
    c: AgentClient,
    seconds: int,
    say: Callable[[str], None],
    camera_kinds: tuple[str, ...] = ("local",),
) -> int:
    _guard_not_capturing(c)
    cams = ensure_local_camera(c, say, camera_kinds)
    c.call("capture.start", {"camera_ids": [x["id"] for x in cams], "inhibit_sleep": False})
    try:
        say("Abrindo a webcam (o LED vai acender)...")
        h0 = {x["camera_id"]: x for x in _wait_streaming(c)["cameras"]}
        t0 = time.monotonic()
        say(f"Medindo por {seconds} s. Deixe o ambiente bem iluminado.")
        while (elapsed := time.monotonic() - t0) < seconds:
            time.sleep(min(5.0, seconds - elapsed))
            h = c.call("capture.health")
            line = " | ".join(
                f"{x['name']}: {x['state']} {x['fps_in']:.1f} fps" for x in h["cameras"]
            )
            say(f"  {int(time.monotonic() - t0):3d}s  {line}")
        h1 = {x["camera_id"]: x for x in c.call("capture.health")["cameras"]}
        duration = time.monotonic() - t0
    finally:
        c.call("capture.stop")

    ok = True
    say("")
    for cid, end in h1.items():
        start = h0.get(cid, {"frames_total": 0})
        measured = (end["frames_total"] - start["frames_total"]) / duration
        nominal = end["nominal_fps"] or 30.0
        cam_ok = measured >= 0.95 * nominal and end["reconnects"] == 0
        ok = ok and cam_ok
        say(f"{end['name']}: {end['width']}x{end['height']} via {end['backend']}")
        say(f"  {measured:.1f} fps medido / {nominal:.1f} nominal; reconexões: {end['reconnects']}")
        say(
            f"  {'PASSOU' if cam_ok else 'FALHOU'}"
            + ("" if cam_ok else "  (pouca luz reduz o fps da webcam; acenda as luzes e repita)")
        )
    return 0 if ok else 1


def lock_test(
    c: AgentClient,
    paths: AppPaths,
    *,
    minutes: int,
    allow_sleep: bool,
    keep_display_on: bool,
    snapshot_interval_s: float,
    say: Callable[[str], None],
    wait_for_user: Callable[[str], object] = input,
    camera_kinds: tuple[str, ...] = ("local",),
) -> int:
    _guard_not_capturing(c)
    cams = ensure_local_camera(c, say, camera_kinds)
    started = c.call(
        "capture.start",
        {
            "camera_ids": [x["id"] for x in cams],
            "probe": True,
            "snapshot_interval_s": snapshot_interval_s,
            "inhibit_sleep": not allow_sleep,
            "keep_display_on": keep_display_on,
        },
    )
    probe_dir = Path(started["probe_dir"])
    try:
        _wait_streaming(c)
        power = c.call("capture.health")["power"]
        say("")
        say("=" * 60)
        say("  TESTE DE TELA BLOQUEADA — a captura está rodando")
        say("=" * 60)
        say(f"Inibição de sono: {'ATIVA' if power['active'] else 'desligada (teste de controle)'}")
        say("")
        say("1. Coloque o celular com um CRONÔMETRO rodando na frente da webcam.")
        say("2. Deixe o notebook NA TOMADA.")
        say("3. Pressione  Win + L  para bloquear.")
        say(f"4. Não toque no notebook por {minutes} minutos.")
        say("   A tela vai apagar sozinha depois de ~1 minuto: é exatamente o que queremos testar.")
        say("   Passe na frente da câmera por volta dos minutos 3, 9 e 14 e anote os horários.")
        say("5. Depois, desbloqueie e volte a esta janela.")
        say("")
        wait_for_user("Quando tiver desbloqueado, pressione ENTER aqui para encerrar o teste... ")
    finally:
        c.call("capture.stop")

    report = analyze(probe_dir)
    (probe_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    say(format_report(report))
    say(f"Fotos do teste: {probe_dir / 'snapshots'}")
    say(f"Relatório para enviar: {probe_dir / 'report.json'}")
    return 0 if report["verdict"] == "PASSOU" else 1
