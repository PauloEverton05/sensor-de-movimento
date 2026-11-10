"""Câmeras: tipos, estado do link e política de reconexão (regras puras)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CameraKind(StrEnum):
    LOCAL = "local"  # webcam integrada ou USB
    RTSP = "rtsp"  # câmera IP
    ONVIF = "onvif"  # câmera IP descoberta via ONVIF (stream RTSP)
    FILE = "file"  # arquivo de vídeo (testes e demonstração)


class LinkState(StrEnum):
    """Estado da conexão com a fonte de vídeo (independente de gravação e IA)."""

    STOPPED = "STOPPED"  # captura não solicitada
    CONNECTING = "CONNECTING"  # abrindo o dispositivo / stream
    STREAMING = "STREAMING"  # recebendo frames dentro do prazo
    NO_SIGNAL = "NO_SIGNAL"  # aberto, mas sem frames além do prazo, ou falha ao abrir


@dataclass(frozen=True, slots=True)
class CameraConfig:
    id: str
    name: str
    kind: CameraKind
    device_index: int | None = None  # LOCAL
    url: str | None = None  # RTSP/ONVIF, SEM credenciais
    path: str | None = None  # FILE
    secret_ref: str | None = None  # referência ao cofre do SO
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.kind is CameraKind.LOCAL and (self.device_index is None or self.device_index < 0):
            raise ValueError("câmera local exige device_index >= 0")
        if self.kind in (CameraKind.RTSP, CameraKind.ONVIF):
            if not self.url or "://" not in self.url:
                raise ValueError("câmera IP exige uma URL rtsp://")
            if "@" in self.url.split("://", 1)[1].split("/", 1)[0]:
                raise ValueError(
                    "a URL não pode conter credenciais; informe usuário e senha à parte"
                )
        if self.kind is CameraKind.FILE and not self.path:
            raise ValueError("fonte de arquivo exige path")
        if self.fps is not None and self.fps <= 0:
            raise ValueError("fps deve ser positivo")


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """Backoff exponencial com jitter para reconexão (§13)."""

    initial_s: float = 1.0
    max_s: float = 60.0
    factor: float = 2.0
    jitter: float = 0.2  # fração ± aplicada ao atraso

    def delay(self, attempt: int, rand: float) -> float:
        """Atraso antes da tentativa `attempt` (1 = primeira reconexão). `rand` ∈ [0, 1)."""
        if attempt < 1:
            return 0.0
        base = min(self.max_s, self.initial_s * self.factor ** (attempt - 1))
        spread = base * self.jitter
        return max(0.0, min(self.max_s, base - spread + 2 * spread * rand))


def derive_link_state(
    *,
    capture_requested: bool,
    opened: bool,
    seconds_since_last_frame: float | None,
    frame_timeout_s: float,
) -> LinkState:
    """Estado observado a partir de fatos medidos. Nunca diz STREAMING sem frame recente."""
    if not capture_requested:
        return LinkState.STOPPED
    if not opened:
        return LinkState.CONNECTING if seconds_since_last_frame is None else LinkState.NO_SIGNAL
    if seconds_since_last_frame is None:
        return LinkState.CONNECTING
    if seconds_since_last_frame <= frame_timeout_s:
        return LinkState.STREAMING
    return LinkState.NO_SIGNAL
