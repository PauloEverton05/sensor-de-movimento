"""Detecção do estado da sessão do usuário (tela bloqueada), só para diagnóstico.

Windows: se a área de trabalho de entrada não pode ser aberta/ativada, a sessão
está bloqueada (ou a área de trabalho segura do UAC está ativa). Nas demais
plataformas devolve None (desconhecido); entra na Fase 8.
"""

from __future__ import annotations

import sys


def is_session_locked() -> bool | None:
    if sys.platform != "win32":
        return None
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    desktop_switchdesktop = 0x0100
    handle = user32.OpenInputDesktop(0, False, desktop_switchdesktop)
    if not handle:
        return True
    try:
        return not bool(user32.SwitchDesktop(handle))
    finally:
        user32.CloseDesktop(handle)
