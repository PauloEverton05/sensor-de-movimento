"""Máquina de estados da vigilância (docs/ARQUITETURA.md §6)."""

from __future__ import annotations

from enum import StrEnum


class SurveillanceState(StrEnum):
    """Estado observado: o que o agente verifica que está acontecendo."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class DesiredState(StrEnum):
    """Intenção do usuário. Persistida separadamente do estado observado."""

    STOPPED = "STOPPED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


_S = SurveillanceState

ALLOWED_TRANSITIONS: dict[SurveillanceState, frozenset[SurveillanceState]] = {
    _S.STOPPED: frozenset({_S.STARTING}),
    # STARTING → STOPPING: o usuário pode cancelar durante a inicialização.
    _S.STARTING: frozenset({_S.ACTIVE, _S.ERROR, _S.STOPPING}),
    _S.ACTIVE: frozenset({_S.PAUSED, _S.ERROR, _S.STOPPING}),
    # Retomar uma pausa volta a abrir as câmeras, por isso passa por STARTING.
    _S.PAUSED: frozenset({_S.STARTING, _S.STOPPING}),
    # ERROR = vigilância pedida, mas nenhuma câmera gravando; volta a ACTIVE na recuperação.
    _S.ERROR: frozenset({_S.ACTIVE, _S.STOPPING}),
    _S.STOPPING: frozenset({_S.STOPPED}),
}

# Estados em que fechar a interface exige o diálogo de confirmação (§6.4).
REQUIRES_CLOSE_CONFIRMATION: frozenset[SurveillanceState] = frozenset(
    {_S.STARTING, _S.ACTIVE, _S.PAUSED, _S.ERROR}
)


class InvalidTransitionError(ValueError):
    def __init__(self, current: SurveillanceState, target: SurveillanceState) -> None:
        super().__init__(f"transição inválida: {current} → {target}")
        self.current = current
        self.target = target


def can_transition(current: SurveillanceState, target: SurveillanceState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: SurveillanceState, target: SurveillanceState) -> SurveillanceState:
    """Valida e devolve o novo estado; levanta InvalidTransitionError se proibido."""
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target
