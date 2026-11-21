"""A clock can group a located stock contact only while that stock is also within its own band."""

from dataclasses import replace

import pytest

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CEILING = '(2 - t / (1 h)) * (1 L/h)'
# The adaptive path can have about 1e-9 L of integration error at the kink.
# At 1 L/h that shifts a located time by the same number of hours. This
# tolerance keeps the checks strictly on their own side of the 5e-9 h gap.
KINK_ERROR = 1.5e-9


def gauge(method, target, horizon, *, mixed=False, empty=False, empty_at='0.5', ceiling='pipe', close=False):
    pipe_cap = f'\n        capacity = formula({CEILING})' if ceiling == 'pipe' else ''
    end_cap = f'\n        inflow.capacity = formula({CEILING})' if ceiling == 'endpoint' else ''
    close_pipe = '\n            this.fill.request = 0 L/h' if close else ''
    source = f"""scenario "Nearby stock crossings"
    horizon {horizon} h
yard:
    stock: L = 0 L scale 1 L{end_cap}
    marked: h = -1 h
    seen: L = -1 L
    opening_mark: h = -1 h
    flow fill: SOURCE -> this.stock
        request = 1 L/h{pipe_cap}
    watch = event():
        when this.stock >= {target} L:
            this.watch.start()
        after 0 h:
            this.marked = t
    clock = event():
        after 1 h:
            this.seen = this.stock
            this.opening_mark = this.marked{close_pipe}
        after 0 h
"""
    if mixed:
        source += f"""    close: L = 0 L scale 10 L
    close_mark: h = -1 h
    flow other: SOURCE -> this.close
        request = 1 L/h
    near = event():
        when this.close >= {target} L:
            this.near.start()
        after 0 h:
            this.close_mark = t
"""
    if empty:
        source += f"""    extra = event():
        after {empty_at} h
yard.extra.start()
"""
    source += 'yard.clock.start()\n'
    if method == 'moving_declared':
        source += """owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
"""
        if ceiling == 'solver':
            source += f'        constraints:\n            pipe.actual_rate <= {CEILING}\n'
    return compile_text(source, UNITS)


def force(method, monkeypatch):
    connect = Plan.connect

    def groups(plan, *args, **kwargs):
        found = connect(plan, *args, **kwargs)
        if method == 'moving_declared':
            return [replace(group, moves=True) if group.way == 'declared' else group for group in found]
        return [replace(group, way=method) for group in found]

    monkeypatch.setattr(Plan, 'connect', groups)


def results(case, restore, *, breakpoint='yard.clock.step[0]', stop_at=1):
    def plan():
        return Plan.of(case.program, case.configuration)

    run = Run(plan(), (Breakpoint(breakpoint),) if restore else ())
    record = run.run()
    if restore:
        assert isinstance(record, Checkpoint) and record.stop.t == stop_at
        data = dumps(record)
        fields = ['yard.stock', 'yard.fill.actual_rate']
        forward = read(record.record, case.program, fields, [0.5, stop_at])
        reverse = read(record.record, case.program, fields[::-1], [stop_at, 0.5])
        assert [row.values for row in forward] == [row.values[::-1] for row in reverse[::-1]]
        assert dumps(record) == data
        run = Run.restored(plan(), loads(data))
        record = run.resume()
    assert record.failure is None, record.failure
    return record


def times(record, watch):
    return [e.t for e in record.entries('fire', f'yard.{watch}.when[0]')]


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize('target', ['0.999999995', '1.000000005'])
def test_a_time_near_stock_contact_keeps_its_true_time_on_either_side_of_the_stage(
    method, target, monkeypatch
):
    force(method, monkeypatch)
    at = float(target)
    for empty, restore in ((False, False), (True, False), (True, True)):
        case = gauge(method, target, '1.1', empty=empty)
        record = results(case, restore)
        assert times(record, 'watch') == pytest.approx([at], rel=0, abs=KINK_ERROR)
        seen, opening, mark = read(
            record, case.program, ['yard.seen', 'yard.opening_mark', 'yard.marked'], [1.1]
        )
        assert seen.values == pytest.approx([1], rel=0, abs=KINK_ERROR)
        assert opening.values == pytest.approx([at if at < 1 else -1], rel=0, abs=KINK_ERROR)
        assert mark.values == pytest.approx([at], rel=0, abs=KINK_ERROR)
        clock = [e for e in record.entries('commit') if e.part.startswith('yard.clock.step')]
        assert [e.t for e in clock] == [1, 1]
        assert clock[0].round < clock[1].round


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_late_checkpoint_preserves_the_stock_crossing_beyond_the_hour(method, monkeypatch):
    force(method, monkeypatch)
    target = '1.000000005'
    for cut, restore in ((False, False), (True, False), (True, True)):
        case = gauge(method, target, '1.1', empty=cut, empty_at='0.99999')
        record = results(case, restore, breakpoint='yard.extra.step[0]', stop_at=0.99999)
        water, seen = read(record, case.program, ['yard.stock', 'yard.seen'], [0.99999, 1])
        assert water.values == pytest.approx([0.99999, 1], abs=KINK_ERROR, rel=0)
        assert seen.values[-1] == pytest.approx(1, abs=KINK_ERROR, rel=0)
        assert times(record, 'watch') == pytest.approx([float(target)], abs=KINK_ERROR, rel=0)


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_stage_at_the_horizon_does_not_consume_a_later_out_of_band_contact(method, monkeypatch):
    force(method, monkeypatch)
    case = gauge(method, '1.000000005', '1')
    for restore in (False, True):
        record = results(case, restore)
        assert record.end == 1 and not times(record, 'watch')
        seen, mark = read(record, case.program, ['yard.seen', 'yard.marked'], [1])
        assert seen.values == pytest.approx([1], rel=0, abs=KINK_ERROR)
        assert mark.values == (-1,)


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_one_stock_can_join_a_stage_without_consuming_another_stock_on_the_same_clock(method, monkeypatch):
    # The same 5e-9 L gap fits the 10-L scale and lies outside the 1-L stock's band.
    threshold = '1.000000005'
    force(method, monkeypatch)
    case = gauge(method, threshold, '1.1', mixed=True, empty=True)
    for restore in (False, True):
        record = results(case, restore)
        assert times(record, 'near') == [1]
        assert times(record, 'watch') == pytest.approx([float(threshold)], abs=KINK_ERROR, rel=0)
        markers = read(record, case.program, ['yard.close_mark', 'yard.marked'], [1.1])
        assert markers[0].values == (1,)
        assert markers[1].values == pytest.approx([float(threshold)], abs=KINK_ERROR, rel=0)


@pytest.mark.parametrize(
    'method,ceiling', [('sparse', 'endpoint'), ('moving_declared', 'endpoint'), ('moving_declared', 'solver')]
)
def test_an_endpoint_or_declared_rate_ceiling_preserves_the_later_contact(method, ceiling, monkeypatch):
    force(method, monkeypatch)
    case = gauge(method, '1.000000005', '1.1', ceiling=ceiling)
    record = results(case, True)
    assert times(record, 'watch') == pytest.approx([1.000000005], abs=KINK_ERROR, rel=0)
    (seen,) = read(record, case.program, ['yard.seen'], [1.1])
    assert seen.values == pytest.approx([1], abs=KINK_ERROR, rel=0)


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_half_a_litre_on_a_small_remaining_stock_cannot_be_moved_to_a_nearby_stage(method, monkeypatch):
    force(method, monkeypatch)
    source = """scenario "Half a litre near a clock crossing"
    horizon 1.000000008 h
yard:
    stock: L = 100000001 L scale 0.000001 L
    seen: L = -1 L
    flow fill: this.stock -> SINK
        request = 100000000 L/h
        capacity = formula((2 - t / (1 h)) * (100000000 L/h))
    watch = event():
        when this.stock <= 0.5 L:
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h:
            this.seen = this.stock
    cut = event():
        after 0.99999 h
yard.clock.start()
yard.cut.start()
"""
    if method == 'moving_declared':
        source += """owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
"""
    case = compile_text(source, UNITS)
    for restore in (False, True):
        record = results(case, restore)
        (seen,) = read(record, case.program, ['yard.seen'], [record.end])
        assert seen.values == pytest.approx([1], abs=1e-5, rel=0)
        # The final 1e-5 h before the clock provides only 0.005 L of extra
        # room. Achieving 0.5 L on that clock would spend 0.495 L beyond it.
        # The half-litre crossing lies 5e-9 h later, under the falling cap.
        assert times(record, 'watch') == pytest.approx([1.000000005], abs=1e-12, rel=0)


@pytest.mark.parametrize(
    'target,horizon,mixed,watch_times',
    [
        ('0.999999995', '1.1', False, ('0.999999995',)),
        ('1.000000005', '1.1', False, ('1.000000005',)),
        ('1.000000005', '1', False, ()),
        ('1.000000005', '1.1', True, ('1.000000005',)),
    ],
)
def test_the_reference_keeps_each_stocks_exact_contact_time(target, horizon, mixed, watch_times):
    from fractions import Fraction

    from tests.reference.from_program import run_of

    # With a held request and no moving constraint, all roots are rational and
    # all parts of the comparison lie inside the independent interpreter's domain.
    case = gauge('component', target, horizon, mixed=mixed, ceiling='none')
    run, failure = run_of(case.program, case.configuration)
    assert failure is None
    fires = [(entry.label, entry.t) for entry in run.trace if entry.kind == 'fire']
    expected = [('yard.near.when[0]', Fraction(1))] if mixed else []
    expected.extend(('yard.watch.when[0]', Fraction(t)) for t in watch_times)
    assert fires == expected


@pytest.mark.parametrize('method', ['component', 'sparse', 'moving_declared'])
def test_a_stage_that_closes_the_pipe_cancels_only_its_later_contact(method, monkeypatch):
    force(method, monkeypatch)
    for target in ('0.999999995', '1.000000005'):
        case = gauge(method, target, '1.1', close=True)
        request = case.configuration.request
        for selection in (request, replace(request, everything=False, keys=(Key('yard', ('seen',)),))):
            selected = replace(case, configuration=replace(case.configuration, request=selection))
            record = results(selected, False)
            at = float(target)
            expected = [at] if at < 1 else []
            assert times(record, 'watch') == pytest.approx(expected, abs=KINK_ERROR, rel=0)
            (seen,) = read(record, case.program, ['yard.seen'], [1.1])
            assert seen.values == pytest.approx([1], abs=KINK_ERROR, rel=0)
