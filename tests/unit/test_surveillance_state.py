import itertools

import pytest

from sentinel.domain.surveillance import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    SurveillanceState,
    can_transition,
    transition,
)

S = SurveillanceState


def test_all_states_have_transition_entry() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(SurveillanceState)


def test_required_states_exist() -> None:
    assert {s.value for s in S} == {"STOPPED", "STARTING", "ACTIVE", "PAUSED", "STOPPING", "ERROR"}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.STOPPED, S.STARTING),
        (S.STARTING, S.ACTIVE),
        (S.STARTING, S.ERROR),
        (S.ACTIVE, S.PAUSED),
        (S.PAUSED, S.STARTING),
        (S.ACTIVE, S.ERROR),
        (S.ERROR, S.ACTIVE),
        (S.ACTIVE, S.STOPPING),
        (S.STOPPING, S.STOPPED),
    ],
)
def test_valid_transitions(current: SurveillanceState, target: SurveillanceState) -> None:
    assert transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.STOPPED, S.ACTIVE),  # nunca ACTIVE sem passar por STARTING (1º frame gravado)
        (S.STOPPED, S.STOPPING),
        (S.ACTIVE, S.STOPPED),  # parar sempre finaliza segmentos em STOPPING
        (S.ERROR, S.STOPPED),
        (S.PAUSED, S.ACTIVE),
        (S.STOPPING, S.ACTIVE),
    ],
)
def test_invalid_transitions(current: SurveillanceState, target: SurveillanceState) -> None:
    with pytest.raises(InvalidTransitionError):
        transition(current, target)


def test_every_non_stopped_state_can_reach_stopped() -> None:
    """Nenhum estado pode prender o usuário: sempre existe caminho até STOPPED."""
    for start in S:
        seen = {start}
        frontier = [start]
        while frontier:
            nxt = [t for s in frontier for t in ALLOWED_TRANSITIONS[s] if t not in seen]
            seen.update(nxt)
            frontier = nxt
        assert S.STOPPED in seen or start is S.STOPPED, start


def test_no_self_transitions() -> None:
    for s, t in itertools.product(S, S):
        if s is t:
            assert not can_transition(s, t)
