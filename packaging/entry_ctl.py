"""Ponto de entrada do executável empacotado do sentinel-ctl."""

from sentinel.ipc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
