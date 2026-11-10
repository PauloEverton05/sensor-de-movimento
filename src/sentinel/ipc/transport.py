"""Transporte local: Named Pipe (Windows) ou Unix Domain Socket (Linux/macOS).

Usa multiprocessing.connection, da biblioteca padrão, que já oferece framing por
comprimento e autenticação mútua HMAC por desafio. Nenhuma porta TCP é aberta.

Segurança:
- Unix: socket dentro de um diretório 0700 do usuário.
- Windows: o pipe é criado com o descritor de segurança padrão; a autenticação é
  feita pelo token, que fica num arquivo dentro do perfil privado do usuário.
  Uma DACL explícita restrita ao SID do usuário está planejada para a Fase 10.
"""

from __future__ import annotations

import os
import secrets
import sys
from multiprocessing.connection import Client, Connection, Listener
from pathlib import Path
from typing import cast

TOKEN_BYTES = 32


def family_for_platform() -> str:
    return "AF_PIPE" if sys.platform == "win32" else "AF_UNIX"


def generate_token() -> bytes:
    return secrets.token_bytes(TOKEN_BYTES)


def write_token(path: Path, token: bytes) -> None:
    """Grava o token de forma atômica e legível apenas pelo usuário."""
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.hex().encode("ascii"))
    finally:
        os.close(fd)
    tmp.replace(path)


def read_token(path: Path) -> bytes:
    return bytes.fromhex(path.read_text(encoding="ascii").strip())


def create_listener(address: str) -> Listener:
    """Listener sem autenticação no accept(): o handshake é feito por conexão,
    numa thread própria, para um cliente lento não bloquear os demais."""
    if family_for_platform() == "AF_UNIX":
        sock = Path(address)
        # Remove socket órfão de uma execução anterior (o lock de instância garante
        # que nenhum outro agente está usando este endereço).
        if sock.exists():
            sock.unlink()
    listener = Listener(address, family=family_for_platform(), backlog=8)
    if family_for_platform() == "AF_UNIX":
        Path(address).chmod(0o600)
    return listener


def connect(address: str, token: bytes) -> Connection:
    # No Windows é um PipeConnection, com a mesma interface pública de Connection.
    # O tipo declarado no typeshed muda por plataforma; passar por `object` mantém o
    # mypy consistente em Windows, Linux e macOS.
    conn: object = Client(address, family=family_for_platform(), authkey=token)
    return cast(Connection, conn)
