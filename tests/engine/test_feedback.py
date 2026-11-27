"""The report-only feedback check finds positive circuits of switch choices and clears the others
(`napkin.engine.feedback`). The fixtures are checked against the engine's own outcomes in the G6
report: two hold for TWO, one for each ONE_*, none for NEGATIVE."""

import pytest

from napkin.engine import feedback
from napkin.engine.timeline import Plan
from napkin.model.compile import compile_text

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def pair(fill_a, drain_a, fill_b, drain_b, title):
    return f"""scenario "{title}"
    horizon 1 h
yard:
    a: L = 1 L in [0,]
    b: L = 1 L in [0,]
    flow fill_a: SOURCE -> this.a
        request = formula({fill_a})
    flow drain_a: this.a -> SINK
        request = formula({drain_a})
    flow fill_b: SOURCE -> this.b
        request = formula({fill_b})
    flow drain_b: this.b -> SINK
        request = formula({drain_b})
"""


# A rises while B is below its mark, and B rises while A is below its mark: at both marks,
# "A rises, B falls" and "A falls, B rises" both hold.
TWO = pair(
    '1 L/h if this.b < 1 L else 0 L/h',
    '0 L/h if this.b < 1 L else 1 L/h',
    '1 L/h if this.a < 1 L else 0 L/h',
    '0 L/h if this.a < 1 L else 1 L/h',
    'Two answers',
)
# B rises whatever A does (faster while A is above its mark); A rises while B is above its mark.
# One outcome holds: both rise. Every influence is positive, so a check on signs alone flags it.
ONE_POSITIVE = pair(
    '1 L/h if this.b > 1 L else 0 L/h',
    '0.5 L/h',
    '2 L/h if this.a > 1 L else 1 L/h',
    '0.5 L/h',
    'One answer, positive circuit',
)
# A rises while B is above its mark, B rises while A is below its mark: a negative circuit.
NEGATIVE = pair(
    '1 L/h if this.b > 1 L else 0 L/h',
    '0 L/h if this.b > 1 L else 1 L/h',
    '1 L/h if this.a < 1 L else 0 L/h',
    '0 L/h if this.a < 1 L else 1 L/h',
    'Negative circuit',
)
FULL = """scenario "The tank is full"
    horizon 2 h
yard:
    tank: L = 0 L in [0,]
    flow fill: SOURCE -> this.tank
        request = formula(1 L/h if this.tank < 1 L else 0 L/h)
    flow use: this.tank -> SINK
        request = 0.25 L/h
"""

# As ONE_POSITIVE, but B fills from a large store instead of an unlimited source: its rate is not
# known to stay above its drain without a run, so the check cannot clear the positive circuit.
ONE_POSITIVE_STORE = """scenario "One answer, a rate the compiler cannot bound"
    horizon 1 h
yard:
    a: L = 1 L in [0,]
    b: L = 1 L in [0,]
    reserve: L = 100 L in [0,]
    flow fill_a: SOURCE -> this.a
        request = formula(1 L/h if this.b > 1 L else 0 L/h)
    flow drain_a: this.a -> SINK
        request = formula(0.5 L/h)
    flow fill_b: this.reserve -> this.b
        request = formula(2 L/h if this.a > 1 L else 1 L/h)
    flow drain_b: this.b -> SINK
        request = formula(0.5 L/h)
"""


@pytest.mark.parametrize(
    'source, verdict',
    [
        (TWO, 'positive feedback'),
        (ONE_POSITIVE, 'a direction that the rates decide'),
        (ONE_POSITIVE_STORE, 'positive feedback'),  # one outcome at run time: a conservative flag
        (NEGATIVE, 'every circuit is negative'),
        (FULL, 'every circuit is negative'),
    ],
    ids=['two-answers', 'one-answer-bounded', 'one-answer-unbounded', 'negative', 'tank-full'],
)
def test_a_circuit_is_flagged_only_when_its_signs_can_keep_a_choice(source, verdict):
    model = compile_text(source, UNITS)
    report = feedback.check(Plan.of(model.program, model.configuration))
    reasons = [reason for _, _, reason in report.flagged] + [reason for _, reason in report.cleared]
    assert len(reasons) == 1 and reasons[0].startswith(verdict)
    if report.flagged:
        ((_, (path, _, _), _),) = report.flagged
        assert len(path) > 1 and path[0] == path[-1]
