"""Mensagens JSON-RPC 2.0 e versionamento do protocolo."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 4 * 1024 * 1024


class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # Erros da aplicação (-32000 a -32099)
    PROTOCOL_MISMATCH = -32001
    INVALID_STATE = -32002


class RpcRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


class RpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class RpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: RpcError | None = None


class RpcCallError(Exception):
    """Erro devolvido pelo agente para uma chamada."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


def encode(model: BaseModel) -> bytes:
    data = model.model_dump_json(exclude_none=False).encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("mensagem excede o tamanho máximo do protocolo")
    return data


def decode_request(raw: bytes) -> RpcRequest | RpcResponse:
    """Devolve a requisição válida ou uma resposta de erro pronta para enviar."""
    if len(raw) > MAX_MESSAGE_BYTES:
        return error_response(None, ErrorCode.INVALID_REQUEST, "mensagem grande demais")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return error_response(None, ErrorCode.PARSE_ERROR, "JSON inválido")
    try:
        return RpcRequest.model_validate(obj)
    except ValidationError as exc:
        req_id = obj.get("id") if isinstance(obj, dict) else None
        if not isinstance(req_id, int | str):
            req_id = None
        return error_response(
            req_id,
            ErrorCode.INVALID_REQUEST,
            "requisição inválida",
            exc.errors(include_url=False, include_input=False),
        )


def decode_response(raw: bytes) -> RpcResponse:
    return RpcResponse.model_validate_json(raw)


def error_response(
    req_id: int | str | None, code: int, message: str, data: Any | None = None
) -> RpcResponse:
    return RpcResponse(id=req_id, error=RpcError(code=code, message=message, data=data))
