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
