"""The resolution of a scenario: the step cap of its numerical segments (docs/language.md §2.2,
docs/engine.md).

A scenario without the line keeps the engine's cap of 1 h, and its structure, its settings and its
model hash stay as they were. A scenario with `resolution D` has a cap of D, its timescales can only
shorten it, and `NumericalSettings.max_step` scales D. The cap is the interval at which the engine
reads a segment; the solver takes longer steps where its control of the error allows them, and a
timescale limits those steps. Logistic growth has a closed form,
x(t) = K / (1 + (K / x0 - 1) exp(-r t)), so a long run is checked against it.
"""

from __future__ import annotations

import math

import pytest

import napkin.engine.continuous.integrate as integrate
from napkin.engine.runtime import NumericalSettings
from napkin.model.language import parse
from napkin.model.language.evidence import identity
from tests.build import edit, flow, member, parameter, rejected, resolved, run, stock, system, with_horizon

YEAR_H = 8760.0
HORIZON = 20 * YEAR_H  # twenty years of hours
X0, CAPACITY = 10.0, 1000.0  # people at the start, and the most that the population reaches
GROWTH = 0.5 / YEAR_H  # per hour: half a year's growth rate


def logistic(*members):
    return system(
        parameter('r', GROWTH, 'per_h', 1e-6, 1e-3, doc='Growth rate'),
        parameter('cap', CAPACITY, 'people', 100, 10000, doc='Capacity'),
        parameter('tau', 2000, 'h', 1, 100000, doc='A time scale'),
        stock('x', X0, 'people', size=CAPACITY, doc='Population'),
        flow('grow', '-> x', 'r * x'),
        flow('crowd', 'x ->', 'r * x * x / cap'),
        *members,
        horizon=HORIZON,
    )


def with_line(text, line):
    return edit(text, member('scenario:', line))


def closed_form(t):
    return CAPACITY / (1 + (CAPACITY / X0 - 1) * math.exp(-GROWTH * t))


def test_a_coarse_resolution_follows_the_closed_form_over_twenty_years():
    _, trajectory = run(with_line(logistic(), 'resolution 30 days'))
    assert trajectory.settings['max_step'] == 720
    assert trajectory.settings['scenario_resolution_h'] == 720
    segments = trajectory.settings['integration_segments']
    assert segments and all(segment['max_step_h'] == 720 for segment in segments)
    for years in (1, 5, 10, 15, 20):
        t = years * YEAR_H
        assert trajectory.env_at(t)['s.x'] == pytest.approx(closed_form(t), rel=1e-7)


def test_a_timescale_still_shortens_the_step_of_a_scenario_with_a_resolution():
    text = with_line(with_line(logistic(), 'resolution 30 days'), 'timescales s.tau')
    _, trajectory = run(text)
    assert trajectory.settings['max_step'] == 2000 / 8


def solver_steps(monkeypatch, text, **options):
    """(the trajectory of a run, the lengths of the steps of its solver)."""
    lengths = []
    original = integrate.radau

    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        lengths.extend(float(b - a) for a, b in zip(result.t, result.t[1:]))
        return result

    monkeypatch.setattr(integrate, 'radau', counted)
    _, trajectory = run(text, **options)
    return trajectory, lengths


def test_the_cap_is_the_interval_of_the_checks_and_not_the_longest_step_of_the_solver(monkeypatch):
    """A scenario with no resolution has a cap of 1 h. Over twenty years of slow growth the solver
    takes steps of many hours where its own control of the error allows them: far fewer steps than
    the hours of the run. The settings give the cap as before, and the run follows the closed form
    at the ends of the years and between them."""
    trajectory, lengths = solver_steps(monkeypatch, logistic())
    assert trajectory.settings['max_step'] == 1
    assert all(segment['max_step_h'] == 1 for segment in trajectory.settings['integration_segments'])
    assert max(lengths) > 100 and len(lengths) < HORIZON / 20
    for years in (0.37, 1, 4.5, 5, 10, 13.21, 15, 20):
        t = years * YEAR_H
        assert trajectory.env_at(t)['s.x'] == pytest.approx(closed_form(t), rel=1e-8)


def test_a_timescale_limits_the_steps_of_the_solver(monkeypatch):
    """A timescale is what the scenario says of its fastest change: the solver takes eight steps or
    more in each. With `timescales s.tau` (2,000 h) no step is longer than 250 h, and with no
    timescale some are."""
    _, free = solver_steps(monkeypatch, with_line(logistic(), 'resolution 30 days'))
    monkeypatch.undo()
    text = with_line(with_line(logistic(), 'resolution 30 days'), 'timescales s.tau')
    trajectory, limited = solver_steps(monkeypatch, text)
    assert trajectory.settings['max_step'] == 250
    assert max(limited) <= 250 * (1 + 1e-12) < max(free)


def test_the_settings_step_scales_the_resolution():
    text = with_line(logistic(), 'resolution 30 days')
    _, trajectory = run(text, settings=NumericalSettings(max_step=0.5))
    assert trajectory.settings['max_step'] == 360


def test_a_scenario_without_the_line_keeps_its_structure_settings_and_identity():
    text = logistic()
    assert resolved(text).time.resolution is None
    _, trajectory = run(with_short(text))
    assert 'scenario_resolution_h' not in trajectory.settings
    assert trajectory.settings['max_step'] == 1.0
    scenario = identity(parse.parse(text))[1]['scenario'][1]
    assert 'resolution' not in scenario
    # The line is model content: two resolutions give two identities.
    coarse = identity(parse.parse(with_line(text, 'resolution 30 days')))
    fine = identity(parse.parse(with_line(text, 'resolution 10 days')))
    assert coarse != fine


def with_short(text):
    """The same model for 10 h, so that a run at the 1 h step stays short."""
    return with_horizon(text, 10)


@pytest.mark.parametrize(
    'line',
    ['resolution 0 h', 'resolution 2 people', 'resolution s.tau', f'resolution {HORIZON + 1} h'],
)
def test_a_resolution_that_is_not_a_time_within_the_horizon_is_rejected_at_its_line(line):
    assert rejected(with_line(logistic(), line)) == {('structure', 'scenario:/resolution:')}


@pytest.mark.parametrize('under', ['', '        "A text"\n'])
def test_a_resolution_line_has_its_time_and_nothing_under_it(under):
    written = 'resolution' if not under else 'resolution 30 days'
    text = with_line(logistic(), written).replace(f'    {written}\n', f'    {written}\n{under}')
    assert {code for code, _ in rejected(text)} == {'syntax'}
