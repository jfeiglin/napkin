"""Change 29: a comparison's band belongs to the quantities it compares."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    Builder,
    after,
    assign,
    event,
    formula,
    named,
    q,
    start,
    this,
    value,
    within,
)
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.engine.test_solver_memberships import plant
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'mL': ({'volume': 1}, Fraction(1, 1000))}


def values(program, configuration, names, reader):
    keys = [Key('tank', (name,)) for name in names]
    if reader == 'reference':
        oracle, failure = run_of(program, configuration)
        assert failure is None
        return [value_at(oracle, program, key, 1) for key in keys]
    record = run(program, configuration)
    assert record.failure is None
    return [v.values[0] for v in read(record, program, keys, [1])]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_declared_scales_govern_a_comparison_in_both_orders(reader):
    """A 1e-12 L signal differs from literal zero by a billion of its own bands.
    A separately declared coarse peer has a 1e-9 L band. The finer fallback for
    an unscaled mL value is 1e-12 L. An alias keeps its target's scale."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('signal', 'L', 1e-12, scale=1e-12),
        value('alias', 'L', formula(this.signal)),
        value('coarse', 'L', 0),
        value('drop', 'mL', 5e-8),
        value('fine', BOOL, formula(this.signal == q(0, 'L'))),
        value('backwards', BOOL, formula(q(0, 'L') == this.alias)),
        value('peers', BOOL, formula(this.signal == this.coarse)),
        value('reverse_peers', BOOL, formula(this.coarse == this.signal)),
        value('millilitres', BOOL, formula(this.drop == q(0, 'L'))),
        value('flag', '', 0),
        event('check', after(q(1, 'h'), assign(this.flag, 1), when=this.signal <= this.coarse)),
    )
    b.setup(start(named('tank').check))
    names = ['fine', 'backwards', 'peers', 'reverse_peers', 'millilitres', 'flag']
    assert values(b.finish(), Configuration(Request(1)), names, reader) == [
        False,
        False,
        True,
        True,
        False,
        1,
    ]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
@pytest.mark.parametrize(('precision', 'equal'), [(1e-9, False), (1e-6, True)])
def test_a_configured_band_applies_to_formulas_and_guards(reader, precision, equal):
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('level', 'L', 1.0000005),
        value('flag', '', 0),
        value('answer', BOOL, formula(this.level <= q(1, 'L'))),
        event('check', after(q(1, 'h'), assign(this.flag, 1), when=this.answer)),
    )
    b.setup(start(named('tank').check))
    cfg = Configuration(Request(1), numerics=Numerics(rtol=precision))
    assert values(b.finish(), cfg, ['answer', 'flag'], reader) == [equal, int(equal)]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_membership_whose_ends_compare_equal_is_valid(reader):
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('lo', 'L', 0.30000000005),
        value('hi', 'L', 0.3),
        value('accepted', BOOL, formula(within(q(0.3, 'L'), this.lo, this.hi))),
    )
    assert values(b.finish(), Configuration(Request(1)), ['accepted'], reader) == [True]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_an_in_band_inverted_solver_interval_has_one_admissible_point(reader):
    """The midpoint of the two known ends is 0.300000000025 L/h."""
    p = plant(0.30000000005, 0.3)
    config = Configuration(Request(1))
    rate = Key('clinic', ('use', 'actual_rate'))
    if reader == 'reference':
        oracle, failed = run_of(p, config)
        assert failed is None
        found = value_at(oracle, p, rate, 1)
    else:
        record = run(p, config)
        assert record.failure is None
        found = read(record, p, [rate], [1])[0].values[0]
    assert float(found) == pytest.approx(0.300000000025, abs=1e-13)


def test_compilation_accepts_constant_interval_ends_within_the_band():
    from napkin.model.compile import compile_text
    from tests.program.examples import UNITS as units

    model = compile_text(
        """scenario "Near interval"
    horizon 1 h

tank:
    level: L = 0.3 L
    ready = formula(this.level in [0.30000000005 L, 0.3 L])
""",
        units,
    )
    assert values(model.program, model.configuration, ['ready'], 'engine') == [True]


@pytest.mark.deep
@pytest.mark.parametrize('reader', ['engine', 'reference'])
@pytest.mark.parametrize('magnitude', ['0.001', '0.3', '1', '1000', '1000000000'])
def test_each_relation_at_its_own_scale(magnitude, reader):
    at = Fraction(magnitude)
    gap = at * Fraction(1, 10**9)
    for multiplier in (0, Fraction(1, 4), 4, -4):
        delta = multiplier * gap
        b = Builder(UNITS)
        b.entity(
            'tank',
            value('amount', 'L', at + delta, scale=at),
            *(
                value(name, BOOL, formula(test))
                for name, test in (
                    ('eq', this.amount == q(at, 'L')),
                    ('ne', this.amount != q(at, 'L')),
                    ('le', this.amount <= q(at, 'L')),
                    ('lt', this.amount < q(at, 'L')),
                    ('ge', this.amount >= q(at, 'L')),
                    ('gt', this.amount > q(at, 'L')),
                )
            ),
        )
        sign = 0 if abs(multiplier) < 1 else 1 if multiplier > 0 else -1
        assert values(
            b.finish(), Configuration(Request(1)), ['eq', 'ne', 'le', 'lt', 'ge', 'gt'], reader
        ) == [
            sign == 0,
            sign != 0,
            sign <= 0,
            sign < 0,
            sign >= 0,
            sign > 0,
        ]


@pytest.mark.parametrize('through_choice', [False, True], ids=['direct', 'selected-formula'])
def test_sparse_template_filters_each_member_at_its_own_scale(through_choice):
    """All four tanks hold the same small signal. Only the rows with scale 1 L
    count it as zero. Their requests start at 1 L/h, the finer rows' at 7 L/h."""
    from napkin.engine.timeline import Plan, Run
    from napkin.engine.timeline.sparse import Sparse
    from napkin.program.build import endpoint, flow, ifelse, input_

    b = Builder(UNITS)
    supply = b.entity('supply', value('stock', 'L', 100, lower=0))
    extra = ()
    signal = this.signal
    if through_choice:
        extra = (
            value('coarse', 'L', 5e-11, scale=1),
            value('fine', 'L', 5e-11, scale=0.001),
            value('selected', 'L', formula(ifelse(this.resolution > q(0.1, 'L'), this.coarse, this.fine))),
        )
        signal = this.selected + q(0, 'L')
    cell = b.template(
        'Cell',
        input_('resolution', 'L', 1),
        value('signal', 'L', 5e-11, scale=this.resolution),
        *extra,
        value('water', 'L', 1, lower=0, inflow=endpoint(capacity=q(12, 'L/h'))),
        flow(
            'fill',
            supply.stock,
            this.water,
            request=formula(ifelse(signal == q(0, 'L'), this.water / q(1, 'h'), q(7, 'L/h'))),
        ),
    )
    b.table('cells', cell, [{'resolution': x} for x in (1, 0.001, 1, 0.001)])
    program = b.finish()
    cfg = Configuration(Request(1))
    timeline = Run(Plan.of(program, cfg))
    assert all(isinstance(way, Sparse) for way in timeline.prepare()[2])
    record = run(program, cfg)
    assert record.failure is None
    names = [Key(f'cells[{i}]', ('fill', 'actual_rate')) for i in range(4)]
    assert [series.values[0] for series in read(record, program, names, [0])] == [1, 7, 1, 7]


def test_an_inclusive_guard_does_not_prove_a_roundoff_value_nonnegative():
    """x = -1e-11 holds x >= 0 but has no real square root."""
    from napkin.core import expr, intervals
    from napkin.core.errors import ExpressionError
    from napkin.core.units import UnitRegistry

    prove = intervals.prover({'x': (-1, 1)}, UnitRegistry({}))
    with pytest.raises(ExpressionError, match='sqrt argument is nonnegative'):
        prove(expr.read('sqrt(x) if x >= 0 else 0'))


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_solver_locals_inverted_domain_uses_its_own_band(reader):
    from napkin.program.build import solver, unknown

    b = Builder(UNITS)
    b.entity('tank', solver('share', unknown('yielded', 'L', lower=q(0.30000000005, 'L'), upper=q(0.3, 'L'))))
    model = b.finish()
    cfg = Configuration(Request(1))
    key = Key('tank', ('share', 'yielded'))
    if reader == 'reference':
        oracle, failed = run_of(model, cfg)
        assert failed is None
        amount = value_at(oracle, model, key, 1)
    else:
        record = run(model, cfg)
        assert record.failure is None
        amount = read(record, model, [key], [1])[0].values[0]
    assert float(amount) == pytest.approx(0.300000000025, abs=1e-13)


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_redefined_alias_reads_the_scale_of_its_definition_at_the_requested_time(reader):
    """Both quantities hold 5e-11 L. The old alias has a 1e-9 L band and the new one 1e-12 L."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('coarse', 'L', 5e-11, scale=1),
        value('fine', 'L', 5e-11, scale=0.001),
        value('alias', 'L', formula(this.coarse)),
        value('zero', BOOL, formula(this.alias == q(0, 'L'))),
        event('change', after(q(1, 'h'), assign(this.alias, formula(this.fine)))),
    )
    b.setup(start(named('tank').change))
    program, cfg = b.finish(), Configuration(Request(1))
    key = Key('tank', ('zero',))
    if reader == 'reference':
        oracle, failure = run_of(program, cfg)
        assert failure is None
        values = tuple(value_at(oracle, program, key, t) for t in (1, 0))
    else:
        record = run(program, cfg)
        assert record.failure is None
        values = read(record, program, [key], [1, 0])[0].values
    assert values == (False, True)


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_starting_predicate_reads_a_later_fields_declared_scale(reader):
    """The boolean initializes first. The 1e−12 L band of the later field excludes zero."""
    from napkin.program.build import input_

    b = Builder(UNITS)
    b.entity(
        'tank',
        value('fine_zero', BOOL, this.fine == q(0, 'L')),
        value('coarse_zero', BOOL, this.coarse == q(0, 'L')),
        value('fine', 'L', 5e-11, scale=this.resolution),
        value('coarse', 'mL', 5e-8, scale=this.wide),
        input_('resolution', 'L', 0.001),
        input_('wide', 'L', 1),
    )
    assert values(b.finish(), Configuration(Request(1)), ['fine_zero', 'coarse_zero'], reader) == [
        False,
        True,
    ]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_fine_concentration_keeps_its_scale_in_inline_and_named_arithmetic(reader):
    """At 1e-12 mol/m3 the fine band's radius is 1e-21 mol/m3.
    The coarse peer and an explicitly coarse result each have radius 1e-9."""
    from napkin.program.build import ifelse

    u = 'mol/m3'
    b = Builder({**UNITS, 'mol': {'substance': 1}, 'm3': {'volume': 1}})
    fields = [
        value('c', u, 1e-12, scale=1e-12),
        value('coarse', u, 0, scale=1),
        value('offset', u, formula(this.c + q(0, u))),
        value('fixed', u, formula(this.offset), scale=1),
        value('fine_first', BOOL, False),
        value('chosen', u, formula(ifelse(this.fine_first, this.coarse, this.offset))),
    ]
    zero = q(0, u)
    checks = {
        'direct': this.c > zero,
        'inline': this.c + zero > zero,
        'backwards': zero < this.offset,
        'overridden': this.fixed > zero,
        'peers': this.c + this.coarse > zero,
        'peers_reversed': this.coarse + this.c > zero,
        'selected': this.chosen > zero,
        'selected_inline': ifelse(this.fine_first, this.coarse, this.offset) > zero,
    }
    b.entity('tank', *fields, *(value(k, BOOL, formula(v)) for k, v in checks.items()))
    assert values(b.finish(), Configuration(Request(1)), checks, reader) == [
        True,
        True,
        True,
        False,
        False,
        False,
        True,
        True,
    ]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_rescaled_quantity_and_its_literal_threshold_keep_the_same_band(reader):
    """2e-12 L is twice the 1e-12 L band. Scaling both sides by 1e-3
    gives a 2e-15 L signal and 1e-15 L band; either writing distinguishes it."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('signal', 'L', 2e-12, scale=0.001),
        value('small', 'mL', formula(0.001 * this.signal)),
        value('multiply', BOOL, formula(this.small > q(0, 'mL'))),
        value('divide', BOOL, formula(q(0, 'L') < this.signal / 1000)),
        value('scaled_inside', BOOL, formula(this.small <= q(1.5e-12, 'mL'))),
    )
    assert values(b.finish(), Configuration(Request(1)), ['multiply', 'divide', 'scaled_inside'], reader) == [
        True,
        True,
        True,
    ]


def test_sparse_expression_uses_the_selected_rows_scale():
    """The coarse rows' 1e-9 L band contains 5e-11 L; the fine rows' 1e-12 L band excludes it."""
    import numpy as np

    from napkin.core import arrays, expr
    from napkin.core.units import UnitRegistry

    units = UnitRegistry({})
    scales = {'a': 1.0, 'b': 0.001}
    units.comparisons.named = lambda n: (1, scales[n])
    node = expr.read('(c + 0 if pick else d + 0) > 0')
    env = {'c': np.full(4, 5e-11), 'd': np.full(4, 5e-11), 'pick': np.array([True, True, False, False])}
    bindings = {'c': ('a', 'b', 'a', 'b'), 'd': ('b', 'a', 'b', 'a'), 'pick': ('a',) * 4}
    assert list(arrays.values(node, env, units, 4, bindings)) == [False, True, True, False]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_repeated_reads_of_one_quantity_have_the_same_floor_as_a_literal_multiple(reader):
    """Twice x = 1.5e-9 L is inside twice x's band (2e-9 L).
    Subtracting its alias leaves zero contribution from x, so y keeps its fine scale."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('x', 'L', 0.75e-9, scale=1),
        value('y', 'L', 1e-12, scale=1e-12),
        value('alias', 'L', formula(this.x + q(0, 'L'))),
        value('doubled', BOOL, formula(2 * this.x > q(0, 'L'))),
        value('added', BOOL, formula(this.x + this.alias > q(0, 'L'))),
        value('cancelled', BOOL, formula(this.x + this.y - this.alias > q(0, 'L'))),
    )
    assert values(b.finish(), Configuration(Request(1)), ['doubled', 'added', 'cancelled'], reader) == [
        False,
        False,
        True,
    ]


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_named_choice_reads_only_its_selected_scale_at_the_requested_time(reader):
    """The value stays 1e-12 L. Its old floor is 1 L; its new floor is 1e-12 L.
    Dividing by zero in the unselected arm would fail the run."""
    from napkin.program.build import ifelse

    b = Builder(UNITS)
    b.entity(
        'tank',
        value('fine', 'L', 1e-12, scale=1e-12),
        value('coarse', 'L', 1e-12, scale=1),
        value('switched', BOOL, False),
        value('choice', 'L', formula(ifelse(this.switched, this.fine, this.coarse))),
        value(
            'guarded',
            'L',
            formula(ifelse(this.switched, this.choice, ifelse(this.switched, this.fine / 0, this.choice))),
        ),
        value('positive', BOOL, formula(this.guarded > q(0, 'L'))),
        event('narrow', after(q(1, 'h'), assign(this.switched, True))),
    )
    b.setup(start(named('tank').narrow))
    program, cfg = b.finish(), Configuration(Request(1))
    key = Key('tank', ('positive',))
    if reader == 'reference':
        oracle, failed = run_of(program, cfg)
        assert failed is None
        found = tuple(value_at(oracle, program, key, t) for t in (1, 0, 1))
    else:
        record = run(program, cfg)
        assert record.failure is None
        found = read(record, program, [key], [1, 0, 1])[0].values
    assert found == (True, False, True)


@pytest.mark.deep
@pytest.mark.parametrize('power', [0.5, 1, 2, 3])
def test_a_power_transforms_the_floor_in_the_results_units(power):
    """x = 1e-12 is a billion bands above zero. Its power has the same relative margin."""
    from napkin.core import arrays, evaluation, expr
    from napkin.core.units import UnitRegistry

    units = UnitRegistry({})
    units.comparisons.named = lambda name: (1, 1e-12)
    n = expr.read(f'x ** {power} > 0')
    env = {'x': 1e-12}
    assert evaluation.value(n, env, units)
    assert evaluation.program([], [n], units=units, write=False)(env, units) == (True,)
    assert arrays.values(n, env, units, 1)


@pytest.mark.parametrize('reader', ['engine', 'checkpoint', 'reference'])
def test_an_indexed_occurrence_keeps_the_selected_scale_when_its_formula_freezes(reader):
    """The 1e-12 L sample finishes at hour one with a 1e-12 L scale.
    Changing the live source to the coarse arm at hour two leaves that sample positive."""
    from napkin.engine.timeline import Plan, Run
    from napkin.program.build import ifelse, t
    from napkin.program.checkpoint import Breakpoint, dumps, loads

    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('fine', 'L', 1e-12, scale=1e-12),
        value('coarse', 'L', 1e-12, scale=1),
        value('pick', BOOL, True),
        event(
            'job', value('sample', 'L', formula(ifelse(this.pick, this.fine, this.coarse))), after(q(1, 'h'))
        ),
        event('change', after(q(2, 'h'), assign(this.pick, False))),
        value('sample_positive', BOOL, formula(this.job.occurrences.at(t).sample > q(0, 'L'))),
    )
    b.setup(start(tank.job), start(tank.change))
    p, cfg = b.finish(), Configuration(Request(3))
    key, times = Key('tank', ('sample_positive',)), [3, 0, 1, 2]
    if reader == 'reference':
        oracle, failure = run_of(p, cfg)
        assert failure is None
        found = [value_at(oracle, p, key, at) for at in times]
    else:
        if reader == 'checkpoint':
            machine = Run(Plan.of(p, cfg), (Breakpoint('tank.change.step[0]'),))
            checkpoint = machine.run()
            record = Run.restored(Plan.of(p, cfg), loads(dumps(checkpoint))).resume()
        else:
            record = run(p, cfg)
        assert record.failure is None
        found = read(record, p, [key], times)[0].values
    assert list(found) == [True] * len(times)


@pytest.mark.parametrize('reader', ['engine', 'reference'])
def test_a_table_key_forwards_the_selected_rows_comparison_scale(reader):
    """Two table rows both hold 5e-11 L. Row 0 uses a 1e-9 L band,
    row 1 a 1e-12 L band. At 1 h the table switches to row 1."""
    from napkin.program.build import input_, t

    b = Builder(UNITS)
    row = b.template(
        'Reading',
        input_('hour', 'h', 0),
        input_('resolution', 'L', 1),
        value('sample', 'L', 5e-11, scale=this.resolution),
    )
    b.table('readings', row, [{'hour': 0, 'resolution': 1}, {'hour': 1, 'resolution': 0.001}])
    sample = row.instances.by('hour').at(t).sample
    b.entity('tank', value('positive', BOOL, formula(sample > q(0, 'L'))))
    program, cfg = b.finish(), Configuration(Request(2))
    key, times = Key('tank', ('positive',)), (1, 0, 2)
    if reader == 'reference':
        oracle, failed = run_of(program, cfg)
        assert failed is None
        found = tuple(value_at(oracle, program, key, at) for at in times)
    else:
        record = run(program, cfg)
        assert record.failure is None
        found = read(record, program, [key], list(times))[0].values
    assert found == (True, False, True)
