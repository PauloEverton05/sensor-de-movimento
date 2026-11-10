"""Análise de uma sonda de captura: veredito do teste de tela bloqueada.

Critérios (docs/ARQUITETURA.md §12.6):
- O agente não pode ter ficado suspenso (buracos na própria timeline).
- Pelo menos 15 min contínuos de sessão bloqueada.
- Nenhuma lacuna de frames ≥ 2 s em nenhuma câmera.
- FPS médio com a sessão bloqueada ≥ 95% do FPS com ela desbloqueada.
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_GAP_S = 2
MIN_LOCKED_S = 15 * 60
MIN_FPS_RATIO = 0.95
TICK_TOLERANCE_MS = 2500  # a timeline tem uma linha por segundo


def _fmt(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M:%S")


def latest_probe(diagnostics_dir: Path) -> Path | None:
    probes = sorted(p for p in diagnostics_dir.glob("probe-*") if p.is_dir())
    return probes[-1] if probes else None


def _frame_gaps(lines: list[dict[str, Any]], cid: str) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    run_start: dict[str, Any] | None = None

    def close(end_ts: int) -> None:
        assert run_start is not None
        secs = round((end_ts - run_start["ts_ms"]) / 1000)
        if secs >= MAX_GAP_S:
            gaps.append(
                {
                    "from": _fmt(run_start["ts_ms"]),
                    "seconds": secs,
                    "locked": run_start.get("locked"),
                }
            )

    for ln in lines:
        frames = ln["cameras"].get(cid, {}).get("frames", 0)
        if frames == 0:
            if run_start is None:
                run_start = ln
        elif run_start is not None:
            close(ln["ts_ms"])
            run_start = None
    if run_start is not None:  # lacuna que durou até o fim do teste
        close(lines[-1]["ts_ms"] + 1000)
    return gaps


def analyze(probe: Path) -> dict[str, Any]:
    raw = (probe / "timeline.jsonl").read_text("utf-8").splitlines()
    lines = [json.loads(x) for x in raw if x.strip()]
    if not lines:
        raise ValueError("timeline vazia: a sonda não chegou a registrar nada")
    meta = json.loads((probe / "meta.json").read_text("utf-8"))
    names = {c["id"]: c["name"] for c in meta.get("cameras", [])}
    camera_ids = sorted({cid for ln in lines for cid in ln["cameras"]})

    agent_gaps = [
        {
            "from": _fmt(a["ts_ms"]),
            "to": _fmt(b["ts_ms"]),
            "seconds": round((b["ts_ms"] - a["ts_ms"]) / 1000),
        }
        for a, b in itertools.pairwise(lines)
        if b["ts_ms"] - a["ts_ms"] > TICK_TOLERANCE_MS
    ]

    best = 0.0
    best_range: tuple[int, int] | None = None
    run_start: int | None = None
    prev_ts: int | None = None
    for ln in lines:
        contiguous = prev_ts is not None and ln["ts_ms"] - prev_ts <= TICK_TOLERANCE_MS
        if ln.get("locked") is True:
            if run_start is None or not contiguous:
                run_start = ln["ts_ms"]
            length = (ln["ts_ms"] - run_start) / 1000
            if length > best:
                best, best_range = length, (run_start, ln["ts_ms"])
        else:
            run_start = None
        prev_ts = ln["ts_ms"]

    locked_lines = [ln for ln in lines if ln.get("locked") is True]
    report: dict[str, Any] = {
        "probe": str(probe),
        "start": _fmt(lines[0]["ts_ms"]),
        "end": _fmt(lines[-1]["ts_ms"]),
        "duration_min": round((lines[-1]["ts_ms"] - lines[0]["ts_ms"]) / 60000, 1),
        "inhibit_sleep": meta.get("inhibit_sleep"),
        "keep_display_on": meta.get("keep_display_on"),
        "platform": meta.get("platform"),
        "agent_version": meta.get("agent_version"),
        "agent_suspended_gaps": agent_gaps,
        "locked_total_min": round(len(locked_lines) / 60, 1),
        "longest_locked_min": round(best / 60, 1),
        "longest_locked_range": (
            f"{_fmt(best_range[0])} a {_fmt(best_range[1])}" if best_range else None
        ),
        "cameras": {},
    }

    verdict_ok = not agent_gaps and best >= MIN_LOCKED_S
    reasons: list[str] = []
    if agent_gaps:
        total = sum(g["seconds"] for g in agent_gaps)
        reasons.append(
            f"o agente ficou suspenso {len(agent_gaps)} vez(es), {total} s no total "
            "(provável Modern Standby/suspensão)"
        )
    if best < MIN_LOCKED_S:
        reasons.append(f"bloqueio contínuo de {best / 60:.1f} min (mínimo: 15 min)")

    for cid in camera_ids:
        gaps = _frame_gaps(lines, cid)
        unlocked = [
            ln["cameras"].get(cid, {}).get("frames", 0) for ln in lines if ln.get("locked") is False
        ]
        locked = [ln["cameras"].get(cid, {}).get("frames", 0) for ln in locked_lines]
        fps_u = sum(unlocked) / len(unlocked) if unlocked else 0.0
        fps_l = sum(locked) / len(locked) if locked else 0.0
        ratio = fps_l / fps_u if fps_u else 0.0
        cam_ok = not gaps and ratio >= MIN_FPS_RATIO
        verdict_ok = verdict_ok and cam_ok
        label = names.get(cid, cid[:8])
        report["cameras"][label] = {
            "fps_unlocked": round(fps_u, 2),
            "fps_locked": round(fps_l, 2),
            "locked_vs_unlocked": f"{ratio:.0%}",
            "gaps_over_2s": gaps,
            "ok": cam_ok,
        }
        if gaps:
            reasons.append(f"{label}: {len(gaps)} lacuna(s) de frames de 2 s ou mais")
        elif locked and ratio < MIN_FPS_RATIO:
            reasons.append(f"{label}: fps com a tela bloqueada foi {ratio:.0%} do normal")

    report["verdict"] = "PASSOU" if verdict_ok else "FALHOU"
    report["reasons"] = reasons
    return report


def format_report(r: dict[str, Any]) -> str:
    out = [
        "",
        "=" * 60,
        f"  RESULTADO: {r['verdict']}",
        "=" * 60,
        f"Duração do teste .......... {r['duration_min']} min ({r['start']} a {r['end']})",
        f"Maior bloqueio contínuo ... {r['longest_locked_min']} min"
        + (f" ({r['longest_locked_range']})" if r["longest_locked_range"] else ""),
        f"Inibição de sono .......... {'sim' if r['inhibit_sleep'] else 'NÃO'}"
        + ("  (tela forçada ligada)" if r.get("keep_display_on") else ""),
        "Agente suspenso ........... "
        + (
            "não"
            if not r["agent_suspended_gaps"]
            else ", ".join(
                f"{g['from']}-{g['to']} ({g['seconds']} s)" for g in r["agent_suspended_gaps"]
            )
        ),
    ]
    for name, cam in r["cameras"].items():
        out.append(
            f"{name}: {cam['fps_unlocked']} fps desbloqueado / {cam['fps_locked']} fps bloqueado "
            f"({cam['locked_vs_unlocked']}); lacunas: {len(cam['gaps_over_2s'])}"
        )
    if r["reasons"]:
        out.append("")
        out.append("Motivos:")
        out.extend(f"  - {x}" for x in r["reasons"])
    out.append("")
    return "\n".join(out)
