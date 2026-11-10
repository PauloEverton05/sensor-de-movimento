"""Sonda de captura: evidências para o teste de tela bloqueada (§12.6 / §20.3).

Grava em <dados>/diagnostics/probe-<data-hora>/:
- timeline.jsonl: uma linha por segundo com os frames recebidos por câmera,
  o estado do link, se a sessão estava bloqueada e se o sono estava inibido.
- snapshots/<camera>/<hora>.jpg: um frame a cada N segundos com data e hora
  gravadas na imagem (prova visual, junto com o cronômetro filmado).
- meta.json: ambiente e parâmetros do teste.

As imagens ficam só no diretório de dados do usuário; nada sai da máquina.
"""

from __future__ import annotations

import json
import logging
import platform
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2

import sentinel
from sentinel.agent.capture.source import Frame
from sentinel.agent.capture.supervisor import CameraSupervisor
from sentinel.agent.power import PowerManager
from sentinel.agent.session import is_session_locked

log = logging.getLogger(__name__)


class CaptureProbe:
    def __init__(
        self,
        base_dir: Path,
        supervisor: CameraSupervisor,
        power: PowerManager,
        *,
        snapshot_interval_s: float = 10.0,
    ) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = base_dir / f"probe-{stamp}"
        self._supervisor = supervisor
        self._power = power
        self._snapshot_interval_s = max(1.0, snapshot_interval_s)
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def on_frame(self, camera_id: str, _frame: Frame) -> None:
        with self._lock:
            self._counts[camera_id] += 1

    def start(self, extra_meta: dict[str, Any]) -> None:
        (self.dir / "snapshots").mkdir(parents=True, exist_ok=True)
        meta = {
            "agent_version": sentinel.__version__,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "snapshot_interval_s": self._snapshot_interval_s,
            **extra_meta,
        }
        (self.dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
        self._thread = threading.Thread(target=self._run, name="capture-probe", daemon=True)
        self._thread.start()
        log.info("sonda de captura iniciada", extra={"probe_dir": str(self.dir)})

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        timeline = (self.dir / "timeline.jsonl").open("a", encoding="utf-8", buffering=1)
        next_tick = time.monotonic() + 1.0
        next_snapshot = time.monotonic()
        try:
            while not self._stop.wait(max(0.0, next_tick - time.monotonic())):
                next_tick += 1.0
                with self._lock:
                    counts = dict(self._counts)
                    self._counts.clear()
                health = {h["camera_id"]: h for h in self._supervisor.health()}
                cams = {
                    cid: {
                        "frames": counts.get(cid, 0),
                        "state": h["state"],
                        "fps_in": h["fps_in"],
                        "reconnects": h["reconnects"],
                    }
                    for cid, h in health.items()
                }
                line = {
                    "ts_ms": int(time.time() * 1000),
                    "locked": is_session_locked(),
                    "power_request": self._power.status()["active"],
                    "cameras": cams,
                }
                timeline.write(json.dumps(line) + "\n")
                if time.monotonic() >= next_snapshot:
                    next_snapshot += self._snapshot_interval_s
                    self._snapshot(health)
        except Exception:
            log.exception("sonda de captura falhou")
        finally:
            timeline.close()

    def _snapshot(self, health: dict[str, dict[str, Any]]) -> None:
        for cid, frame in self._supervisor.latest_frames().items():
            if frame is None:
                continue
            age_s = (time.monotonic_ns() - frame.mono_ns) / 1e9
            img = frame.image.copy()
            captured = datetime.fromtimestamp(frame.wall_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            label = f"{captured}  {health.get(cid, {}).get('state', '?')}"
            if age_s > 2:
                label += f"  (frame com {age_s:.0f}s de idade!)"
            cv2.putText(img, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(img, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            out = self.dir / "snapshots" / cid[:8]
            out.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%H%M%S") + ".jpg"
            cv2.imwrite(str(out / name), img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
