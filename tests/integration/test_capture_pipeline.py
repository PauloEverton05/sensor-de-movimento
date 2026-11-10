"""Pipeline e supervisor com fontes simuladas e com arquivo de vídeo real (OpenCV)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from sentinel.agent.capture.pipeline import CameraPipeline
from sentinel.agent.capture.source import ActualFormat, Image, SourceError, build_source
from sentinel.agent.capture.supervisor import CameraSupervisor
from sentinel.domain.camera import BackoffPolicy, CameraConfig, CameraKind

pytestmark = pytest.mark.integration

FAST = BackoffPolicy(initial_s=0.05, max_s=0.2, jitter=0)


class FakeSource:
    """Fonte controlável: pode falhar ao abrir, entregar N frames e então "cair"."""

    def __init__(self, world: dict[str, object]) -> None:
        self.world = world
        self.delivered = 0

    @property
    def description(self) -> str:
        return "fake"

    def open(self) -> ActualFormat:
        if self.world.get("unplugged"):
            raise SourceError("dispositivo ausente")
        return ActualFormat(width=4, height=4, fps=50, backend="FAKE")

    def read(self) -> Image | None:
        if self.world.get("unplugged"):
            return None
        time.sleep(0.02)
        self.delivered += 1
        return np.zeros((4, 4, 3), dtype=np.uint8)

    def close(self) -> None:
        pass


def wait_for(cond: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("condição não atingida a tempo")


def test_pipeline_streams_and_reconnects_after_unplug() -> None:
    world: dict[str, object] = {}
    received: list[int] = []
    pipe = CameraPipeline(
        "cam", "Fake", lambda: FakeSource(world), backoff=FAST, frame_timeout_s=0.5
    )
    pipe.subscribe(lambda _cid, f: received.append(f.seq))
    pipe.start()
    try:
        wait_for(lambda: pipe.health()["state"] == "STREAMING")
        world["unplugged"] = True
        wait_for(lambda: pipe.health()["state"] == "NO_SIGNAL")
        assert pipe.health()["receiving_frames"] is False
        # Espera o pipeline desistir da fonte e fechá-la; senão uma volta rápida do sinal
        # é absorvida sem reabrir (comportamento correto, mas não é o que este teste mede).
        wait_for(lambda: pipe.health()["connected"] is False)
        world["unplugged"] = False
        wait_for(lambda: pipe.health()["state"] == "STREAMING")
        assert pipe.health()["reconnects"] >= 1
    finally:
        pipe.stop()
    assert pipe.health()["state"] == "STOPPED"
    assert received == sorted(received) and len(set(received)) == len(received)


def test_never_streaming_while_device_missing() -> None:
    world: dict[str, object] = {"unplugged": True}
    pipe = CameraPipeline(
        "cam", "Fake", lambda: FakeSource(world), backoff=FAST, frame_timeout_s=0.5
    )
    pipe.start()
    try:
        time.sleep(0.5)
        h = pipe.health()
        assert h["state"] in ("CONNECTING", "NO_SIGNAL")
        assert h["last_error"] == "dispositivo ausente"
    finally:
        pipe.stop()


def test_stuck_read_is_reported_as_no_signal() -> None:
    """Se o driver travar dentro do read(), a saúde precisa refletir isso."""
    release = threading.Event()

    class Stuck(FakeSource):
        def read(self) -> Image | None:
            if self.delivered >= 3:
                release.wait(5)
                return None
            return super().read()

    pipe = CameraPipeline("cam", "Fake", lambda: Stuck({}), backoff=FAST, frame_timeout_s=0.3)
    pipe.start()
    try:
        wait_for(lambda: pipe.health()["frames_total"] >= 3)
        wait_for(lambda: pipe.health()["state"] == "NO_SIGNAL")
        assert pipe.health()["connected"] is True  # aberta, porém sem frames
    finally:
        release.set()
        pipe.stop()


def test_failing_subscriber_does_not_stop_capture() -> None:
    pipe = CameraPipeline("cam", "Fake", lambda: FakeSource({}), backoff=FAST)

    def bad(_cid: str, _f: object) -> None:
        raise RuntimeError("boom")

    pipe.subscribe(bad)
    pipe.start()
    try:
        wait_for(lambda: pipe.health()["frames_total"] >= 10)
    finally:
        pipe.stop()


def test_supervisor_with_real_video_file(sample_video: Path) -> None:
    cams = [
        CameraConfig(
            id=f"file-{i}",
            name=f"Arquivo {i}",
            kind=CameraKind.FILE,
            path=str(sample_video),
            fps=20,
        )
        for i in range(2)
    ]
    sup = CameraSupervisor(lambda c: build_source(c), backoff=FAST)
    sup.start(cams)
    try:
        wait_for(lambda: all(h["state"] == "STREAMING" for h in sup.health()))
        time.sleep(1.5)  # vídeo de 1 s em loop: prova que o loop funciona
        for h in sup.health():
            assert 15 <= h["fps_in"] <= 25, h
            assert (h["width"], h["height"]) == (160, 120)
        jpeg = sup.snapshot_jpeg("file-0")
        assert jpeg is not None and jpeg[:2] == b"\xff\xd8"
    finally:
        sup.stop()
    assert sup.health() == []
