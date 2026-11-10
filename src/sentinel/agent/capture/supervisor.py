"""Supervisor de câmeras: um pipeline isolado por câmera."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import cv2

from sentinel.agent.capture.pipeline import CameraPipeline, FrameSubscriber
from sentinel.agent.capture.source import CameraSource
from sentinel.domain.camera import BackoffPolicy, CameraConfig

log = logging.getLogger(__name__)

SourceBuilder = Callable[[CameraConfig], CameraSource]


class CameraSupervisor:
    def __init__(
        self,
        source_builder: SourceBuilder,
        *,
        backoff: BackoffPolicy | None = None,
        frame_timeout_s: float = 5.0,
    ) -> None:
        self._build = source_builder
        self._backoff = backoff or BackoffPolicy()
        self._frame_timeout_s = frame_timeout_s
        self._pipelines: dict[str, CameraPipeline] = {}
        self._subscribers: list[FrameSubscriber] = []
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return bool(self._pipelines)

    def subscribe(self, cb: FrameSubscriber) -> None:
        with self._lock:
            self._subscribers.append(cb)
            for p in self._pipelines.values():
                p.subscribe(cb)

    def unsubscribe_all(self) -> None:
        with self._lock:
            self._subscribers.clear()

    def start(self, cameras: list[CameraConfig]) -> None:
        with self._lock:
            if self._pipelines:
                raise RuntimeError("captura já está em andamento")
            for cfg in cameras:
                if not cfg.enabled:
                    continue
                pipe = CameraPipeline(
                    cfg.id,
                    cfg.name,
                    lambda c=cfg: self._build(c),  # type: ignore[misc]
                    backoff=self._backoff,
                    frame_timeout_s=self._frame_timeout_s,
                )
                for cb in self._subscribers:
                    pipe.subscribe(cb)
                self._pipelines[cfg.id] = pipe
            pipelines = list(self._pipelines.values())
        for p in pipelines:
            p.start()
        log.info("captura iniciada", extra={"cameras": len(pipelines)})

    def stop(self) -> None:
        with self._lock:
            pipelines = list(self._pipelines.values())
            self._pipelines.clear()
            self._subscribers.clear()
        for p in pipelines:
            p.stop()
        if pipelines:
            log.info("captura parada", extra={"cameras": len(pipelines)})

    def health(self) -> list[dict[str, Any]]:
        with self._lock:
            pipelines = list(self._pipelines.values())
        return [p.health() for p in pipelines]

    def camera_ids(self) -> list[str]:
        with self._lock:
            return list(self._pipelines)

    def snapshot_jpeg(self, camera_id: str, quality: int = 85) -> bytes | None:
        with self._lock:
            pipe = self._pipelines.get(camera_id)
        frame = pipe.latest_frame() if pipe else None
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame.image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return bytes(buf) if ok else None

    def latest_frames(self) -> dict[str, Any]:
        with self._lock:
            pipelines = list(self._pipelines.values())
        return {p.camera_id: p.latest_frame() for p in pipelines}
