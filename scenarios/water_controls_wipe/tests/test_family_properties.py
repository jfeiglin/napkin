"""Service balances, repair and advisory properties across the water family.

The historical model predicted extra work from two actors' behavior. The current package accepts an
observed field report. The corresponding controls check zero extra work without a report, the exact
work it adds when supplied and an unchanged report when recognition is moved earlier. Civilian water,
resident, hospital, crew, parts and wholesale accounting are still checked from each utility's run.
"""

import pytest

import napkin
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.tests.water_service import person_days
from tests.helpers import catalogue_model, catalogue_study

RUN = 'delayed_none'
PLACES = family.places()
SHAPES = [
    sid
    for sid in (
        'water_controls_wipe:washington_dc',
        'water_controls_wipe:jamestown',
        'water_controls_wipe:lumberton',
    )
    if sid in PLACES
]
TIMES = (0, 24, 72, 168, 336, 720, 1440)
ACCOUNTS = (
    'people_followed',
    'people_interrupted_now',
    'people_under_advisory',
    'restored_share',
    'person_days_lost',
    'hospital_hours_constrained',
)


def completed(sid, settings=None, run=RUN):
    edits = {'set': settings} if settings else None
    record = catalogue_study(sid, edits, runs=[run])[run]
    assert record.end == catalogue_model(sid).configuration.request.horizon and record.failure is None
    return record


def samples(sid, record, keys, hours):
    return {row.path: row.values for row in napkin.read(record, catalogue_model(sid).program, keys, hours)}


def at(sid, record, keys, hour):
    return {path: readings[0] for path, readings in samples(sid, record, keys, [hour]).items()}


def for_systems(sid, **fields):
    return {f'{system}.{name}': value for system in family.systems(sid) for name, value in fields.items()}


@pytest.mark.parametrize('sid', PLACES)
def test_each_resident_is_counted_once_and_the_accounts_are_bounded(sid):
    record = completed(sid)
    horizon = record.end
    hours = [*(t for t in TIMES if t < horizon), horizon]
    populations = [f'{home}.population' for home in family.homes(sid).values()]
    facilities = [f'{hospital}.facilities' for hospital in family.hospitals(sid).values()]
    data = at(sid, record, [*populations, *facilities], 0)
    people = sum(data[k] for k in populations)
    hospitals = sum(data[k] for k in facilities)
    readings = samples(sid, record, ACCOUNTS, hours)
    for hour, (followed, interrupted, advisory, served, days, hospital_hours) in zip(
        hours, zip(*readings.values(), strict=True), strict=True
    ):
        assert followed == pytest.approx(people, rel=1e-12)
        assert 0 <= interrupted <= people + 1e-6
        assert 0 <= advisory <= people + 1e-6
        assert 0 <= served <= 1 + 1e-9
        assert 0 <= days <= people * hour / 24 + 1e-6
        assert 0 <= hospital_hours <= hospitals * hour + 1e-6


@pytest.mark.parametrize('sid', PLACES)
def test_delivered_and_unserved_water_partition_normal_use(sid):
    record = completed(sid)
    for system in family.systems(sid):
        # Authored units are Mgal/day for demand, Mgal for the stocks and hours for the clock.
        keys = [f'{system}.{measure}' for measure in ('demand', 'delivered', 'unserved')]
        demand, delivered, unserved = at(sid, record, keys, record.end).values()
        assert delivered + unserved == pytest.approx(demand * record.end / 24, rel=1e-6, abs=1e-6), system
        assert unserved >= 0


@pytest.mark.parametrize('sid', PLACES)
def test_the_person_days_follow_the_unserved_water(sid):
    record = completed(sid)
    expected = 0
    for system, home in family.homes(sid).items():
        paths = [f'{home}.population', f'{system}.demand', f'{system}.unserved']
        people, daily_demand, unserved = at(sid, record, paths, record.end).values()
        expected += person_days(people, 24 * unserved / daily_demand)
    assert at(sid, record, ['person_days_lost'], record.end)['person_days_lost'] == pytest.approx(
        expected, rel=1e-6, abs=1e-6
    )


@pytest.mark.parametrize('sid', PLACES)
def test_extra_controls_work_requires_an_observed_service_report(sid):
    record = completed(sid)
    starts = [e.owner for e in record.entries('start') if '.observed_setback#' in e.owner]
    assert not starts
    assert at(sid, record, ['rework_caused'], record.end)['rework_caused'] == 0


@pytest.mark.parametrize('sid', PLACES)
def test_every_advisory_ends_by_the_end_of_the_run(sid):
    for run in catalogue_model(sid).declared.runs:
        record = completed(sid, run=run.name)
        assert at(sid, record, ['people_under_advisory'], record.end)['people_under_advisory'] == 0, run.name


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_a_reported_controls_outage_that_stops_no_water_interrupts_nobody(sid):
    settings = for_systems(sid, treat_disabled=0, pump_disabled=0)
    utility = family.systems(sid)[0]
    settings.update(
        {
            f'{utility}.has_setback': True,
            f'{utility}.setback_at': '4 h',
            f'{utility}.setback_work': '10 work_h',
        }
    )
    record = completed(sid, settings)
    keys = ['person_days_lost', 'unserved_volume', 'economic_loss', 'people_under_advisory', 'rework_caused']
    vals = at(sid, record, keys, record.end)
    assert list(vals.values()) == pytest.approx([0, 0, 0, 0, 10], abs=1e-9)


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_operators_who_meet_use_by_hand_bridge_the_outage(sid):
    record = completed(sid, for_systems(sid, manual_share=1, pump_disabled=0, activation_delay=0.25))
    measures = at(sid, record, ['person_days_lost', 'unserved_volume', 'restored_share'], record.end)
    assert list(measures.values()) == pytest.approx([0, 0, 1], abs=1e-9)


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_an_unstaffed_repair_queue_keeps_its_outstanding_controls_work(sid):
    record = completed(sid, {'controls_crew.capacity': 0})
    for system in family.systems(sid):
        keys = [
            f'{system}.{field}'
            for field in ('controls_load', 'controls_work', 'controls_done', 'rework_caused')
        ]
        load, remaining, done, extra = at(sid, record, keys, record.end).values()
        assert (remaining, done, extra) == pytest.approx((load, 0, 0), abs=1e-6)


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_earlier_recognition_keeps_the_supplied_field_report_and_its_work(sid):
    utility = family.systems(sid)[0]
    reported = f'{utility}.observed_setback'
    common = {
        f'{utility}.has_setback': True,
        f'{utility}.setback_at': '4 h',
        f'{utility}.setback_work': '10 work_h',
    }
    keys = [f'{utility}.rework_caused', 'rework_caused']
    for recognition in (1, 24):
        record = completed(
            sid, {**common, 'responders.recognition_time': recognition, 'responders.removal_time': 1}
        )
        onset = {e.owner.split('#')[0]: e.t for e in record.entries('start')}
        assert onset['responders.recognized'] == recognition
        assert onset[reported] == 4
        for readings in samples(sid, record, keys, [3, 4, record.end]).values():
            assert readings == pytest.approx([0, 10, 10])


@pytest.mark.deep
@pytest.mark.parametrize(
    'sid', [s for s in SHAPES if any(seller in family.homes(s) for seller, _ in family.ties(s).values())]
)
def test_a_seller_short_of_water_serves_its_own_customers_first(sid):
    sellers = {seller for seller, _ in family.ties(sid).values()}
    settings = {
        **for_systems(sid, pump_disabled=0),
        **{f'{seller}.manual_ready': False for seller in sellers},
    }
    record = completed(sid, settings)
    crew_clocks = [
        'responders.recognition_time',
        *(f'controls_crew.{stage}_time' for stage in ('request', 'approval', 'travel', 'orientation')),
    ]
    at_work = sum(at(sid, record, crew_clocks, 0).values())
    early, late = 0.75 * at_work, 0.9 * at_work
    checked = 0
    for seller in sellers:
        bought, demand = at(sid, record, [f'{seller}.bought', f'{seller}.demand'], 0).values()
        if bought >= demand:
            continue
        keys = [f'{seller}.{k}' for k in ('finished', 'exported', 'delivered')]
        stock, exported, delivered = samples(sid, record, keys, [early, late]).values()
        assert stock[0] == pytest.approx(0, abs=1e-6)
        assert exported[1] - exported[0] == pytest.approx(0, abs=1e-6)
        assert delivered[1] - delivered[0] == pytest.approx(bought * (late - early) / 24, rel=1e-6)
        checked += 1
    assert checked


@pytest.mark.deep
def test_no_spares_and_a_late_batch_hold_the_replacement_work():
    sid = 'water_controls_wipe:jamestown'
    if sid not in PLACES:
        pytest.skip('the selected variants do not include the replacement-parts example')
    record = completed(sid, {'parts.spares_on_hand': 0, 'parts.lead_time': '4000 h'})
    loads = at(sid, record, [f'{s}.replace_load' for s in family.systems(sid)], 0)
    required = sum(loads.values())
    assert required > 0
    assert at(sid, record, ['work_remaining'], record.end)['work_remaining'] >= required * (1 - 1e-9)
    default = completed(sid)
    assert at(sid, default, ['work_remaining'], default.end)['work_remaining'] == pytest.approx(0, abs=1e-5)
