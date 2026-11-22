"""Recovery, finite work queues, transport and physical lot holds."""

import pytest

from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import readings, record, starts

WORK = (
    'release_team.ordinary_left',
    'release_team.to_reconcile',
    'release_team.reserve',
    'release_team.work_done',
)


@pytest.mark.parametrize(
    ('run', 'release', 'total'),
    [
        ('near_ideal', 252, 504),
        ('subpar', 504, 504),
        ('minimal', 840, 504),
        ('near_ideal_persistent', 336, 1008),
        ('subpar_persistent', 672, 1008),
        ('subpar_persistent_human', 672, 1008),
        ('minimal_persistent', 1120, 1008),
    ],
)
def test_named_runs_keep_qualification_work_and_shipping_lead(run, release, total):
    r = record(run)
    events = starts(r)
    assert events['release_team.restart_release'] == pytest.approx(release)
    assert events['deliveries.first_arrival'] == pytest.approx(release + 24)
    hours = sorted({0, 0.001, 72, 168, release, release + 24, 1440, *events.values()})
    work = readings(r, WORK, hours)
    assert all(sum(parts) == pytest.approx(total) for parts in zip(*work.values(), strict=True))
    assert work[WORK[0]][0] == 504
    assert work[WORK[0]][hours.index(release)] == 0
    assert work[WORK[-1]][hours.index(release)] == pytest.approx(672 if total == 1008 else 504)


@pytest.mark.parametrize('procurement', [60, 63, 72])
def test_review_before_at_or_after_ordinary_completion_is_done_before_release(procurement):
    r = record(
        'subpar_persistent',
        **{
            'hospitals.start_delay': procurement,
            'manufacturer.containment_time': 80,
            'release_team.pace': 8,
            'records.released_lot': 'CLEAR',
        },
    )
    events = starts(r)
    release = max(80, max(63, procurement) + 168 / 8)
    assert events['release_team.restart_release'] == pytest.approx(release)
    assert events['deliveries.first_arrival'] == pytest.approx(release + 24)
    assert readings(r, WORK, [release])[WORK[-1]] == pytest.approx([672])
    assert 'manufacturer.discrepancy_confirmed' not in events


def test_zero_extra_work_and_simultaneous_containment_still_require_physical_transport():
    r = record(
        'subpar_persistent',
        **{
            'release_team.records_work': 0,
            'release_team.pace': 2.1,
            'manufacturer.containment_time': 240,
            'hospitals.start_delay': 240,
            'records.released_lot': 'CLEAR',
        },
    )
    events = starts(r)
    assert [
        events[n]
        for n in (
            'release_team.ready_without_changes',
            'hospitals.emergency_procurement',
            'manufacturer.containment_complete',
            'release_team.restart_release',
            'deliveries.first_arrival',
        )
    ] == pytest.approx([240, 240, 240, 240, 264])
    assert readings(r, WORK, [100])[WORK[0]] == pytest.approx([294])
    assert 'release_team.ordinary_work_done' not in events


def test_routine_review_can_include_a_finite_extra_task():
    r = record(**{'release_team.records_work': 24})
    assert readings(r, WORK, [0])[WORK[0]] == pytest.approx([528])
    assert starts(r)['deliveries.first_arrival'] == 552


def test_disabled_release_keeps_qualified_inventory_and_courses_accounted():
    r = record(**{'manufacturer.release_allowed': False})
    assert 'deliveries.first_arrival' not in starts(r)
    counts = readings(
        r,
        [
            'resuscitation_patients.eligible',
            'resuscitation_patients.timely',
            'resuscitation_patients.unserved',
        ],
        [1440],
    )
    assert sum(values[0] for values in counts.values()) == pytest.approx(18000)


def test_product_check_posts_the_hold_and_the_reconciliation_work_in_one_stage():
    r = record(
        'subpar_persistent',
        **{'manufacturer.time_to_find': 24, 'release_team.product_work': 24, 'manufacturer.reset_delay': 168},
    )
    hold = 696.25
    times = starts(r)
    assert times['manufacturer.discrepancy_confirmed'] == hold
    assert times['release_team.reconciled_against_product'] == 840
    assert times['deliveries.arrival_after_reconciliation'] == 864
    keys = [
        *WORK,
        'deliveries.state',
        'resuscitation_reserve.stock',
        'resuscitation_reserve.held',
        'other_care_reserve.held',
    ]
    obs = readings(r, keys, [hold - 0.001, hold, hold + 1, 840, 864])
    assert obs['deliveries.state'] == ('ARRIVING', 'HELD', 'HELD', 'HELD', 'ARRIVING')
    assert obs[WORK[1]] == pytest.approx([0, 24, 23, 0, 0])
    assert obs[WORK[2]][:2] == pytest.approx([24, 0])
    assert obs['resuscitation_reserve.held'][:2] == pytest.approx([0, 6.25])
    assert obs['other_care_reserve.held'][:2] == pytest.approx([0, 0])
    assert obs['resuscitation_reserve.stock'][0] - obs['resuscitation_reserve.stock'][1] == pytest.approx(
        6.25
    )


@pytest.mark.parametrize(
    ('reset_delay', 'expected_time'),
    [(0, 672), (168, 696.25), (24.25, 696.25)],
)
def test_credentials_are_revoked_on_a_confirmed_hold_or_the_scheduled_reset(reset_delay, expected_time):
    r = record(
        'subpar_persistent',
        **{'manufacturer.time_to_find': 24, 'manufacturer.reset_delay': reset_delay},
    )
    assert [entry.t for entry in r.entries('start', 'manufacturer.credentials_reset')] == pytest.approx(
        [672 + reset_delay], abs=1e-9, rel=0
    )
    values = readings(r, ['release_systems.credentials'], [expected_time - 0.001, expected_time, 1440])
    assert values['release_systems.credentials'] == ('UNCHANGED', 'RESET', 'RESET')


@pytest.mark.parametrize('ulp', [-2, 2])
def test_holding_an_empty_reserve_uses_its_accepted_balance(monkeypatch, ulp):
    from napkin.engine import edits_for
    from napkin.engine.timeline import run, stocks
    from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model

    monkeypatch.setattr(stocks, 'LEDGER_PROBE', ulp)
    m = model()
    changes = {'manufacturer.time_to_find': 24, 'manufacturer.reset_delay': 168}
    config = m.configure('subpar_persistent', edits_for(m, {'set': changes}))
    # Run the numerical probe directly since the normal run store contains unperturbed results.
    r = run(m.program, config)
    assert r.failure is None and r.end == 1440
    hold = starts(r)['manufacturer.discrepancy_confirmed']
    assert starts(r)['manufacturer.credentials_reset'] == pytest.approx(840, abs=1e-9, rel=0)
    assert readings(r, ['release_systems.credentials'], [hold])['release_systems.credentials'] == ('RESET',)
    at_hold = readings(r, ['other_care_reserve.held', 'resuscitation_reserve.held'], [hold])
    assert at_hold['other_care_reserve.held'] == pytest.approx([0], abs=1e-6)
    assert at_hold['resuscitation_reserve.held'] == pytest.approx([6.25])


@pytest.mark.parametrize(
    ('name', 'notice_hours', 'review_hours', 'clearance', 'release'),
    [
        ('fixed_quality_review', [72, 312], [72, 408], 744, 744),
        ('followup_quality_review', [72, 648], [72, 648], 984, 984),
        ('expedited_quality_review', [72, 312], [72, 312], 480, 672),
    ],
)
def test_quality_review_clock_enters_release_and_downstream_product_checks(
    name, notice_hours, review_hours, clearance, release
):
    r = record(name)
    assert r.failure is None and r.end == 1440
    assert [e.t for e in r.entries('start', 'quality_review.notice')] == notice_hours
    assert [e.t for e in r.entries('start', 'quality_review.review')] == review_hours
    assert starts(r)['release_team.restart_release'] == release
    assert starts(r)['deliveries.first_arrival'] == release + 24
    assert starts(r)['manufacturer.credentials_reset'] == release + 24
    assert starts(r)['manufacturer.discrepancy_confirmed'] == release + 216.25
    result = readings(r, ['quality_review.cleared_at', 'quality_review.completed'], [r.end])
    assert result['quality_review.cleared_at'] == (clearance,)
    assert result['quality_review.completed'] == (2,)


def test_seeded_reviews_compare_both_schedules_and_staffing_under_the_same_demand():
    from napkin.spread import spread
    from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model

    paths = ['quality_review.effort', 'quality_review.gap', 'quality_review.cleared_at']
    m = model()
    by_run = {}
    for name, capacity in [
        ('fixed_quality_review', 1),
        ('followup_quality_review', 1),
        ('expedited_quality_review', 2),
    ]:
        result = spread(m, paths, run=name, samples=3, seed=23)
        assert result.refused is None and len(result.samples) == 3
        demand = {}
        for sample in result.samples:
            (effort,), (gap,), (cleared,) = sample.values
            assert 288 <= effort <= 384 and 180 <= gap <= 300
            demand[sample.seed] = effort, gap
            duration = effort / capacity
            second_start = duration + gap if name == 'followup_quality_review' else max(gap, duration)
            assert cleared == pytest.approx(72 + second_start + duration, abs=1e-8, rel=0)
        by_run[name] = demand
    fixed = by_run['fixed_quality_review']
    assert fixed == by_run['expedited_quality_review'] == by_run['followup_quality_review']
    assert len({effort for effort, _ in fixed.values()}) == len({gap for _, gap in fixed.values()}) == 3


@pytest.mark.parametrize(('window', 'accepted', 'cleared'), [(240, 1, 408), (241, 2, 1080)])
def test_intake_closes_at_the_named_hour_and_review_effort_changes_clearance(window, accepted, cleared):
    r = record(
        'fixed_quality_review',
        **{'quality_review.intake_window': window, 'quality_review.followup_effort': 2},
    )
    assert r.failure is None and r.end == 1440
    values = readings(
        r, ['quality_review.received', 'quality_review.completed', 'quality_review.cleared_at'], [1440]
    )
    assert values['quality_review.received'] == values['quality_review.completed'] == (accepted,)
    assert values['quality_review.cleared_at'] == (cleared,)


@pytest.mark.parametrize(
    ('name', 'limit', 'notices', 'reviews', 'clearance'),
    [
        ('fixed_quality_review', 1, [70], [70], 238),
        ('fixed_quality_review', 3, [70, 118, 166], [70, 238, 406], 574),
        ('followup_quality_review', 3, [70, 286, 502], [70, 286, 502], 670),
        ('fixed_quality_review', 3, [], [], None),
    ],
)
def test_notice_limit_and_first_delay_follow_the_procurement_clock(name, limit, notices, reviews, clearance):
    r = record(
        name,
        **{
            'hospitals.start_delay': 60,
            'quality_review.first_delay': 10,
            'quality_review.notice_limit': limit,
            'quality_review.capacity': 2,
            'quality_review.interval': 48,
            'quality_review.intake_window': 960 if notices else 9,
        },
    )
    assert r.failure is None and r.end == 1440
    assert [e.t for e in r.entries('start', 'quality_review.notice')] == notices
    assert [e.t for e in r.entries('start', 'quality_review.review')] == reviews
    assert starts(r).get('quality_review.clearance') == clearance


def test_notice_arriving_as_a_review_finishes_starts_one_new_review():
    r = record(
        'fixed_quality_review',
        **{
            'quality_review.notice_limit': 3,
            'quality_review.capacity': 2,
            'quality_review.interval': 168,
        },
    )
    assert r.failure is None and r.end == 1440
    hours = [72, 240, 408]
    assert [e.t for e in r.entries('start', 'quality_review.notice')] == hours
    assert [e.t for e in r.entries('start', 'quality_review.review')] == hours
    assert starts(r)['quality_review.clearance'] == 576


def test_future_notice_has_no_effect_on_release_inventory_or_supply():
    baseline = record('subpar_persistent_human')
    future = record(
        'fixed_quality_review', **{'quality_review.first_delay': 1440, 'records.released_lot': 'CLEAR'}
    )
    assert future.failure is None and future.end == baseline.end == 1440
    assert 'quality_review.notice' not in starts(future)
    for event in (
        'release_team.restart_release',
        'deliveries.first_arrival',
        'manufacturer.credentials_reset',
    ):
        assert starts(future)[event] == starts(baseline)[event]
    paths = ['deliveries.delivery_rate', 'other_care_reserve.stock', 'other_care_reserve.deficit']
    assert readings(future, paths, [72, 671, 672, 695, 696, 1440]) == readings(
        baseline, paths, [72, 671, 672, 695, 696, 1440]
    )


def test_late_notice_pauses_and_resumes_hospital_supply_after_transport():
    r = record(
        'fixed_quality_review',
        **{
            'quality_review.notice_limit': 1,
            'quality_review.first_delay': 700,
            'records.released_lot': 'CLEAR',
        },
    )
    assert r.failure is None and r.end == 1440
    events = starts(r)
    assert (events['release_team.restart_release'], events['deliveries.first_arrival']) == (672, 696)
    assert (events['quality_review.notice'], events['quality_review.clearance']) == (772, 1108)
    times = [771, 772, 795, 796, 1108, 1131, 1132]
    values = readings(
        r, ['quality_review.cleared', 'deliveries.available', 'other_care_reserve.unmet_rate'], times
    )
    assert values['quality_review.cleared'] == (True, False, False, False, True, True, True)
    assert values['deliveries.available'] == (True, True, True, False, False, False, True)
    assert values['other_care_reserve.unmet_rate'] == pytest.approx([0, 0, 0, 25, 25, 25, 0])
