from sentinel.agent.capture.pipeline import FpsMeter
from sentinel.agent.capture.source import inject_credentials
from sentinel.security.secrets import MemorySecretStore


def test_fps_meter() -> None:
    m = FpsMeter(window_s=5)
    for i in range(11):
        m.tick(int(i * 0.1 * 1e9))  # 10 fps durante 1 s
    assert abs(m.fps(int(1.0 * 1e9)) - 10.0) < 1e-6
    # janela expira: sem frames recentes, fps cai para zero
    assert m.fps(int(10 * 1e9)) == 0.0


def test_inject_credentials_percent_encodes() -> None:
    url = inject_credentials("rtsp://10.0.0.2:554/s", ("ad min", "p@ss:w/rd"))
    assert url == "rtsp://ad%20min:p%40ss%3Aw%2Frd@10.0.0.2:554/s"
    assert inject_credentials("rtsp://h/s", None) == "rtsp://h/s"


def test_memory_secret_store() -> None:
    s = MemorySecretStore()
    ref = s.put("u", "p")
    assert s.get(ref) == ("u", "p")
    s.delete(ref)
    assert s.get(ref) is None
    s.delete(ref)  # idempotente
