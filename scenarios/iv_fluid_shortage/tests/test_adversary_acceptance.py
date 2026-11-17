"""Independent acceptance inputs and causal clocks for all six response paths.

The archived consequence fixtures preserve their original literal inputs and
independent formulas. Current electricity acceptance uses independently authored
operational clocks and finite support arithmetic. Current supply acceptance uses
fixed qualification work, explicit resource rates and a physical receipt lag.
"""

import pytest

from napkin.engine import edits_for
from scenarios.iv_fluid_shortage.tests.adversary_acceptance_support import keeps_access as keeps_access
from scenarios.iv_fluid_shortage.tests.shortage import ai_clocks, release_work
from scenarios.tests.sources import oracle_inputs, response_of
from tests.helpers import catalogue_default, catalogue_model
from tools.publish.brief import brief_of

pytestmark = pytest.mark.deep

ALTER = 'attacker.alter_on_procurement'


def assert_supply_work(model, item):
    """Release-work states equal the independent serial ledger at each clock, just after it and at the end."""
    p = oracle_inputs('iv_fluid_shortage', item['resolved'].parameter_values)
    persistent = keeps_access(model, item['resolved'].run)
    clocks = ai_clocks(p, persistent=persistent)
    ordinary = p['qualification_work_h'] + (0 if persistent else p['extra_delay_h'])
    total = ordinary + (p['extra_delay_h'] + p['deep_reconcile_h'] if persistent else 0)
    marks = {0, 0.001, p['act_h'], ordinary / p['qualification_rate'], 1440}
    marks |= {clock + step for clock in clocks.values() if clock is not None for step in (0, 1)}
    tr = item['trajectory']
    for t in sorted(mark for mark in marks if mark <= 1440):
        expected = release_work(p, t, persistent=persistent)
        env = tr.env_at(t)
        assert env['release_team.ordinary_left'] == pytest.approx(expected['ordinary'], abs=1e-8), t
        assert env['release_team.to_reconcile'] == pytest.approx(expected['pending'], abs=1e-8), t
        assert env['release_team.reserve'] == pytest.approx(expected['potential'], abs=1e-8), t
        assert env['release_team.work_done'] == pytest.approx(expected['completed'], abs=1e-8), t
        assert sum(
            env[k]
            for k in (
                'release_team.ordinary_left',
                'release_team.to_reconcile',
                'release_team.reserve',
                'release_team.work_done',
            )
        ) == pytest.approx(total, abs=1e-8)


def assert_supply_release(model, item):
    """The qualified release, and the receipt one physical lead later, occur at the independent release
    clocks of the run's own inputs."""
    p = oracle_inputs('iv_fluid_shortage', item['resolved'].parameter_values)
    clocks = ai_clocks(p, persistent=keeps_access(model, item['resolved'].run))
    events = {e['event']: e['t'] for e in item['trajectory'].trace}
    for event, clock in (
        ('release_team.restart_release.done', 'release'),
        ('deliveries.first_arrival.done', 'receipt'),
    ):
        if clocks[clock] is None:
            assert event not in events, event
        else:
            assert events[event] == pytest.approx(clocks[clock], abs=1e-8), event


def test_serial_work_preserves_qualification_rates_and_finite_reconciliation():
    model = catalogue_model('iv_fluid_shortage')
    result = catalogue_default('iv_fluid_shortage')
    assert result.admissible, result.diagnostics
    for item in result.runs.values():
        assert_supply_work(model, item)
        assert_supply_release(model, item)


def test_zero_extra_work_preserves_containment_and_physical_receipt_lag():
    from napkin.engine import evaluate_study

    model = catalogue_model('iv_fluid_shortage')
    (access,) = model.start_options
    result = evaluate_study(model, edits_for(model, {'options': {access: {'release_team.records_work': 0}}}))
    assert result.admissible, result.diagnostics
    for item in result.runs.values():
        assert_supply_work(model, item)
        assert_supply_release(model, item)


def test_baseline_extra_work_is_an_explicit_finite_task():
    from napkin.engine import evaluate_study

    model = catalogue_model('iv_fluid_shortage')
    single = [run for run in model.runs if not keeps_access(model, run)]
    result = evaluate_study(
        model, edits_for(model, {'runs': {run: {'release_team.records_work': 24} for run in single}})
    )
    assert result.admissible, result.diagnostics
    for run, item in result.runs.items():
        if keeps_access(model, run):
            continue
        assert_supply_work(model, item)
        assert_supply_release(model, item)
        # The single strike folds its extra work into the ordinary qualification work.
        work = item['resolved'].parameter_values['release_team.ordinary_work'] + 24
        assert item['trajectory'].env_at(0)['release_team.ordinary_left'] == pytest.approx(work, abs=1e-8)
        assert f'{ALTER}.done' not in {e['event'] for e in item['trajectory'].trace}


def test_work_completion_activation_and_containment_settle_at_one_timestamp():
    from napkin.engine import evaluate_study

    model = catalogue_model('iv_fluid_shortage')
    # 504 work-hours at 2.1 an hour finish at 240 h, the hour procurement starts and the foothold is removed.
    result = evaluate_study(
        model,
        edits_for(
            model,
            {
                'set': {'release_team.ordinary_work': 504, 'release_team.records_work': 0},
                'options': {
                    response: {
                        'hospitals.start_delay': 240,
                        'manufacturer.foothold_removal_time': 240,
                        'release_team.pace': 2.1,
                        'manufacturer.release_allowed': True,
                    }
                    for response in model.menu[brief_of(model).choice_group]
                },
            },
        ),
    )
    assert result.admissible, result.diagnostics
    for run, item in result.runs.items():
        assert_supply_work(model, item)
        events = {e['event']: e['t'] for e in item['trajectory'].trace}
        for event in (
            'hospitals.emergency_procurement.done',
            'release_team.ready_without_changes.done',
            'release_team.restart_release.done',
        ):
            assert events[event] == pytest.approx(240, abs=1e-8)
        # No record is altered, so the work is ready as the ordinary work ends, with no reconciliation.
        assert 'release_team.ordinary_work_done.done' not in events
        assert 'release_team.work_ready.done' not in events
        lead = item['resolved'].parameter_values['deliveries.lead_time']
        assert events['deliveries.first_arrival.done'] == pytest.approx(240 + lead, abs=1e-8)
        assert item['trajectory'].env_at(100)['release_team.ordinary_left'] == pytest.approx(294, abs=1e-8)
        if keeps_access(model, run):
            # The cleanup at the same instant comes first, so the first tampering is stopped.
            assert events['manufacturer.foothold_removed.done'] == events[f'{ALTER}.stopped'] == 240
            assert f'{ALTER}.done' not in events


@pytest.mark.parametrize('procurement', [60, 63, 72])
def test_changes_after_the_ordinary_work_are_reconciled_before_release(procurement):
    """504 ordinary work-hours at 8 an hour end at 63 h; procurement starts just before, at or after
    that, and the foothold goes at 80 h. With hidden access the 168 work-hours of altered records are
    reconciled once both the ordinary work and the change exist, so release waits for that work: at
    max(80, max(procurement, 63) + 21) h, which is 84 h or 93 h, never at 80 h with work pending."""
    from napkin.engine import evaluate_study

    model = catalogue_model('iv_fluid_shortage')
    (access,) = model.start_options
    ordinary, records, pace, foothold = 504, 168, 8, 80
    responses = {
        response: {
            'hospitals.start_delay': procurement,
            'manufacturer.foothold_removal_time': foothold,
            'release_team.pace': pace,
            'manufacturer.release_allowed': True,
        }
        for response in model.menu[brief_of(model).choice_group]
    }
    edits = {
        'set': {'release_team.ordinary_work': ordinary},
        'options': {access: {'release_team.records_work': records}, **responses},
    }
    result = evaluate_study(model, edits_for(model, edits))
    assert result.admissible, result.diagnostics
    for run, item in result.runs.items():
        assert_supply_work(model, item)
        assert_supply_release(model, item)
        if keeps_access(model, run):
            release, work = (
                max(foothold, max(procurement, ordinary / pace) + records / pace),
                ordinary + records,
            )
        else:
            release, work = max(foothold, procurement, ordinary / pace), ordinary
        events = {e['event']: e['t'] for e in item['trajectory'].trace}
        assert events['release_team.restart_release.done'] == pytest.approx(release, abs=1e-8)
        assert item['trajectory'].env_at(release)['release_team.work_done'] == pytest.approx(work, abs=1e-6)


def test_disabled_release_keeps_qualified_inventory_and_courses_accounted():
    from napkin.engine import evaluate_study

    model = catalogue_model('iv_fluid_shortage')
    response = response_of(model, 'subpar')
    result = evaluate_study(
        model, edits_for(model, {'options': {response: {'manufacturer.release_allowed': False}}})
    )
    assert result.admissible, result.diagnostics
    for run, item in result.runs.items():
        if response_of(model, run) != response:
            continue
        assert 'deliveries.first_arrival.done' not in {e['event'] for e in item['trajectory'].trace}
        p = item['resolved'].parameter_values
        env = item['trajectory'].env_at(item['trajectory'].horizon)
        # The study period's resuscitation demand, in complete courses, is eligible, timely or unserved.
        assert env['resuscitation_patients.eligible'] + env['resuscitation_patients.timely'] + env[
            'resuscitation_patients.unserved'
        ] == pytest.approx(
            p['resuscitation_reserve.daily_need']
            / 24
            * p['manufacturer.study_length']
            / p['resuscitation_patients.course_volume'],
            abs=1e-6,
        )
