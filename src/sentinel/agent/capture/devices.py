"""Descoberta de câmeras locais.

Atenção: sondar índices ABRE cada câmera por um instante (o LED acende).
Por isso só roda quando o usuário pede explicitamente.

Limitação da Fase 3: o OpenCV não expõe o nome nem um ID estável do dispositivo.
Os nomes vêm do SO e só são associados a um índice quando há exatamente um
dispositivo (associação inequívoca). A enumeração com ID estável (símbolo do
Media Foundation, /dev/v4l/by-id, uniqueID do AVFoundation) fica registrada
como pendência no PROJECT_STATUS.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2

from sentinel.agent.capture.source import local_backend


def os_camera_names() -> list[str]:
    """Nomes de câmeras informados pelo SO (sem abrir os dispositivos)."""
    try:
        if sys.platform == "win32":
            cmd = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in 'Camera','Image' "
                "-and $_.Status -eq 'OK' } | Select-Object -ExpandProperty Name | ConvertTo-Json",
            ]
            # Comando fixo, sem nenhuma entrada do usuário.
            out = subprocess.run(  # noqa: S603
                cmd, capture_output=True, text=True, timeout=15, check=False
            ).stdout
            data = json.loads(out) if out.strip() else []
            return [data] if isinstance(data, str) else [str(x) for x in data]
        if sys.platform.startswith("linux"):
            names = []
            for d in sorted(Path("/sys/class/video4linux").glob("video*")):
                name_file = d / "name"
                if name_file.exists():
                    names.append(name_file.read_text(encoding="utf-8").strip())
            return names
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return []


def probe_local_devices(max_index: int = 4) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for idx in range(max_index + 1):
        cap = cv2.VideoCapture(idx, local_backend())
        try:
            if not cap.isOpened():
                continue
            ok, _ = cap.read()
            found.append(
                {
                    "index": idx,
                    "readable": bool(ok),
                    "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
                    "backend": str(cap.getBackendName()),
                }
            )
        finally:
            cap.release()
    return found


def discover(max_index: int = 4) -> dict[str, Any]:
    devices = probe_local_devices(max_index)
    names = os_camera_names()
    if len(devices) == 1 and len(names) == 1:
        devices[0]["name"] = names[0]
    return {"devices": devices, "os_reported_names": names}
