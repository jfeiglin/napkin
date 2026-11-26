"""The rate guard can retry a trial, or report its unproved committed interval."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import Radau

from napkin.core import expr
from napkin.engine.continuous import rate_guard
from napkin.engine.continuous.transfers import CollocationRates, radau_amount
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.declared import MovingDeclared
from napkin.engine.timeline.rate_scope import rate_node
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.test_public_engine import compiled
from tests.engine.test_threshold_transfer_placement import use_method


def guard(node):
    model = compiled("""scenario "Clock interval"
    horizon 2 h
yard:
    water: L = 0 L
""")
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    g = rate_guard.RateGuard(run, {}, {}, None)
    g.rates.append(('input', node, (0,)))
    return g


class Entries:
    def __init__(self):
        self.rows = []

    def entry(self, at, kind, name, **details):
        self.rows.append((at, kind, name, details))


def test_a_retried_trial_keeps_accepted_collocation_transfers_and_all_solver_work():
    g = guard(expr.read('t ** 3'))
    # Make a trial with a simple field so Radau accepts a long step itself.
    evaluations = []

    def field(t, y):
        evaluations.append(t)
        return np.array([1.0])

    solver = Radau(field, 0, [0.0], 1.0, first_step=1.0, rtol=1e-9, atol=np.array([1e-10]))
    capture = CollocationRates(solver, lambda: np.array([evaluations[-1] ** 2]))
    original_evals, original_calls = solver.nfev, len(evaluations)
    rate_guard.step(solver, g)
    dense = solver.dense_output()
    assert dense.t < 0.1
    assert solver.nfev > original_evals + 3
    assert solver.nfev - original_evals == len(evaluations) - original_calls
    capture.finish(dense)
    assert radau_amount(dense, dense.t, None)[0] == pytest.approx(dense.t**3 / 3, rel=1e-12)
    assert not hasattr(dense, 'rate_warnings')


def test_rejecting_a_trial_with_cached_newton_factors_matches_a_clean_half_step():
    def prepared():
        solver = Radau(
            lambda t, y: -y, 0, [1.0], 1, first_step=0.02, rtol=1e-7, atol=1e-10, jac=np.array([[-1.0]])
        )
        while solver.LU_real is None:
            solver.step()
        return solver

    class RejectFirst:
        span = None

        def check(self, solver):
            if self.span is None:
                self.span = solver.t - solver.t_old
                return None
            return []

    limited, rejected, clean = prepared(), prepared(), prepared()
    original = (limited.nfev, limited.nlu)
    guard = RejectFirst()
    rate_guard.step(limited, guard)
    rejected.step()
    clean.max_step = guard.span / 2
    clean.LU_real = clean.LU_complex = None
    clean.step()
    assert limited.t == clean.t
    for a, b in ((limited.y, clean.y), (limited.sol.Q, clean.sol.Q)):
        np.testing.assert_array_equal(a, b)
    for counter, count in zip(('nfev', 'nlu'), original, strict=True):
        assert getattr(limited, counter) == getattr(rejected, counter) + getattr(clean, counter) - count


def test_a_later_unavailable_bound_cannot_hide_an_earlier_material_interval():
    # Valid on the left half. The full estimate cannot prove a finite range to the right.
    g = guard(expr.read('exp(800*t)'))
    solver = SimpleNamespace(t_old=0.0, t=1.0, rtol=1e-9, atol=[1e-10], y=[0.0], y_old=[0.0])
    assert g.check(solver) is None
    solver.t = 0.5
    assert g.check(solver) is None


def test_a_finite_but_undecidable_opening_subdivides_to_crossing():
    # The interval prover has no branch refinement for a general membership predicate.
    g = guard(expr.read('1 if within(t, 0, 1) else 10'))
    solver = SimpleNamespace(t_old=0.0, t=1.0, rtol=1e-9, atol=[1e-10], y=[0.0], y_old=[0.0])
    assert g.check(solver) is None
    solver.t = g.crossing
    reason, allowance, mathematical, total = g.check(solver)['input']
    assert reason == 'mathematical error unresolved at the crossing tolerance'
    assert total >= mathematical > allowance


def test_mark_an_unbounded_step_only_over_the_prefix_actually_committed():
    g = guard(None)  # The guard cannot read the rate on this installation.
    solver = Radau(lambda t, y: [0.0], 0.0, [1.0], 1.0, first_step=1.0, atol=np.array([1e-10]))
    rate_guard.step(solver, g)
    dense = solver.dense_output()
    # A shorter step cannot make the rate readable: the step keeps its length, with its note.
    assert dense.t == 1.0
    entries = Entries()
    rate_guard.mark(entries, dense, 0, 0)
    assert not entries.rows
    rate_guard.mark(entries, dense, 0, dense.t / 2)
    first = entries.rows[0][3]
    assert first['start'] == 0 and first['end'] == dense.t / 2
    assert first['mathematical_bound'] is None and first['bound_with_roundoff'] is None
    rate_guard.mark(entries, dense, dense.t / 2, 2 * dense.t)  # a mark past the step ends at its end
    assert entries.rows[-1][3]['start'] == dense.t / 2 and entries.rows[-1][3]['end'] == dense.t
    assert len(entries.rows) == 2


def test_an_unresolved_rate_at_the_minimum_solver_step_keeps_the_accepted_trial():
    start = 1e8
    end = start + 1e-6
    solver = Radau(
        lambda t, y: [1.0], start, [0.0], end, first_step=end - start, rtol=1e-9, atol=np.array([1e-10])
    )
    g = guard(expr.read('1e8 * exp(-((t-100000000.0000005)/1e-7)**2)'))
    assert rate_guard.step(solver, g) is None
    step = solver.dense_output()
    assert solver.status == 'running' and step.t == start + 10 * np.spacing(start)
    assert solver.y[0] == pytest.approx(step.t - start, rel=1e-14)
    entries = Entries()
    rate_guard.mark(entries, step, start, step.t)
    [(_, _, _, details)] = entries.rows
    assert (details['start'], details['end']) == (start, step.t)
    assert 'minimum solver step' in details['reason']


def test_a_subresolution_pulse_is_marked_after_checkpoint_restore():
    model = compiled("""scenario "Unresolved pulse"
    horizon 4 h
yard:
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(100000000 L/h * exp(-((t - 2.07831415 h) / 0.000000000001 h) ** 2))
    inspect = event():
        after 1 h
yard.inspect.start()
""")
    make = lambda: Plan.of(model.program, model.configuration)  # noqa: E731
    live = Run(make(), (Breakpoint('yard.inspect.step[0]'),))
    held = live.run()
    assert isinstance(held, Checkpoint)
    assert not tuple(held.record.entries('rate_unresolved'))
    for record in (live.resume(), Run.restored(make(), loads(dumps(held))).resume()):
        assert record.failure is None and record.end == 4
        output = tuple(record.entries('rate_unresolved'))
        assert any(e.detail('start') <= 2.07831415 <= e.detail('end') for e in output)
        assert all(e.detail('end') <= e.t and e.part == 'yard.fill.request' for e in output)


def test_outward_bounds_enclose_small_log1p_and_expm1():
    g = guard(None)
    import math

    for name in ('log1p', 'expm1'):
        lower, upper = g.prove.over({'t': (1e-17, 2e-17)})(expr.read(f'{name}(t)'))
        fn = getattr(math, name)
        assert lower <= fn(1e-17) <= fn(2e-17) <= upper


def test_a_pulse_due_to_roundoff_marks_the_accepted_step():
    # In real arithmetic the inflow is constant. Its floating evaluation
    # gives 16,384 extra units/h on (8191, 8192), between the stage nodes.
    g = guard(expr.read('1e15 + (((1e20 + (t + 1)) - 1e20) - ((1e20 + t) - 1e20))'))

    def net(t, _y):
        return [1e15 + (((1e20 + (t + 1)) - 1e20) - ((1e20 + t) - 1e20)) - 1e15]

    assert net(8191.5, None) == [16384]
    solver = Radau(net, 0, [0.0], 20000, first_step=20000, rtol=1e-9, atol=np.array([1e-10]))
    rate_guard.step(solver, g)
    assert solver.t == 20000 and solver.y[0] == 0
    entries = Entries()
    rate_guard.mark(entries, solver.dense_output(), 0, 20000)
    [(_, _, _, details)] = entries.rows
    assert details['reason'] == 'roundoff prevents certification'
    assert details['mathematical_bound'] <= details['tolerance'] < details['bound_with_roundoff']
    assert details['start'] == 0 and details['end'] == 20000


@pytest.mark.parametrize('method', ('sparse', 'component', 'moving_declared'))
def test_a_large_affine_through_flow_marks_roundoff_at_an_empty_store(method, monkeypatch):
    model = use_method(
        """scenario "An affine rate through an empty store"
    horizon 4 h
yard:
    water: L = 0 L in [0 L, 10 L] scale 1 L
    used: L = 0 L
    flow fill: SOURCE -> this.water
        request = formula(10000000 L/h * (1 + t / (100 h)))
        capacity = formula(10000000 L/h * (1 + t / (100 h)))
    flow drain: this.water -> this.used
        request = 20000000 L/h
""",
        method,
        monkeypatch,
        'fill',
    )
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None and record.end == 4
    assert record.history(Key('yard', ('water',))).at(4) == 0
    assert record.history(Key('yard', ('used',))).at(4) == pytest.approx(40_800_000, rel=1e-9)
    marks = tuple(record.entries('rate_unresolved', 'yard.fill.request'))
    assert marks and any(e.detail('end') - e.detail('start') > 1 for e in marks)
    for entry in marks:
        assert entry.detail('reason') == 'roundoff prevents certification'
        assert (
            entry.detail('mathematical_bound')
            <= entry.detail('tolerance')
            < entry.detail('bound_with_roundoff')
        )


def test_a_time_test_keeps_a_named_inputs_comparison_scale():
    model = compiled("""scenario "A time threshold inside its declared band"
    horizon 3 h
yard:
    input threshold: h = 1 h scale 1000000000 h
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(10 L/h if t <= this.threshold else 0 L/h)
""")
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    name = 'yard.fill.request'
    guard = rate_guard.RateGuard(run, {name: ('yard.water',)}, {'yard.water': 0}, rate_node)
    _, node, _ = guard.rates[0]
    condition = run.plan.values[name].node.test
    band = run.plan.units.comparisons.band(*condition.operands, 1, 1)
    edge = 1 + band

    def bounds(lo, hi):
        return guard.prove.over({**guard.fixed, 't': (lo, hi)})(node)

    # The named scale extends the inclusive branch to its band edge. The
    # cell just below it must use 10. The straddling cell must contain both.
    assert bounds(edge - 0.2 * band, edge - 0.1 * band) == pytest.approx((10, 10))
    low, high = bounds(edge - 0.1 * band, edge + 0.1 * band)
    assert low <= 0 and high >= 10


def test_outward_sum_bounds_hold_through_cancellation():
    g = guard(None)
    # The left-to-right floating sum loses both small addends. Its exact
    # mathematical sum, used in the derivative remainder, is two.
    lo, hi = g.prove(expr.read('sum(1e20, 1, 1, -1e20)'))
    assert lo <= 0 < 2 <= hi


@pytest.mark.parametrize(
    'test', ('this.valve == RUN and t <= 1 h', 'this.valve == OFF or t <= 1 h', 't <= 1 h and t < 2 h')
)
def test_a_time_window_proves_both_constant_sides_of_a_compound_test(test):
    model = compiled(f"""scenario "A clock window"
    horizon 2 h
yard:
    input valve: enum[RUN, OFF] = RUN
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(10 L/h if {test} else 0 L/h)
""")
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    name = 'yard.fill.request'
    g = rate_guard.RateGuard(run, {name: ('yard.water',)}, {'yard.water': 0}, rate_node)
    _, node, _ = g.rates[0]
    for lo, hi, expected in [(0, 0.1, 10), (1.2, 1.3, 0)]:
        assert g.prove.over({**g.fixed, 't': (lo, hi)})(node) == pytest.approx((expected, expected))
        mathematical, total = g._bounds(node, lo, hi, 1e-10)
        assert mathematical <= total < 1e-10
    record = run.run()
    assert record.failure is None and record.end == 2


@pytest.mark.parametrize(
    ('method', 'reinstall'),
    [('sparse', True), ('component', True), ('moving_declared', True), ('sparse', False)],
)
def test_a_pulse_on_the_selected_clock_arm_inside_its_band(method, reinstall, monkeypatch):
    import math

    # A narrower band also puts the start outside it. The clock contact then
    # selects the outgoing arm on the existing way, without a definition change.
    center, scale = (1.5, 1e9) if reinstall else (1.05, 1e8)
    rate = f'formula(0 L/h if t <= this.edge else 10 L/h * exp(-((t - {center} h) / 0.00001 h) ** 2))'
    change = (
        f"""    change = event():
        after 1.2 h:
            this.fill.request = {rate}
yard.change.start()
"""
        if reinstall
        else ''
    )
    model = use_method(
        f"""scenario "The outgoing clock arm"
    horizon 2 h
yard:
    input edge: h = 1 h scale {scale} h
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = {rate}
{change}""",
        method,
        monkeypatch,
        'fill',
    )
    key = Key('yard', ('water',))
    request = replace(model.configuration.request, everything=False, keys=(key,))
    run = Run(Plan.of(model.program, replace(model.configuration, request=request)))
    record = run.run()
    assert record.failure is None
    expected = 1e-4 * math.sqrt(math.pi)
    assert record.history(key).at(record.end) == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize('method', ('sparse', 'component', 'moving_declared'))
@pytest.mark.parametrize('curved', (False, True))
def test_two_close_clock_edges_or_a_curved_time_test_can_enclose_a_pulse(method, curved, monkeypatch):
    window = '((t - 1.25006 h) / (1 h)) ** 2 < 0.0000000025' if curved else 't > 1.25001 h and t < 1.25011 h'
    model = use_method(
        f"""scenario "A short window"
    horizon 2 h
yard:
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(10 L/h if {window} else 0 L/h)
""",
        method,
        monkeypatch,
        'fill',
    )
    key = Key('yard', ('water',))
    request = replace(model.configuration.request, everything=False, keys=(key,))
    record = Run(Plan.of(model.program, replace(model.configuration, request=request))).run()
    assert record.failure is None
    assert record.history(key).at(2) == pytest.approx(0.001, abs=1e-10)


def test_clock_edges_within_crossing_share_one_declared_contact_batch(monkeypatch):
    model = use_method(
        """scenario "One clock batch"
    horizon 2 h
yard:
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(10 L/h if t > 1.25001 h and t < 1.250010005 h else 0 L/h)
""",
        'moving_declared',
        monkeypatch,
        'fill',
    )
    batches = []
    settle = MovingDeclared._settle

    def capture(way, t, contacts=(), departing=()):
        if contacts:
            batches.append((t, sorted(contacts.values())))
        return settle(way, t, contacts, departing)

    monkeypatch.setattr(MovingDeclared, '_settle', capture)
    run = Run(Plan.of(model.program, model.configuration))
    assert run.run().failure is None
    assert batches == [(1.25001, [1.25001, 1.250010005])]
    assert run.value('yard.water') == 0


@pytest.mark.parametrize(
    'condition',
    (
        't != this.narrow and t == this.wide',
        'this.wide == t and this.narrow != t',
        'not (this.narrow == t or this.wide != t)',
    ),
)
def test_a_time_inside_a_wide_zero_band_can_still_be_outside_a_narrow_one(condition):
    import math

    model = compiled(f"""scenario "An impulse between two zero bands"
    horizon 1 h
yard:
    input narrow: h = 0 h scale 1 h
    input wide: h = 0 h scale 1000000000 h
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula(10 L/h * exp(-((t - 0.5 h) / 0.00001 h) ** 2) if {condition} else 0 L/h)
""")
    key = Key('yard', ('water',))
    request = replace(model.configuration.request, everything=False, keys=(key,))
    run = Run(Plan.of(model.program, replace(model.configuration, request=request)))
    record = run.run()
    assert record.failure is None
    assert record.history(key).at(1) == pytest.approx(1e-4 * math.sqrt(math.pi), abs=1e-10)


def test_a_rate_the_guard_cannot_read_gives_a_note_and_does_not_stop_the_run():
    # The untaken branch divides by zero. Before, the guard shortened the step until the run stopped.
    model = compiled("""scenario "An untaken branch that divides by zero"
    horizon 0.01 h
tank:
    input k = 0 in [0,]
    level: L = 0 L
    flow fill: SOURCE -> this.level
        request = formula(10 L/h * exp(-t / (1 h)) if (t / (1 h)) ** 2 < 1000 else 10 L/h / this.k)
""")
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None
    marks = [entry for entry in record.trace if entry.kind == 'rate_unresolved']
    assert marks and all(entry.detail('reason') == 'the guard cannot read this rate' for entry in marks)


@pytest.mark.parametrize(
    ('kinked', 'spelled', 'total'),
    (
        ('abs(t - 5 h)', 'max(t - 5 h, 5 h - t)', 25),
        ('max(t - 5 h, 5 h - t, 0 h)', 'max(t - 5 h, 5 h - t)', 25),
        ('clip(t - 5 h, 0 h, 2 h)', 'min(max(t - 5 h, 0 h), 2 h)', 8),
    ),
)
def test_a_kink_costs_the_guard_what_its_two_argument_spelling_costs(kinked, spelled, total, monkeypatch):
    # Each operation with kinks becomes its piece on a cell (`ops.Operation.active`).
    checks = []
    check = rate_guard.RateGuard.check

    def counted(self, solver):
        checks.append(solver.t)
        return check(self, solver)

    monkeypatch.setattr(rate_guard.RateGuard, 'check', counted)
    counts = []
    for rate in (spelled, kinked):
        model = compiled(f"""scenario "A kink at hour 5"
    horizon 10 h
yard:
    water: L = 0 L scale 1 L
    flow fill: SOURCE -> this.water
        request = formula({rate} * 1 L/h/h)
""")
        checks.clear()
        record = Run(Plan.of(model.program, model.configuration)).run()
        assert record.failure is None
        assert record.history(Key('yard', ('water',))).at(10) == pytest.approx(total, rel=1e-9)
        counts.append(len(checks))
    assert counts[1] <= 2 * counts[0]
