"""Servidor JSON-RPC local.

Uma thread aceita conexões e cada conexão é atendida na sua própria thread.
Os clientes esperados são poucos (interface, CLI); não há necessidade de asyncio aqui.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from multiprocessing.connection import (  # type: ignore[attr-defined]
    AuthenticationError,
    Connection,
    answer_challenge,
    deliver_challenge,
)
from typing import Any

from pydantic import ValidationError

from sentinel.ipc import transport
from sentinel.ipc.protocol import (
    ErrorCode,
    RpcCallError,
    RpcRequest,
    RpcResponse,
    decode_request,
    encode,
    error_response,
)

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Any]


class RpcServer:
    def __init__(self, address: str, token: bytes) -> None:
        self._address = address
        self._token = token
        self._handlers: dict[str, Handler] = {}
        self._listener = transport.create_listener(address)
        self._stopping = threading.Event()
        self._accept_thread: threading.Thread | None = None
        self._conns: set[Connection] = set()
        self._conns_lock = threading.Lock()

    def register(self, method: str, handler: Handler) -> None:
        if method in self._handlers:
            raise ValueError(f"método já registrado: {method}")
        self._handlers[method] = handler

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="ipc-accept", daemon=True
        )
        self._accept_thread.start()
        log.info("servidor IPC ouvindo", extra={"transport": transport.family_for_platform()})

    def stop(self) -> None:
        if self._stopping.is_set():
            return
        self._stopping.set()
        # accept() é bloqueante e não é interrompido por close() em todas as plataformas:
        # uma conexão local de despertar o libera.
        # Erro aqui é esperado: o loop de accept fecha a conexão de despertar.
        with contextlib.suppress(OSError, EOFError, AuthenticationError):
            transport.connect(self._address, self._token).close()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=5)
        self._listener.close()
        with self._conns_lock:
            for c in list(self._conns):
                c.close()
            self._conns.clear()

    # ------------------------------------------------------------------ internos
    def _accept_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                conn = self._listener.accept()
            except OSError:
                if self._stopping.is_set():
                    break
                log.exception("falha ao aceitar conexão IPC")
                continue
            if self._stopping.is_set():
                conn.close()
                break
            threading.Thread(
                target=self._serve_connection, args=(conn,), name="ipc-conn", daemon=True
            ).start()

    def _serve_connection(self, conn: Connection) -> None:
        try:
            deliver_challenge(conn, self._token)
            answer_challenge(conn, self._token)
        except (AuthenticationError, EOFError, OSError):
            log.warning("conexão IPC rejeitada: autenticação falhou")
            conn.close()
            return

        with self._conns_lock:
            self._conns.add(conn)
        try:
            while not self._stopping.is_set():
                try:
                    raw = conn.recv_bytes()
                except (EOFError, OSError):
                    break
                response = self._dispatch(raw)
                try:
                    conn.send_bytes(encode(response))
                except (OSError, ValueError):
                    break
        finally:
            with self._conns_lock:
                self._conns.discard(conn)
            conn.close()

    def _dispatch(self, raw: bytes) -> RpcResponse:
        req = decode_request(raw)
        if isinstance(req, RpcResponse):
            return req
        return self._call(req)

    def _call(self, req: RpcRequest) -> RpcResponse:
        handler = self._handlers.get(req.method)
        if handler is None:
            return error_response(
                req.id, ErrorCode.METHOD_NOT_FOUND, f"método desconhecido: {req.method}"
            )
        try:
            result = handler(req.params)
        except RpcCallError as exc:
            return error_response(req.id, exc.code, exc.message, exc.data)
        except (ValidationError, TypeError, ValueError) as exc:
            return error_response(req.id, ErrorCode.INVALID_PARAMS, str(exc))
        except Exception:
            log.exception("erro interno no método IPC", extra={"method": req.method})
            return error_response(req.id, ErrorCode.INTERNAL_ERROR, "erro interno do agente")
        return RpcResponse(id=req.id, result=result)
