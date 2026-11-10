"""Testes guiados (webcam-test / lock-test) e analisador, com câmera de arquivo."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from sentinel.common.paths import AppPaths
from sentinel.ipc.cli import main as ctl_main
from sentinel.tools import guided
from sentinel.tools.probe_report import analyze
from tests.conftest import RunningAgent

pytestmark = pytest.mark.integration


def _add_file_cam(agent: RunningAgent, video: Path) -> None:
    with agent.client() as c:
        c.call("cameras.add", {"kind": "file", "name": "Arquivo", "path": str(video), "fps": 20})


def test_webcam_test_passes_with_steady_source(agent: RunningAgent, sample_video: Path) -> None:
    _add_file_cam(agent, sample_video)
    out: list[str] = []
    with agent.client() as c:
        rc = guided.webcam_test(c, 4, out.append, camera_kinds=("file",))
        assert c.call("capture.health")["active"] is False  # sempre para a captura
    assert rc == 0, "\n".join(out)
    assert any("PASSOU" in x for x in out)


def test_lock_test_flow_writes_report(agent: RunningAgent, sample_video: Path) -> None:
    _add_file_cam(agent, sample_video)
    out: list[str] = []
    with agent.client() as c:
        rc = guided.lock_test(
            c,
            agent.paths,
            minutes=30,
            allow_sleep=True,
            keep_display_on=False,
            snapshot_interval_s=1,
            say=out.append,
            wait_for_user=lambda _msg: time.sleep(3.5),
            camera_kinds=("file",),
        )
        assert c.call("capture.health")["active"] is False
    text = "\n".join(out)
    assert rc == 1 and "RESULTADO: FALHOU" in text  # sem 15 min de bloqueio, falha por definição
    assert "Win + L" in text
    reports = list((agent.paths.data_dir / "diagnostics").glob("probe-*/report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text("utf-8"))
    assert report["cameras"]["Arquivo"]["gaps_over_2s"] == []
    assert report["inhibit_sleep"] is False


def test_guided_command_starts_and_stops_agent(
    tmp_path: Path, runtime_dir: Path, sample_video: Path
) -> None:
    """Sem agente rodando, o comando guiado sobe um e o encerra ao final."""
    data = tmp_path / "data"
    paths = AppPaths.resolve(data)
    messages: list[str] = []
    client, started = guided.connect_or_start_agent(paths, data, 10, messages.append)
    try:
        assert started is True
        client.call("cameras.add", {"kind": "file", "name": "A", "path": str(sample_video)})
        assert client.call("system.status")["capture_active"] is False
        client.call("system.shutdown")
    finally:
        client.close()
    deadline = time.monotonic() + 15
    while paths.token_file.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not paths.token_file.exists(), "agente iniciado pelo teste guiado não encerrou"


def _write_probe(d: Path, lines: list[dict[str, object]]) -> Path:
    d.mkdir(parents=True)
    (d / "meta.json").write_text(
        json.dumps({"cameras": [{"id": "cam1", "name": "W"}], "inhibit_sleep": True}), "utf-8"
    )
    (d / "timeline.jsonl").write_text("\n".join(json.dumps(x) for x in lines), "utf-8")
    return d


def _tl(
    n: int, *, locked_from: int, frames: object = 30, step_ms: int = 1000
) -> list[dict[str, object]]:
    return [
        {
            "ts_ms": 1_000_000 + i * step_ms,
            "locked": i >= locked_from,
            "cameras": {"cam1": {"frames": frames(i) if callable(frames) else frames}},
        }
        for i in range(n)
    ]


def test_analyzer_passes_on_clean_locked_run(tmp_path: Path) -> None:
    r = analyze(_write_probe(tmp_path / "p", _tl(17 * 60, locked_from=60)))
    assert r["verdict"] == "PASSOU", r["reasons"]
    assert r["longest_locked_min"] >= 15


def test_analyzer_detects_agent_suspension(tmp_path: Path) -> None:
    lines = _tl(20 * 60, locked_from=60)
    for ln in lines[300:]:
        ln["ts_ms"] = int(ln["ts_ms"]) + 600_000  # 10 min sem nenhuma linha = processo parado
    r = analyze(_write_probe(tmp_path / "p", lines))
    assert r["verdict"] == "FALHOU"
    assert r["agent_suspended_gaps"] and r["agent_suspended_gaps"][0]["seconds"] >= 600


def test_analyzer_detects_camera_dying_until_the_end(tmp_path: Path) -> None:
    """Lacuna que dura até o fim do teste também precisa ser detectada."""
    lines = _tl(17 * 60, locked_from=60, frames=lambda i: 30 if i < 600 else 0)
    r = analyze(_write_probe(tmp_path / "p", lines))
    assert r["verdict"] == "FALHOU"
    gaps = r["cameras"]["W"]["gaps_over_2s"]
    assert gaps and gaps[-1]["seconds"] >= 400


def test_analyze_command_human_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    probe = _write_probe(
        tmp_path / "data" / "diagnostics" / "probe-20260101-000000", _tl(17 * 60, locked_from=60)
    )
    rc = ctl_main(["analyze", str(probe)])
    assert rc == 0
    assert "RESULTADO: PASSOU" in capsys.readouterr().out
