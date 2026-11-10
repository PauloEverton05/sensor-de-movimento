# PyInstaller spec: sentinel-agent + sentinel-ctl numa única pasta (onedir),
# compartilhando o mesmo runtime. Uso: uv run python scripts/build_agent.py
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH é injetado pelo PyInstaller)
SRC = str(ROOT / "src")
DATAS = collect_data_files("sentinel")  # migrações SQL (importlib.resources)


def _analysis(entry: str):
    return Analysis(  # noqa: F821
        [str(ROOT / "packaging" / entry)],
        pathex=[SRC],
        datas=DATAS,
        hiddenimports=[],
        excludes=["tkinter", "unittest", "pydoc_data"],
        noarchive=False,
    )


a_agent = _analysis("entry_agent.py")
a_ctl = _analysis("entry_ctl.py")


def _exe(a, name: str):
    pyz = PYZ(a.pure)  # noqa: F821
    return EXE(  # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=name,
        console=True,
        upx=False,
    )


exe_agent = _exe(a_agent, "sentinel-agent")
exe_ctl = _exe(a_ctl, "sentinel-ctl")

coll = COLLECT(  # noqa: F821
    exe_agent,
    a_agent.binaries,
    a_agent.datas,
    exe_ctl,
    a_ctl.binaries,
    a_ctl.datas,
    upx=False,
    name="sentinel-agent",
)
