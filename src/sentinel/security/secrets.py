"""Armazenamento de credenciais no cofre nativo do SO (docs/ARQUITETURA.md §13).

O banco guarda apenas `secret_ref` (um UUID). A credencial fica no cofre:
Windows Credential Manager, macOS Keychain ou Secret Service no Linux.

SENTINEL_SECRET_BACKEND=memory usa um cofre só em memória (testes e CI, onde não
há cofre do SO). Nesse modo nada é persistido.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from typing import Protocol

SERVICE = "SentinelAI"


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    def put(self, username: str, password: str) -> str: ...
    def get(self, ref: str) -> tuple[str, str] | None: ...
    def delete(self, ref: str) -> None: ...


class MemorySecretStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def put(self, username: str, password: str) -> str:
        ref = str(uuid.uuid4())
        with self._lock:
            self._data[ref] = (username, password)
        return ref

    def get(self, ref: str) -> tuple[str, str] | None:
        with self._lock:
            return self._data.get(ref)

    def delete(self, ref: str) -> None:
        with self._lock:
            self._data.pop(ref, None)


class KeyringSecretStore:
    def __init__(self) -> None:
        import keyring

        self._keyring = keyring

    def put(self, username: str, password: str) -> str:
        ref = str(uuid.uuid4())
        payload = json.dumps({"u": username, "p": password})
        try:
            self._keyring.set_password(SERVICE, ref, payload)
        except Exception as exc:
            raise SecretStoreError(f"cofre do SO indisponível: {type(exc).__name__}") from exc
        return ref

    def get(self, ref: str) -> tuple[str, str] | None:
        try:
            raw = self._keyring.get_password(SERVICE, ref)
        except Exception as exc:
            raise SecretStoreError(f"cofre do SO indisponível: {type(exc).__name__}") from exc
        if raw is None:
            return None
        data = json.loads(raw)
        return str(data["u"]), str(data["p"])

    def delete(self, ref: str) -> None:
        import keyring.errors

        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            self._keyring.delete_password(SERVICE, ref)


def default_secret_store() -> SecretStore:
    if os.environ.get("SENTINEL_SECRET_BACKEND") == "memory":
        return MemorySecretStore()
    return KeyringSecretStore()
