"""Fontes de vídeo baseadas em OpenCV (webcam local, RTSP e arquivo).

Decisão da Fase 3: RTSP também via OpenCV (backend FFmpeg LGPL embutido no
opencv-python-headless). O PyAV entra na Fase 4 para o remux sem recodificação,
depois de verificada a licença do FFmpeg que ele embute.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

# Abrir webcams via Media Foundation fica muito lento com as transformações de
# hardware ativas (problema conhecido do OpenCV). Precisa ser definido antes do import.
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
# RTSP sobre TCP: mais robusto em Wi-Fi e atrás de NAT do que UDP.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2
import numpy as np
import numpy.typing as npt

from sentinel.domain.camera import CameraConfig, CameraKind

Image = npt.NDArray[np.uint8]

OPEN_TIMEOUT_MS = 8000
READ_TIMEOUT_MS = 5000


class SourceError(RuntimeError):
    """Falha ao abrir a fonte. A mensagem nunca contém credenciais."""


@dataclass(frozen=True, slots=True)
class Frame:
    image: Image
    seq: int
    mono_ns: int  # relógio monotônico (continuidade)
    wall_ms: int  # relógio de parede (exibição e banco)


@dataclass(slots=True)
class ActualFormat:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    backend: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class CameraSource(Protocol):
    @property
    def description(self) -> str: ...

    def open(self) -> ActualFormat: ...

    def read(self) -> Image | None:
        """Próximo frame, ou None em caso de falha (a fonte deve ser reaberta)."""
        ...

    def close(self) -> None: ...


def local_backend() -> int:
    if sys.platform == "win32":
        return int(cv2.CAP_MSMF)
    if sys.platform == "darwin":
        return int(cv2.CAP_AVFOUNDATION)
    return int(cv2.CAP_V4L2)


class OpenCVSource:
    def __init__(
        self,
        target: int | str,
        *,
        api: int,
        description: str,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
        pace_fps: float | None = None,
        loop: bool = False,
        params: list[int] | None = None,
    ) -> None:
        self._target = target
        self._api = api
        self._description = description
        self._width = width
        self._height = height
        self._fps = fps
        self._pace_fps = pace_fps
        self._loop = loop
        self._params = params or []
        self._cap: cv2.VideoCapture | None = None
        self._next_due = 0.0

    @property
    def description(self) -> str:
        return self._description

    def open(self) -> ActualFormat:
        cap = cv2.VideoCapture(self._target, self._api, self._params)
        if not cap.isOpened():
            cap.release()
            raise SourceError(f"não foi possível abrir {self._description}")
        if self._width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        if self._height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        if self._fps:
            cap.set(cv2.CAP_PROP_FPS, self._fps)
        self._cap = cap
        native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if self._pace_fps is None and self._loop:
            # Arquivo: reproduz no ritmo nativo para simular uma câmera real.
            self._pace_fps = native_fps if native_fps > 0 else 15.0
        self._next_due = time.monotonic()
        return ActualFormat(
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=native_fps,
            backend=str(cap.getBackendName()),
        )

    def read(self) -> Image | None:
        cap = self._cap
        if cap is None:
            return None
        if self._pace_fps:
            now = time.monotonic()
            if self._next_due > now:
                time.sleep(self._next_due - now)
            self._next_due = max(self._next_due + 1.0 / self._pace_fps, time.monotonic() - 1.0)
        ok, img = cap.read()
        if not ok and self._loop:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = cap.read()
        if not ok or img is None:
            return None
        # Capturas de vídeo do OpenCV entregam BGR uint8; os stubs tipam de forma genérica.
        return cast(Image, img)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


Credentials = tuple[str, str]
SourceFactory = Callable[[], CameraSource]


def inject_credentials(url: str, creds: Credentials | None) -> str:
    if not creds:
        return url
    from urllib.parse import quote

    scheme, rest = url.split("://", 1)
    user, password = (quote(c, safe="") for c in creds)
    return f"{scheme}://{user}:{password}@{rest}"


def build_source(cfg: CameraConfig, creds: Credentials | None = None) -> CameraSource:
    if cfg.kind is CameraKind.LOCAL:
        assert cfg.device_index is not None
        return OpenCVSource(
            cfg.device_index,
            api=local_backend(),
            description=f"webcam #{cfg.device_index}",
            width=cfg.width,
            height=cfg.height,
            fps=cfg.fps,
        )
    if cfg.kind in (CameraKind.RTSP, CameraKind.ONVIF):
        assert cfg.url is not None
        return OpenCVSource(
            inject_credentials(cfg.url, creds),
            api=int(cv2.CAP_FFMPEG),
            description=f"câmera IP {cfg.url}",  # URL sem credenciais
            params=[
                int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC),
                OPEN_TIMEOUT_MS,
                int(cv2.CAP_PROP_READ_TIMEOUT_MSEC),
                READ_TIMEOUT_MS,
            ],
        )
    if cfg.kind is CameraKind.FILE:
        assert cfg.path is not None
        return OpenCVSource(
            cfg.path,
            api=int(cv2.CAP_ANY),
            description=f"arquivo {Path(cfg.path).name}",
            pace_fps=cfg.fps,
            loop=True,
        )
    raise SourceError(f"tipo de câmera não suportado: {cfg.kind}")
