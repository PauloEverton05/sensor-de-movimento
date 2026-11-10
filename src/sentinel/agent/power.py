"""Inibição de sono enquanto a captura está ativa (docs/ARQUITETURA.md §12).

Windows: Power Request API (PowerCreateRequest/PowerSetRequest). Visível para o
usuário em `powercfg /requests`, com o motivo "Sentinel AI: vigilância ativa".
Nada é escondido e nenhuma configuração do sistema é alterada.

Linux/macOS: implementados na Fase 8 (logind Inhibit / IOPMAssertion). Até lá
o gerenciador só informa que a inibição não está disponível.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

log = logging.getLogger(__name__)

REASON = "Sentinel AI: vigilância ativa (captura de câmera)"


class PowerManager:
    def __init__(self) -> None:
        self._handle: int | None = None
        self._display = False
        self._impl = _WindowsPower() if sys.platform == "win32" else None

    @property
    def supported(self) -> bool:
        return self._impl is not None

    def acquire(self, *, keep_display_on: bool = False) -> bool:
        if self._impl is None:
            log.warning("inibição de sono ainda não implementada nesta plataforma")
            return False
        if self._handle is not None:
            self.release()
        self._handle = self._impl.acquire(REASON, keep_display_on)
        self._display = keep_display_on
        log.info("inibição de sono ativa", extra={"keep_display_on": keep_display_on})
        return True

    def release(self) -> None:
        if self._impl is not None and self._handle is not None:
            self._impl.release(self._handle, self._display)
            log.info("inibição de sono liberada")
        self._handle = None
        self._display = False

    def status(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "active": self._handle is not None,
            "keep_display_on": self._display,
        }


class _WindowsPower:
    # POWER_REQUEST_TYPE
    DISPLAY_REQUIRED = 0
    SYSTEM_REQUIRED = 1
    EXECUTION_REQUIRED = 3
    POWER_REQUEST_CONTEXT_VERSION = 0
    POWER_REQUEST_CONTEXT_SIMPLE_STRING = 0x1

    def __init__(self) -> None:
        assert sys.platform == "win32"  # também orienta o mypy nas outras plataformas
        import ctypes
        from ctypes import wintypes

        class _Reason(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("Flags", wintypes.DWORD),
                ("SimpleReasonString", wintypes.LPWSTR),
            ]

        self._ctypes = ctypes
        self._Reason = _Reason
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
        k32.PowerCreateRequest.argtypes = [ctypes.POINTER(_Reason)]
        k32.PowerCreateRequest.restype = wintypes.HANDLE
        k32.PowerSetRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k32.PowerSetRequest.restype = wintypes.BOOL
        k32.PowerClearRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k32.PowerClearRequest.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        self._k32 = k32
        self._reason_buf: Any = None

    def acquire(self, reason: str, keep_display_on: bool) -> int:
        ctypes = self._ctypes
        self._reason_buf = ctypes.create_unicode_buffer(reason)
        ctx = self._Reason(
            self.POWER_REQUEST_CONTEXT_VERSION,
            self.POWER_REQUEST_CONTEXT_SIMPLE_STRING,
            ctypes.cast(self._reason_buf, ctypes.c_wchar_p),
        )
        handle = self._k32.PowerCreateRequest(ctypes.byref(ctx))
        if not handle or handle == -1:
            raise OSError(ctypes.get_last_error(), "PowerCreateRequest falhou")
        types = [self.SYSTEM_REQUIRED, self.EXECUTION_REQUIRED]
        if keep_display_on:
            types.append(self.DISPLAY_REQUIRED)
        for t in types:
            if not self._k32.PowerSetRequest(handle, t):
                log.warning(
                    "PowerSetRequest falhou", extra={"type": t, "err": ctypes.get_last_error()}
                )
        return int(handle)

    def release(self, handle: int, display: bool) -> None:
        types = [self.SYSTEM_REQUIRED, self.EXECUTION_REQUIRED]
        if display:
            types.append(self.DISPLAY_REQUIRED)
        for t in types:
            self._k32.PowerClearRequest(handle, t)
        self._k32.CloseHandle(handle)
        self._reason_buf = None
