"""Cliente do agente (usado pela interface e pela CLI)."""

from __future__ import annotations

import itertools
import threading
from multiprocessing import AuthenticationError
from multiprocessing.connection import Connection
from pathlib import Path
from types import TracebackType
from typing import Any

from sentinel.ipc import transport
from sentinel.ipc.protocol import (
    PROTOCOL_VERSION,
    ErrorCode,
    RpcCallError,
    RpcRequest,
    decode_response,
    encode,
)


class AgentUnavailableError(ConnectionError):
    """O agente não está rodando ou não respondeu."""


class AgentClient:
    def __init__(self, address: str, token: bytes, *, timeout_s: float = 5.0) -> None:
        self._address = address
        self._token = token
        self._timeout_s = timeout_s
        self._conn: Connection | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    @classmethod
    def from_runtime(cls, address: str, token_file: Path, *, timeout_s: float = 5.0) -> AgentClient:
        try:
            token = transport.read_token(token_file)
        except (OSError, ValueError) as exc:
            raise AgentUnavailableError("token do agente não encontrado") from exc
        return cls(address, token, timeout_s=timeout_s)

    def connect(self) -> AgentClient:
        try:
            self._conn = transport.connect(self._address, self._token)
        except AuthenticationError as exc:
            raise AgentUnavailableError(
                "autenticação recusada pelo agente (token inválido)"
            ) from exc
        except (OSError, EOFError) as exc:
            raise AgentUnavailableError(f"agente inacessível: {exc}") from exc
        info = self.call("system.hello", {"protocol_version": PROTOCOL_VERSION})
        if info.get("protocol_version") != PROTOCOL_VERSION:
            self.close()
            raise RpcCallError(ErrorCode.PROTOCOL_MISMATCH, "versão de protocolo incompatível")
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> AgentClient:
        return self.connect() if self._conn is None else self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._conn is None:
            raise AgentUnavailableError("cliente não conectado")
        with self._lock:
            req = RpcRequest(id=next(self._ids), method=method, params=params or {})
            try:
                self._conn.send_bytes(encode(req))
                if not self._conn.poll(self._timeout_s):
                    raise AgentUnavailableError(f"sem resposta do agente em {self._timeout_s}s")
                raw = self._conn.recv_bytes()
            except (OSError, EOFError) as exc:
                self.close()
                raise AgentUnavailableError(f"conexão com o agente perdida: {exc}") from exc
        resp = decode_response(raw)
        if resp.id != req.id:
            raise AgentUnavailableError("resposta fora de ordem")
        if resp.error is not None:
            raise RpcCallError(resp.error.code, resp.error.message, resp.error.data)
        return resp.result
