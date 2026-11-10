import json

from sentinel.ipc.protocol import (
    ErrorCode,
    RpcRequest,
    RpcResponse,
    decode_request,
    decode_response,
    encode,
)


def test_request_roundtrip() -> None:
    req = RpcRequest(id=7, method="system.status", params={"a": 1})
    decoded = decode_request(encode(req))
    assert isinstance(decoded, RpcRequest)
    assert decoded == req


def test_invalid_json_returns_parse_error() -> None:
    resp = decode_request(b"{not json")
    assert isinstance(resp, RpcResponse)
    assert resp.error is not None
    assert resp.error.code == ErrorCode.PARSE_ERROR


def test_missing_method_is_invalid_request_and_keeps_id() -> None:
    resp = decode_request(json.dumps({"jsonrpc": "2.0", "id": 3}).encode())
    assert isinstance(resp, RpcResponse)
    assert resp.id == 3
    assert resp.error is not None
    assert resp.error.code == ErrorCode.INVALID_REQUEST


def test_unknown_fields_rejected() -> None:
    raw = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "x", "evil": True}).encode()
    resp = decode_request(raw)
    assert isinstance(resp, RpcResponse)
    assert resp.error is not None


def test_response_roundtrip() -> None:
    resp = RpcResponse(id=1, result={"ok": True})
    assert decode_response(encode(resp)) == resp
