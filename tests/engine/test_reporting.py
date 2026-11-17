"""Reporting samples each trajectory instant once per call without changing a single value.

The tests that read a study or a report use `evaluate_study(model)` and `sample_result(study, times)`
with `report['runs']`. The others evaluate the outputs of each run directly.
"""

import copy
import gc
import json
import math
import weakref

import pytest

import napkin.engine.report as engine_report
from napkin import SCHEMA_VERSION
from napkin.engine import evaluate_study, sample_result
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import SimulationError
from napkin.schema import FOLDER as SCHEMAS
from tests.acceptance.helpers import model_of
from tests.build import (
    append,
    check,
    compiled,
    edit,
    event,
    flow,
    formula,
    library,
    member,
    once_at,
    output,
    replace,
    run,
    scenario,
    stock,
    system,
)


class _Uncached:
    """A pass-through stand-in: every request reaches the trajectory itself."""

    def __init__(self, trajectory, capacity=1024):
        self._trajectory = trajectory

    def __getattr__(self, name):
        return getattr(self._trajectory, name)

    def env_at(self, t, side='right'):
        return self._trajectory.env_at(t, side=side)


def delivered(name, lag):
    """An output that counts the people served, as `delivered` does, `lag` later."""
    return output(name, 'service.served', 'people', doc='Delivered', under=(f'lag {lag}',))


def rows(sc, times, name='a', lib=None):
    """The output rows of one run at the given times."""
    lib = lib or library()
    rs, trajectory = run(sc, name, lib)
    return evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, times)


def test_cached_report_equals_the_uncached_report_and_leaves_the_study_intact(monkeypatch):
    sc = edit(scenario(), append(delivered('delayed', 'uniform(1 h, 3 h)')))
    model = compiled(sc, library())
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    times = [0, 0.5, 2, 6, 11.999999999, 12, 12.000000001, 20, 24]
    original_runs = dict(study.runs)
    traces = {name: copy.deepcopy(r['trajectory'].trace) for name, r in study.runs.items()}
    cached = sample_result(study, times)
    monkeypatch.setattr(engine_report, '_EnvironmentCache', _Uncached)
    uncached = sample_result(study, times)
    assert json.dumps(cached, allow_nan=False) == json.dumps(uncached, allow_nan=False)
    assert all(study.runs[name] is original for name, original in original_runs.items())
    assert traces == {name: r['trajectory'].trace for name, r in study.runs.items()}


def test_a_report_gives_each_output_as_the_compiled_model_has_it():
    """The `outcomes` of each run of a report are the outputs of the compiled model: each output
    with the keys and the texts that the compiler wrote, in their order, so the JSON of the two is
    the same text. The fixture has every construct of the language: an output with a lag, one that
    is not estimated, and several keys for each."""
    model = model_of('F5')
    report = sample_result(evaluate_study(model))
    assert report['runs']
    kinds = set()
    for name, found in report['runs'].items():
        compiled_outputs = model.structures[tuple(model.runs[name]['starts'])].plain()['outcomes']
        assert json.dumps(found['outcomes']) == json.dumps(compiled_outputs)
        for item in compiled_outputs.values():
            kinds |= {key for key in ('expr', 'lag', 'reason') if key in item}
            assert len(item) > 4
    assert kinds == {'expr', 'lag', 'reason'}


def test_environment_cache_reuses_exact_times_preserves_sides_and_evicts():
    class Trajectory:
        def __init__(self):
            self.calls = []

        def env_at(self, t, side='right'):
            self.calls.append((float(t), side))
            if side not in {'left', 'right'}:
                raise ValueError('side must be left or right')
            return {'t': float(t), 'impulse': 3 if side == 'left' else 8}

    original = Trajectory()
    view = engine_report._EnvironmentCache(original, capacity=2)
    first = view.env_at(12)
    first['impulse'] = 100
    assert view.env_at(12.0) == {'t': 12.0, 'impulse': 8}
    assert original.calls == [(12.0, 'right')]
    assert view.env_at(12, 'left')['impulse'] == 3
    assert view.env_at(12.000000001)['t'] == 12.000000001
    assert len(view._environments) == 2
    view.env_at(12)
    assert original.calls.count((12.0, 'right')) == 2
    with pytest.raises(ValueError):
        view.env_at(12, 'invalid')
    assert len(view._environments) == 2


def test_each_trajectory_instant_is_sampled_once_per_call(monkeypatch):
    study = evaluate_study(compiled(scenario(), library()))
    calls = []
    for name, item in study.runs.items():
        trajectory = item['trajectory']
        original = trajectory.env_at

        def counted(t, side='right', original=original, name=name):
            calls.append((name, float(t), side))
            return original(t, side=side)

        monkeypatch.setattr(trajectory, 'env_at', counted)
    report = sample_result(study, [0, 1, 2, 4, 8, 12, 24])
    assert report['admissible']
    assert calls and len(calls) == len(set(calls))


def test_reporting_constructs_one_unit_registry_per_call_and_releases_it(monkeypatch):
    study = evaluate_study(compiled(scenario(), library()))
    assert study.admissible
    registries = []
    original = engine_report.UnitSystem

    def construct(definitions):
        registry = original(definitions)
        registries.append(weakref.ref(registry))
        return registry

    monkeypatch.setattr(engine_report, 'UnitSystem', construct)
    first = sample_result(study, [0, 1, 2, 4, 8, 12, 24])
    assert first['admissible']
    assert len(registries) == 1
    gc.collect()
    assert registries[0]() is None
    second = sample_result(study, [0, 0.5, 3, 6, 9, 18, 24])
    assert second['admissible']
    assert len(registries) == 2
    gc.collect()
    assert all(reference() is None for reference in registries)


def capability_fixture():
    """A capability is a formula; its outputs report in the unit they are declared in."""
    return edit(
        scenario(),
        member('service', formula('throughput', '0.5 * rate', 'people/day', doc='Delivered work')),
        append(
            *(
                output(name, expression, 'people/day', 'instantaneous', doc=label)
                for name, label, expression in (
                    ('nominal', 'Nominal work', 'service.rate'),
                    ('throughput', 'Delivered work', 'service.throughput'),
                )
            )
        ),
    )


def test_capability_outputs_keep_display_units_and_current_nominal_service():
    sc = capability_fixture()
    rate = compiled(sc).run_values('a')['service.rate']
    first = rows(sc, [0, 12])[0]
    # The declared value, in the unit it is declared in, and half of it delivered.
    assert first['values']['nominal'] == pytest.approx(rate)
    assert first['values']['throughput'] == pytest.approx(rate / 2)


def test_capability_reports_keep_display_units():
    result = evaluate_study(compiled(capability_fixture(), library()))
    assert result.admissible, result.diagnostics
    report = sample_result(result, [0, 12])
    assert report['schema_version'] == SCHEMA_VERSION
    assert report['model_hash'] == result.model.model_hash
    assert report['implementation_hash'] == result.model.implementation_hash
    # The report names its scenario by its file: the file test.scn of no package is named by its
    # stem, and a model that is not a variant has no variant.
    assert (report['scenario'], report['variant']) == ('test', None)
    assert 'scenario_id' not in report
    a = report['runs']['a']
    assert a['options'] == ['Default']
    assert a['outcomes']['throughput']['unit'] == a['outcomes']['nominal']['unit'] == 'people/day'


def test_an_output_in_a_composed_unit_with_no_entry_reports_in_that_unit():
    """A composed unit needs no entry (docs/language.md): an output in `people/days` or in
    `people-h/days` reports in that unit, by the scales of the declared units it is made of."""
    lib = library()
    assert not {'people/days', 'people-h/days'} & set(lib['units'])
    sc = edit(
        scenario(),
        append(
            output('rate_per_day', 'service.rate', 'people/day', 'instantaneous', doc='Rate per day'),
            output('rate_per_days', 'service.rate', 'people/days', 'instantaneous', doc='Rate per days'),
            output('served_people', 'service.served', 'people', doc='Served'),
            output('served_hours', 'service.served', 'people-h/days', doc='Served, as hours a day'),
        ),
    )
    found = rows(sc, [0, 12, 24], lib=lib)
    assert found
    for row in found:
        values = row['values']
        # A day and `days` are both 24 h, so the rate is one number in either unit.
        assert values['rate_per_days'] == pytest.approx(values['rate_per_day'])
        # One person is 24 people-h/days (1 h / 24 h of a person each), so the count is 24 times as large.
        assert values['served_hours'] == pytest.approx(24 * values['served_people'])
    assert found[-1]['values']['served_people'] > 0


def capped_fixture(*steps):
    """The analytic transfer with an output of the people served, capped at a quarter of the people:
    it reaches its cap inside the first segment of each run and stays there."""
    return edit(
        scenario(),
        *steps,
        append(output('capped', 'min(service.served, service.n / 4)', 'people', 'level', doc='Capped')),
    )


def served_by(values, t):
    """The closed form of the people served by time t: min(n, rate * min(t, end)), with the rate a
    day over 24 hours."""
    return min(values['service.n'], values['service.rate'] / 24 * min(t, values['service.end']))


def test_a_report_gives_the_final_point_and_each_time_that_it_asks_for():
    """A report gives `final`, the horizon, and each time that it asks for, in order, by its number of
    hours: the model names no times. The values at each point are the closed form of the people
    served, and the samples and the health have the same times. The final point is the same, bit for
    bit, whatever times the report asks for."""
    model = compiled(capped_fixture(), library())
    assert 'reports' not in model.time
    study = evaluate_study(model)
    plain, asked = sample_result(study), sample_result(study, [6, 1.5])
    horizon = float(model.time['horizon'])
    for name in model.runs:
        values = model.run_values(name)
        points = asked['runs'][name]['reporting_points']
        assert list(plain['runs'][name]['reporting_points']) == ['final']
        assert list(points) == ['1.5', '6.0', 'final']
        assert [point['t'] for point in points.values()] == [1.5, 6.0, horizon]
        for point in points.values():
            assert point['values'][model.outputs['delivered']] == pytest.approx(
                served_by(values, point['t']), rel=1e-9
            )
        for key in ('samples', 'health'):
            assert [row['t'] for row in asked['runs'][name][key]] == [1.5, 6.0, horizon], key
            assert [row['t'] for row in plain['runs'][name][key]] == [horizon], key
        assert points['final'] == plain['runs'][name]['reporting_points']['final']


def test_a_peak_is_the_same_whatever_times_a_report_asks_for():
    """The capped output reaches its cap inside the first segment of each run and stays there. Its
    peak is the cap, at an end or a middle of a segment after the time when the served people reach
    the cap. A time on that plateau before the peak is no candidate when a report asks for it: the
    peak is the same, bit for bit."""
    plain = compiled(capped_fixture(), library())
    capped = plain.outputs['capped']
    for name in plain.runs:
        values = plain.run_values(name)
        cap = values['service.n'] / 4
        reached = cap / (values['service.rate'] / 24)
        study = evaluate_study(plain, runs=[name])
        peak = sample_result(study)['runs'][name]['peaks'][capped]
        assert peak['value'] == pytest.approx(cap, rel=1e-12) and not peak['certified']
        segments = study.runs[name]['trajectory']._segments
        candidates = {
            x
            for s in segments
            for x in (s.start, s.end, (s.start + s.end) / 2, math.nextafter(s.end, s.start))
        }
        assert peak['t'] in candidates and peak['t'] > reached
        # Times on the plateau before the peak, asked for one by one and together.
        on_plateau = [reached + (peak['t'] - reached) * share for share in (0.25, 0.5, 0.75)]
        for t in on_plateau:
            assert sample_result(study, [t])['runs'][name]['peaks'][capped] == peak
        assert sample_result(study, on_plateau)['runs'][name]['peaks'][capped] == peak


def test_conditional_unknown_is_lazy_and_arbitrary_output_names_work():
    sc = edit(
        scenario(),
        append(
            output(
                'unquantified',
                None,
                'people',
                doc='Unknown',
                under=('scope "Missing"', 'unestimated "No source gives it."'),
            ),
            output(
                'conditional',
                '0 if service.served is 0 else unquantified',
                'people',
                doc='Conditional',
                under=('scope "Conditional"', 'level', 'signed'),
            ),
        ),
    )
    start, final = rows(sc, [0, 24])
    assert start['values']['conditional'] == 0
    assert final['values']['conditional'] is None


def test_delay_kernels_step_ramp_and_impulse_independent_values():
    sc = edit(
        scenario(),
        replace('input n: people = 10 people', 'input n: people = 100 people'),
        replace('input end: h = 12 h', 'input end: h = 24 h'),
        # Two people move at once at 5 h, on top of the ramp of one person an hour.
        member('service', event('impulse', 't >= 5 h', 'move 2 people from stock to served', doc='Impulse')),
        append(
            *(
                delivered(key, lag)
                for key, lag in [
                    ('fixed', '3 h'),
                    ('uniform', 'uniform(1 h, 3 h)'),
                    ('weighted', 'mixture([0.25, 1 h], [0.75, 3 h])'),
                    ('degenerate', 'uniform(3 h, 3 h)'),
                ]
            )
        ),
    )
    (row,) = rows(sc, [7])
    values = row['values']
    assert values['fixed'] == pytest.approx(4)
    assert values['uniform'] == pytest.approx(6)  # mean ramp=5, half of 2-person impulse delivered
    assert values['weighted'] == pytest.approx(0.25 * 8 + 0.75 * 4)
    assert values['degenerate'] == pytest.approx(4)


def test_unknown_dependency_never_becomes_certified_estimated_peak():
    sc = edit(
        scenario(),
        append(
            output('unknown', None, 'people', doc='Delivered', under=('unestimated "No source gives it."',)),
            # An output with no estimate has no expression, so a sum with it proves neither a sign nor
            # a monotone count: the dependent output claims neither.
            output(
                'dependent',
                'unknown + service.served',
                'people',
                doc='Delivered',
                under=('level', 'signed', 'distinct  @fixture'),
            ),
        ),
    )
    result = evaluate_study(compiled(sc, library()))
    assert result.admissible, result.diagnostics
    for item in sample_result(result)['runs'].values():
        final = item['reporting_points']['final']
        assert final['values']['dependent'] is None
        assert final['statuses']['dependent'] == 'unestimated'
        peak = item['peaks']['dependent']
        assert peak['value'] is None
        assert not peak['certified']
        assert peak['status'] == 'unestimated'
        assert peak['partial']


def test_a_lagged_output_that_is_not_estimated_is_never_a_known_zero():
    lib = library()
    sc = edit(
        scenario(),
        member('output:/delivered', 'category deaths'),
        append(
            output(
                'unknown_fixed',
                None,
                'people',
                doc='Delivered',
                under=('category deaths', 'lag 6 h', 'unestimated "No source gives it."'),
            )
        ),
    )
    study = evaluate_study(compiled(sc, lib))
    assert study.admissible, study.diagnostics
    report = sample_result(study, [0, 1, 5.9, 6, 12, 24])['runs']['a']
    for row in report['samples']:
        assert (row['values']['unknown_fixed'], row['statuses']['unknown_fixed']) == (None, 'unestimated')
    peak = report['peaks']['unknown_fixed']
    assert peak['value'] is None and not peak['certified']


def test_a_uniform_lag_is_the_mean_of_its_window_in_closed_form():
    # A decaying stock fills a tally, finished = 100 (1 - e^{-t/10}), and a moment at 7 h splits the
    # history. The output is the mean of finished over [t - 6 h, t - 2 h], and finished is zero before time
    # zero. With C(x) = 100 (x + 10 (e^{-x/10} - 1)), the integral of finished from 0 to x >= 0, the mean
    # is (C(max(0, t - 2)) - C(max(0, t - 6))) / 4. An output with no estimate has none in any window.
    lagged = output('reported', 's.finished', 'people', doc='Reported', under=('lag uniform(2 h, 6 h)',))
    unknown = output(
        'unknown',
        None,
        'people',
        doc='Unknown',
        under=('lag uniform(2 h, 6 h)', 'unestimated "No source gives it."'),
    )
    source = system(
        stock('pending', 100),
        stock('finished', 0),
        stock('flag', kind='state'),
        flow('finish', 'pending -> finished', '0.1 per_h * pending'),
        once_at('mark', '7 h', 'flag = 1 people'),
        horizon=20,
        outputs=(lagged, unknown),
    )
    lib = library()
    rs, trajectory = run(source, 'a', lib)
    completed = {'resolved': rs, 'trajectory': trajectory}
    times = [0, 1, 2, 3, 5, 6, 7, 8, 9.5, 13, 20]

    def integral(x):
        x = max(0.0, x)
        return 100 * (x + 10 * math.expm1(-x / 10))

    together = evaluate_outputs(completed, lib, times)
    for t, row in zip(times, together, strict=True):
        assert row['statuses']['reported'] == 'estimated'
        mean = (integral(t - 2) - integral(t - 6)) / 4
        assert row['values']['reported'] == pytest.approx(mean, rel=1e-11, abs=1e-12)
        assert (row['values']['unknown'], row['statuses']['unknown']) == (None, 'unestimated')
        # The windows of one report share their pieces; a time reported alone has its own pieces and
        # the same mean.
        (alone,) = evaluate_outputs(completed, lib, [t])
        assert alone['values']['reported'] == pytest.approx(row['values']['reported'], rel=1e-13, abs=1e-13)


# The message of the check that `capacity_fixture` adds.
CAPACITY = 'At most five served'


def capacity_fixture():
    # One person is served each hour, so more than five have been served after 5 h.
    return edit(scenario(), append(check('service.served <= 5 people', CAPACITY)))


def test_a_run_stopped_by_an_invariant_names_the_check():
    sc = capacity_fixture()
    with pytest.raises(SimulationError) as caught:
        run(sc)
    failed = [d for d in caught.value.diagnostics if d.get('code') == 'check_failed']
    assert failed and {d['message'] for d in failed} == {f'Check simulate.1: {CAPACITY}'}
    assert all(5 <= d['t'] <= 12 for d in failed)


def test_a_study_stopped_by_an_invariant_reports_a_schema_valid_diagnostic():
    from jsonschema import Draft202012Validator

    sc = capacity_fixture()
    study = evaluate_study(compiled(sc, library()))
    assert not study.admissible
    report = sample_result(study)
    schema = json.loads((SCHEMAS / 'report.schema.json').read_text(encoding='utf-8'))
    assert not [error.message for error in Draft202012Validator(schema).iter_errors(report)]
    failed = [d for d in report['diagnostics'] if d.get('code') == 'check_failed']
    assert failed and {d['message'] for d in failed} == {f'Check simulate.1: {CAPACITY}'}
    assert all(5 <= d['t'] <= 12 for d in failed)
