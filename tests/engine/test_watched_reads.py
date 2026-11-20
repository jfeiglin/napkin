"""What a watched condition reads is classed by what it is, not by its spelling (spec.md:674: a trigger
fires when its condition first becomes true, between scheduled events, "also for a supported condition
that reads a solved value ... It never falls back to polling in silence"; G0, "Fire triggers when their
condition first becomes true": find the first crossing, or diagnose it).

A trigger, a gate and an assertion over state each find the first contact of their condition between
moments. A value that moves there is a store of a set, a rate of a flow, or a result of a declared
solver (its own unknown, or a stored number that it determines), whatever path spells it; each is read
through the way that moves it, and one whose way gives the engine no bound on its motion stops the run
by name. None is read as a line that holds through the window.

The rule test: a clinic whose staff hours drain at 10 h/h from 100 h, and a solver that gives care 0.7
of them (outreach takes at least 0.3): conditions on the store, on a formula of it, on the solver's
unknown, on a rate of the solver's set, in a trigger, a gate and an assertion. Each fires at the time
that the closed form gives, 100 - 10 t = 60 / 0.7 at t = 10/7 h (an assertion over care >= 50 h fails
at 20/7 h), or stops the run with the diagnostic that names it; never at the horizon in silence (on
2cd1751 a trigger on care fired at 4 h without a word).
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from tests.program.examples import UNITS

HEAD = """scenario "Watched reads"
    horizon 4 h

clinic:
    staff_hours: h = 100 h in [0 h,]
    flow attrition: this.staff_hours -> SINK
        request = 10 h/h
    outreach_minimum = formula(0.30 * this.staff_hours)
    care_by_formula = formula(0.7 * this.staff_hours)
    staffing = solver:
        inputs:
            available = this.staff_hours
            minimum_outreach = this.outreach_minimum
        solve_for:
            care: h in [0 h, available]
            outreach: h in [minimum_outreach, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
    fired_at: h = -1 h
"""
TRIGGER = """    alarm = event():
        when {condition}:
            this.alarm.start()
            reset when false
        after 0 h:
            this.fired_at = t
"""
GATE = """    wait = event():
        until {condition}
        after 0 h:
            this.fired_at = t

clinic.wait.start()
"""
ASSERT = """    assert {condition}
"""
CERTIFY = 'cannot be certified'
CONDITIONS = {  # the condition, and when it first holds
    'the store': ('this.staff_hours * 7 <= 600 h', 10 / 7),
    'a formula of the store': ('this.care_by_formula <= 60 h', 10 / 7),
    "the solver's unknown": ('this.staffing.care <= 60 h', 10 / 7),
    'a rate of the moving set': ('this.attrition.actual_rate <= 5 h/h', None),
}


def outcome(text):
    compiled = compile_text(text, UNITS)
    record = run(compiled.program, compiled.configuration)
    return compiled, record


@pytest.mark.parametrize('form', ['trigger', 'gate'])
@pytest.mark.parametrize('what', sorted(CONDITIONS))
def test_a_watched_condition_fires_at_its_first_contact_or_names_what_it_cannot_certify(form, what):
    condition, first = CONDITIONS[what]
    compiled, record = outcome(HEAD + (TRIGGER if form == 'trigger' else GATE).format(condition=condition))
    if record.failure is not None:
        message = record.failure.detail('message')
        assert CERTIFY in message, message
        assert first is None or what == "the solver's unknown", (what, message)
        return
    (at,) = read(record, compiled.program, ['clinic.fired_at'], [4])[0].values
    assert first is not None, (what, at)
    assert at == pytest.approx(first, abs=1e-7), (what, at)


@pytest.mark.parametrize(
    'condition',
    ['this.staff_hours * 7 >= 300 h', 'this.care_by_formula >= 30 h', 'this.staffing.care >= 30 h'],
)
def test_an_assertion_fails_where_it_first_stops_holding_or_names_what_it_cannot_certify(condition):
    """`care >= 30 h` stops holding where 0.7 (100 - 10 t) = 30, at t = 40/7 h: past the horizon of 4 h
    the assertion holds throughout; with care at 50 h, at 20/7 h it fails, or the run names what it
    cannot certify."""
    _, record = outcome(HEAD + ASSERT.format(condition=condition))
    assert record.failure is None or CERTIFY in record.failure.detail('message')
    stricter = condition.replace('>= 300 h', '>= 500 h').replace('>= 30 h', '>= 50 h')
    _, record = outcome(HEAD + ASSERT.format(condition=stricter))
    assert record.failure is not None
    message = record.failure.detail('message')
    if CERTIFY not in message:
        assert record.failure.t == pytest.approx(20 / 7, abs=1e-7), (stricter, record.failure.t, message)
