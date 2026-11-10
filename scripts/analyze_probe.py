"""Analisa uma sonda de captura e emite o veredito do teste de tela bloqueada.

Uso:
    uv run python scripts/analyze_probe.py <pasta probe-AAAAMMDD-HHMMSS>
    uv run python scripts/analyze_probe.py --latest      # a sonda mais recente

Critérios (docs/ARQUITETURA.md §12.6):
- Nenhuma lacuna maior que 2 s entre frames durante todo o teste.
- Pelo menos 15 min contínuos de sessão bloqueada.
- FPS médio durante o bloqueio ≥ 95% do FPS com a sessão desbloqueada.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_GAP_S = 2
MIN_LOCKED_S = 15 * 60
MIN_FPS_RATIO = 0.95


def _fmt(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M:%S")


def _default_data_dir() -> Path:
    env = os.environ.get("SENTINEL_DATA_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "SentinelAI"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SentinelAI"
    return Path.home() / ".local" / "share" / "SentinelAI"


def analyze(probe: Path) -> dict[str, Any]:
    lines = [json.loads(x) for x in (probe / "timeline.jsonl").read_text("utf-8").splitlines() if x]
    if not lines:
        raise SystemExit("timeline vazia")
    meta = json.loads((probe / "meta.json").read_text("utf-8"))
    camera_ids = sorted({cid for ln in lines for cid in ln["cameras"]})
    report: dict[str, Any] = {
        "probe": str(probe),
        "start": _fmt(lines[0]["ts_ms"]),
        "end": _fmt(lines[-1]["ts_ms"]),
        "duration_min": round((lines[-1]["ts_ms"] - lines[0]["ts_ms"]) / 60000, 1),
        "inhibit_sleep": meta.get("inhibit_sleep"),
        "keep_display_on": meta.get("keep_display_on"),
        "platform": meta.get("platform"),
        "cameras": {},
    }

    # Buracos na própria timeline = o agente inteiro ficou sem executar (suspensão).
    agent_gaps = [
        {
            "from": _fmt(a["ts_ms"]),
            "to": _fmt(b["ts_ms"]),
            "seconds": round((b["ts_ms"] - a["ts_ms"]) / 1000),
        }
        for a, b in itertools.pairwise(lines)
        if b["ts_ms"] - a["ts_ms"] > 2500
    ]
    report["agent_suspended_gaps"] = agent_gaps

    locked_lines = [ln for ln in lines if ln.get("locked") is True]
    # Maior trecho contínuo bloqueado (sem buracos na timeline).
    best = 0.0
    best_range: tuple[int, int] | None = None
    run_start: int | None = None
    prev_ts: int | None = None
    for ln in lines:
        contiguous = prev_ts is not None and ln["ts_ms"] - prev_ts <= 2500
        if ln.get("locked") is True:
            if run_start is None or not contiguous:
                run_start = ln["ts_ms"]
            length = (ln["ts_ms"] - run_start) / 1000
            if length > best:
                best, best_range = length, (run_start, ln["ts_ms"])
        else:
            run_start = None
        prev_ts = ln["ts_ms"]
    report["locked_total_min"] = round(len(locked_lines) / 60, 1)
    report["longest_locked_min"] = round(best / 60, 1)
    report["longest_locked_range"] = (
        f"{_fmt(best_range[0])} a {_fmt(best_range[1])}" if best_range else None
    )

    verdict_ok = not agent_gaps and best >= MIN_LOCKED_S
    for cid in camera_ids:
        gaps: list[dict[str, Any]] = []
        run_start = None
        for ln in lines:
            frames = ln["cameras"].get(cid, {}).get("frames", 0)
            if frames == 0:
                run_start = run_start or ln["ts_ms"]
            elif run_start is not None:
                secs = round((ln["ts_ms"] - run_start) / 1000)
                if secs >= MAX_GAP_S:
                    gaps.append(
                        {"from": _fmt(run_start), "seconds": secs, "locked": ln.get("locked")}
                    )
                run_start = None
        unlocked = [
            ln["cameras"].get(cid, {}).get("frames", 0) for ln in lines if ln.get("locked") is False
        ]
        locked = [ln["cameras"].get(cid, {}).get("frames", 0) for ln in locked_lines]
        fps_u = sum(unlocked) / len(unlocked) if unlocked else 0.0
        fps_l = sum(locked) / len(locked) if locked else 0.0
        ratio = fps_l / fps_u if fps_u else 0.0
        cam_ok = not gaps and ratio >= MIN_FPS_RATIO
        verdict_ok = verdict_ok and cam_ok
        report["cameras"][cid[:8]] = {
            "fps_unlocked": round(fps_u, 2),
            "fps_locked": round(fps_l, 2),
            "locked_vs_unlocked": f"{ratio:.0%}",
            "gaps_over_2s": gaps,
            "ok": cam_ok,
        }

    reasons = []
    if agent_gaps:
        reasons.append("o agente ficou suspenso (provável Modern Standby/suspensão)")
    if best < MIN_LOCKED_S:
        reasons.append(f"bloqueio contínuo de {best / 60:.1f} min < 15 min")
    for cid, cam in report["cameras"].items():
        if cam["gaps_over_2s"]:
            reasons.append(f"câmera {cid}: {len(cam['gaps_over_2s'])} lacuna(s) de frames")
        elif not cam["ok"]:
            reasons.append(f"câmera {cid}: fps bloqueado {cam['locked_vs_unlocked']} do normal")
    report["verdict"] = "PASSOU" if verdict_ok else "FALHOU"
    report["reasons"] = reasons
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("probe", nargs="?", type=Path)
    ap.add_argument("--latest", action="store_true")
    args = ap.parse_args()
    if args.latest or args.probe is None:
        probes = sorted((_default_data_dir() / "diagnostics").glob("probe-*"))
        if not probes:
            print("nenhuma sonda encontrada", file=sys.stderr)
            return 1
        probe = probes[-1]
    else:
        probe = args.probe
    report = analyze(probe)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASSOU" else 1


if __name__ == "__main__":
    raise SystemExit(main())
