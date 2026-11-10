"""Pipeline de captura de uma câmera: thread de leitura, reconexão e saúde.

Princípios (docs/ARQUITETURA.md §3.3 e §6.2):
- O estado é derivado de fatos medidos (último frame), nunca de suposições.
  Se a leitura travar dentro do driver, o tempo sem frame cresce e o estado
  vira NO_SIGNAL mesmo com a thread presa.
- Assinantes recebem cada frame de forma síncrona e DEVEM ser rápidos (só
  enfileirar). Um assinante com erro não derruba a captura.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from sentinel.agent.capture.source import ActualFormat, CameraSource, Frame, SourceError
from sentinel.domain.camera import BackoffPolicy, LinkState, derive_link_state

log = logging.getLogger(__name__)

FrameSubscriber = Callable[[str, Frame], None]

# Leituras com falha seguidas antes de considerar a fonte perdida e reabrir.
MAX_CONSECUTIVE_READ_FAILURES = 10


class FpsMeter:
    """FPS medido numa janela deslizante (segundos)."""

    def __init__(self, window_s: float = 5.0) -> None:
        self._window_ns = int(window_s * 1e9)
        self._stamps: deque[int] = deque()

    def tick(self, mono_ns: int) -> None:
        self._stamps.append(mono_ns)
        self._trim(mono_ns)

    def fps(self, now_ns: int) -> float:
        self._trim(now_ns)
        if len(self._stamps) < 2:
            return 0.0
        span = (self._stamps[-1] - self._stamps[0]) / 1e9
        return (len(self._stamps) - 1) / span if span > 0 else 0.0

    def _trim(self, now_ns: int) -> None:
        limit = now_ns - self._window_ns
        while self._stamps and self._stamps[0] < limit:
            self._stamps.popleft()


class CameraPipeline:
    def __init__(
        self,
        camera_id: str,
        name: str,
        source_factory: Callable[[], CameraSource],
        *,
        backoff: BackoffPolicy | None = None,
        frame_timeout_s: float = 5.0,
    ) -> None:
        self.camera_id = camera_id
        self.name = name
        self._factory = source_factory
        self._backoff = backoff or BackoffPolicy()
        self._frame_timeout_s = frame_timeout_s
        self._subscribers: list[FrameSubscriber] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._meter = FpsMeter()
        # fatos medidos
        self._opened = False
        self._last_frame_mono_ns: int | None = None
        self._last_frame_wall_ms: int | None = None
        self._latest: Frame | None = None
        self._seq = 0
        self._reconnects = 0
        self._last_error: str | None = None
        self._format = ActualFormat()
        self._started_wall_ms: int | None = None

    # ------------------------------------------------------------------ controle
    def subscribe(self, cb: FrameSubscriber) -> None:
        self._subscribers.append(cb)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._started_wall_ms = int(time.time() * 1000)
        self._thread = threading.Thread(
            target=self._run, name=f"capture-{self.camera_id[:8]}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout_s: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            if self._thread.is_alive():
                log.warning(
                    "thread de captura não terminou no prazo", extra={"camera_id": self.camera_id}
                )
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def latest_frame(self) -> Frame | None:
        with self._lock:
            return self._latest

    def health(self) -> dict[str, Any]:
        now_ns = time.monotonic_ns()
        with self._lock:
            since = (
                None
                if self._last_frame_mono_ns is None
                else (now_ns - self._last_frame_mono_ns) / 1e9
            )
            state = derive_link_state(
                capture_requested=self.running,
                opened=self._opened,
                seconds_since_last_frame=since,
                frame_timeout_s=self._frame_timeout_s,
            )
            return {
                "camera_id": self.camera_id,
                "name": self.name,
                "state": state.value,
                "connected": self._opened,
                "receiving_frames": state is LinkState.STREAMING,
                "fps_in": round(self._meter.fps(now_ns), 2),
                "frames_total": self._seq,
                "seconds_since_last_frame": None if since is None else round(since, 2),
                "last_frame_at_ms": self._last_frame_wall_ms,
                "reconnects": self._reconnects,
                "last_error": self._last_error,
                "width": self._format.width,
                "height": self._format.height,
                "nominal_fps": self._format.fps,
                "backend": self._format.backend,
                "started_at_ms": self._started_wall_ms,
            }

    # ------------------------------------------------------------------ thread
    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            if attempt > 0:
                delay = self._backoff.delay(attempt, random.random())  # noqa: S311
                log.info(
                    "reconectando câmera",
                    extra={
                        "camera_id": self.camera_id,
                        "attempt": attempt,
                        "delay_s": round(delay, 2),
                    },
                )
                if self._stop.wait(delay):
                    break
            source = self._factory()
            try:
                fmt = source.open()
            except SourceError as exc:
                self._set_error(str(exc))
                attempt += 1
                continue
            except Exception as exc:
                log.exception(
                    "erro inesperado ao abrir a câmera", extra={"camera_id": self.camera_id}
                )
                self._set_error(type(exc).__name__)
                attempt += 1
                continue

            with self._lock:
                self._opened = True
                self._format = fmt
                if attempt > 0:
                    self._reconnects += 1
            log.info(
                "câmera aberta",
                extra={
                    "camera_id": self.camera_id,
                    "source": source.description,
                    "width": fmt.width,
                    "height": fmt.height,
                    "fps": fmt.fps,
                    "backend": fmt.backend,
                },
            )
            got_frame = self._read_loop(source)
            source.close()
            with self._lock:
                self._opened = False
            if self._stop.is_set():
                break
            log.warning("sinal da câmera perdido", extra={"camera_id": self.camera_id})
            # Se chegou a receber frames, recomeça o backoff do início.
            attempt = 1 if got_frame else attempt + 1
        with self._lock:
            self._opened = False

    def _read_loop(self, source: CameraSource) -> bool:
        failures = 0
        got_frame = False
        while not self._stop.is_set():
            img = source.read()
            if img is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_READ_FAILURES:
                    self._set_error("leituras consecutivas falharam")
                    return got_frame
                time.sleep(0.05)
                continue
            failures = 0
            got_frame = True
            mono = time.monotonic_ns()
            wall = int(time.time() * 1000)
            with self._lock:
                self._seq += 1
                frame = Frame(image=img, seq=self._seq, mono_ns=mono, wall_ms=wall)
                self._latest = frame
                self._last_frame_mono_ns = mono
                self._last_frame_wall_ms = wall
                self._last_error = None
                self._meter.tick(mono)
            for cb in self._subscribers:
                try:
                    cb(self.camera_id, frame)
                except Exception:
                    log.exception("assinante de frames falhou", extra={"camera_id": self.camera_id})
        return got_frame

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
