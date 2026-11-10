"""Testes com a webcam real. Nunca rodam no CI.

    uv run pytest -m hardware -s

Acendem o LED da câmera por cerca de 1 minuto. Nenhuma imagem é salva.
"""

from __future__ import annotations

import time

import pytest

from sentinel.agent.capture.devices import discover
from sentinel.agent.capture.source import build_source
from sentinel.agent.capture.supervisor import CameraSupervisor
from sentinel.domain.camera import CameraConfig, CameraKind

pytestmark = pytest.mark.hardware

DURATION_S = 60


def test_discover_finds_a_webcam() -> None:
    result = discover(max_index=3)
    print("\n", result)
    assert result["devices"], "nenhuma webcam encontrada"
    assert result["devices"][0]["readable"]


def test_webcam_sustains_nominal_fps() -> None:
    cfg = CameraConfig(id="hw", name="Webcam", kind=CameraKind.LOCAL, device_index=0)
    sup = CameraSupervisor(build_source)
    sup.start([cfg])
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and sup.health()[0]["state"] != "STREAMING":
            time.sleep(0.2)
        h0 = sup.health()[0]
        assert h0["state"] == "STREAMING", h0
        start_frames, t0 = h0["frames_total"], time.monotonic()
        time.sleep(DURATION_S)
        h1 = sup.health()[0]
    finally:
        sup.stop()
    measured = (h1["frames_total"] - start_frames) / (time.monotonic() - t0)
    nominal = h1["nominal_fps"] or 30.0
    print(
        f"\n{h1['width']}x{h1['height']} via {h1['backend']}: "
        f"{measured:.1f} fps medido / {nominal:.1f} nominal; reconexões={h1['reconnects']}"
    )
    assert h1["reconnects"] == 0
    # Webcams reduzem o fps sozinhas em pouca luz (exposição automática). Ilumine a cena.
    assert measured >= 0.95 * nominal, "fps abaixo de 95% do nominal (cena escura?)"
