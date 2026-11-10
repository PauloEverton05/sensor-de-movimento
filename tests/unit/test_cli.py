from pathlib import Path

from sentinel.ipc.cli import _build_parser


def test_global_options_before_or_after_subcommand() -> None:
    p = _build_parser()
    before = p.parse_args(["--data-dir", "X", "--timeout", "3", "status"])
    after = p.parse_args(["status", "--data-dir", "X", "--timeout", "3"])
    for ns in (before, after):
        assert ns.data_dir == Path("X")
        assert ns.timeout == 3.0
        assert ns.cmd == "status"


def test_defaults_when_omitted() -> None:
    ns = _build_parser().parse_args(["health"])
    assert ns.data_dir is None
    assert ns.timeout == 10.0
