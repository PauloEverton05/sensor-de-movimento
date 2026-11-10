import pytest

from sentinel.domain.camera import (
    BackoffPolicy,
    CameraConfig,
    CameraKind,
    LinkState,
    derive_link_state,
)


def test_backoff_grows_and_caps() -> None:
    p = BackoffPolicy(initial_s=1, max_s=60, factor=2, jitter=0)
    assert [p.delay(n, 0.5) for n in range(1, 9)] == [1, 2, 4, 8, 16, 32, 60, 60]
    assert p.delay(0, 0.5) == 0


def test_backoff_jitter_bounds() -> None:
    p = BackoffPolicy(initial_s=10, max_s=60, jitter=0.2)
    assert p.delay(1, 0.0) == pytest.approx(8.0)
    assert p.delay(1, 0.999999) == pytest.approx(12.0, rel=1e-4)
    assert p.delay(10, 0.999999) <= 60


@pytest.mark.parametrize(
    ("requested", "opened", "since", "expected"),
    [
        (False, True, 0.1, LinkState.STOPPED),
        (True, False, None, LinkState.CONNECTING),
        (True, True, None, LinkState.CONNECTING),
        (True, True, 1.0, LinkState.STREAMING),
        (True, True, 6.0, LinkState.NO_SIGNAL),  # aberta, mas sem frames: nunca STREAMING
        (True, False, 3.0, LinkState.NO_SIGNAL),  # já recebeu frames e caiu
    ],
)
def test_link_state_is_derived_from_facts(
    requested: bool, opened: bool, since: float | None, expected: LinkState
) -> None:
    assert (
        derive_link_state(
            capture_requested=requested,
            opened=opened,
            seconds_since_last_frame=since,
            frame_timeout_s=5.0,
        )
        is expected
    )


def test_rtsp_url_with_credentials_rejected() -> None:
    with pytest.raises(ValueError, match="credenciais"):
        CameraConfig(id="c", name="n", kind=CameraKind.RTSP, url="rtsp://admin:x@10.0.0.2/s")


def test_rtsp_url_with_at_in_path_is_fine() -> None:
    CameraConfig(id="c", name="n", kind=CameraKind.RTSP, url="rtsp://10.0.0.2/live@main")


def test_local_requires_index() -> None:
    with pytest.raises(ValueError):
        CameraConfig(id="c", name="n", kind=CameraKind.LOCAL)


def test_file_requires_path() -> None:
    with pytest.raises(ValueError):
        CameraConfig(id="c", name="n", kind=CameraKind.FILE)
