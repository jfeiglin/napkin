"""Properties that every place of the package keeps: each resident is counted once and the accounts are
bounded, delivered and unserved water partition normal use, the person-days follow the unserved water, the
attacker's watch adds rework only with hidden access and the AI adds more than the human team, and every
advisory ends. On three places of different shapes (a network of sales, a buyer with two sellers, one
system), edited studies show that a first move that stops nothing interrupts nobody, operators who meet use
by hand bridge the outage, no controls crews leave the controls wiped, removing the credential before any
restoration stops every strike, a seller short of water serves its own customers first, and no spares hold
the replacement work."""

import pytest

from napkin.engine import sample_result
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.tests.water_service import person_days
from tests.helpers import catalogue_model, catalogue_study

RUN = 'delayed_kept'
QUIET = 'delayed_none'
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
# The times, in hours, at which the accounts are checked besides the end of the run: the start, the
# first days and weeks, and the first two months.
TIMES = (0, 24, 72, 168, 336, 720, 1440)


def final(sid, edits=None, run=RUN):
    study = catalogue_study(sid, edits, runs=[run] if edits else None)
    assert study.admissible, [d for d in study.diagnostics if d.get('severity') == 'error']
    return study, sample_result(study)['runs'][run]['reporting_points']['final']['values']


def for_systems(sid, **fields):
    return {f'{system}.{name}': value for system in family.systems(sid) for name, value in fields.items()}


@pytest.mark.parametrize('sid', PLACES)
def test_each_resident_is_counted_once_and_the_accounts_are_bounded(sid):
    """At every reporting time the people without service and the people under an advisory are among the
    people the study follows, who are the people of the place's homes; the share served is a share; and the
    person-days and the hospitals' constrained hours never pass what the horizon allows."""
    study = catalogue_study(sid)
    horizon = study.model.time['horizon']
    asked = [t for t in TIMES if t < horizon]
    report = sample_result(study, asked)['runs'][RUN]
    inputs = study.runs[RUN]['resolved'].values
    people = sum(inputs[f'{home}.population'] for home in family.homes(sid).values())
    hospitals = sum(inputs[f'{h}.facilities'] for h in family.hospitals(sid).values())
    # The report gives each time that it asks for, then the end of the run.
    assert [point['t'] for point in report['reporting_points'].values()] == [*map(float, asked), horizon]
    for point in report['reporting_points'].values():
        values = point['values']
        assert values['people_followed'] == pytest.approx(people, rel=1e-12)
        assert 0 <= values['people_interrupted_now'] <= people + 1e-6
        assert 0 <= values['people_under_advisory'] <= people + 1e-6
        assert 0 <= values['restored_share'] <= 1 + 1e-9
        assert 0 <= values['person_days_lost'] <= people * horizon / 24 + 1e-6
        assert 0 <= values['hospital_hours_constrained'] <= hospitals * horizon + 1e-6


@pytest.mark.parametrize('sid', PLACES)
def test_delivered_and_unserved_water_partition_normal_use(sid):
    """A system delivers at most what its customers use and counts the rest as unserved, so over the run
    the water delivered and the water unserved add to its normal use."""
    study = catalogue_study(sid)
    run = study.runs[RUN]
    horizon = study.model.time['horizon']
    env = run['trajectory'].env_at(horizon)
    inputs = run['resolved'].values
    for system in family.systems(sid):
        use = inputs[f'{system}.demand'] * horizon
        assert env[f'{system}.delivered'] + env[f'{system}.unserved'] == pytest.approx(
            use, rel=1e-6, abs=1e-6
        )
        assert env[f'{system}.unserved'] >= 0


@pytest.mark.parametrize('sid', PLACES)
def test_the_person_days_follow_the_unserved_water(sid):
    """A system's people are without their normal service in the proportion of the water it cannot deliver,
    so the person-days lost are each system's people times its unserved water over its normal use, summed
    over the systems that serve people."""
    study, values = final(sid)
    run = study.runs[RUN]
    env = run['trajectory'].env_at(study.model.time['horizon'])
    inputs = run['resolved'].values
    expected = sum(
        person_days(inputs[f'{home}.population'], env[f'{system}.unserved'] / inputs[f'{system}.demand'])
        for system, home in family.homes(sid).items()
    )
    assert values['person_days_lost'] == pytest.approx(expected, rel=1e-6, abs=1e-6)


@pytest.mark.parametrize('sid', PLACES)
def test_the_ai_adds_more_rework_than_the_human_team_and_no_access_adds_none(sid):
    """Without a hidden credential nobody strikes the restored controls. The AI strikes every restoration
    until the credential is removed; the human team strikes later and reaches fewer controller makes."""
    report = sample_result(catalogue_study(sid))['runs']
    rework = {run: report[run]['reporting_points']['final']['values']['rework_caused'] for run in report}
    assert rework[QUIET] == 0
    assert rework[RUN] > 0
    assert rework['delayed_kept_human'] < rework[RUN]


@pytest.mark.parametrize('sid', PLACES)
def test_every_advisory_ends_by_the_end_of_the_run(sid):
    """Every system's controls and supply come back within the run, so every boil-water advisory has ended
    by its end."""
    report = sample_result(catalogue_study(sid))['runs']
    for run, item in report.items():
        assert item['reporting_points']['final']['values']['people_under_advisory'] == 0, run


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_a_first_move_that_stops_nothing_interrupts_nobody(sid):
    """Where the wiped controls stop no production and no pumping, every system keeps delivering from its
    own production or its sellers', so nobody loses service, no water goes undelivered, no advisory is
    issued and the area loses nothing; the attacker's strikes still add work for the crews."""
    _study, values = final(sid, {'set': for_systems(sid, treat_disabled=0, pump_disabled=0)})
    assert values['person_days_lost'] == 0
    assert values['unserved_volume'] == 0
    assert values['economic_loss'] == 0
    assert values['people_under_advisory'] == 0
    assert values['rework_caused'] > 0


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_operators_who_meet_use_by_hand_bridge_the_outage(sid):
    """Where every system's operators run the plants by hand at full production within a quarter of an
    hour, and the pumps keep running, the stored water covers the switch, so no customer loses service."""
    _study, values = final(
        sid, {'set': for_systems(sid, manual_share=1, pump_disabled=0, activation_delay=0.25)}
    )
    assert values['person_days_lost'] == 0
    assert values['unserved_volume'] == 0
    assert values['restored_share'] == pytest.approx(1)


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_without_controls_crews_the_controls_stay_wiped(sid):
    """With no capacity in the controls crews, no system's controls come back, so the attacker has nothing
    to strike again and the controls work stays outstanding."""
    study, values = final(sid, {'set': {'controls_crew.capacity': 0}})
    inputs = study.runs[RUN]['resolved'].values
    loads = sum(inputs[f'{system}.controls_load'] for system in family.systems(sid))
    assert values['rework_caused'] == 0
    assert values['work_remaining'] >= loads * (1 - 1e-9)


@pytest.mark.deep
@pytest.mark.parametrize('sid', SHAPES)
def test_removing_the_credential_before_any_restoration_stops_every_strike(sid):
    """Responders who recognize the attack and remove the credential within two hours leave the attacker
    nothing to strike, so the run with hidden access ends as the run without it."""
    quick = {'set': {'responders.recognition_time': 1, 'responders.removal_time': 1}}
    _study, kept = final(sid, quick)
    _study, none = final(sid, quick, run=QUIET)
    assert kept['rework_caused'] == 0
    for name in ('person_days_lost', 'unserved_volume', 'economic_loss'):
        assert kept[name] == pytest.approx(none[name], rel=1e-9, abs=1e-9), name


@pytest.mark.deep
@pytest.mark.parametrize(
    'sid', [sid for sid in SHAPES if any(s in family.homes(sid) for s, _buyer in family.ties(sid).values())]
)
def test_a_seller_short_of_water_serves_its_own_customers_first(sid):
    """A seller whose plants stop, with nobody to run them by hand, empties its stored water. From then on
    it delivers to its own customers what still reaches it, up to their use, and sends its buyers only what
    is left: when that is less than its customers use, its buyers get nothing from it."""
    sellers = {seller for seller, _buyer in family.ties(sid).values()}
    edits = {'set': {**for_systems(sid, pump_disabled=0), **{f'{s}.manual_ready': False for s in sellers}}}
    study = catalogue_study(sid, edits, runs=[QUIET])
    run = study.runs[QUIET]
    inputs = run['resolved'].values
    trajectory = run['trajectory']
    # The crews are at work only after recognition and their four stages, so no plant comes back before.
    at_work = inputs['responders.recognition_time'] + sum(
        inputs[f'controls_crew.{stage}_time'] for stage in ('request', 'approval', 'travel', 'orientation')
    )
    late, later = 0.75 * at_work, 0.9 * at_work
    checked = 0
    for tie, (seller, _buyer) in family.ties(sid).items():
        supply = inputs[
            f'{seller}.bought'
        ]  # its plants are stopped: only its purchases from outside reach it
        if supply >= inputs[f'{seller}.demand']:
            continue
        a, b = trajectory.env_at(late), trajectory.env_at(later)
        assert a[f'{seller}.finished'] == pytest.approx(0, abs=1e-6), tie
        assert b[f'{seller}.exported'] - a[f'{seller}.exported'] == pytest.approx(0, abs=1e-6), tie
        delivered = b[f'{seller}.delivered'] - a[f'{seller}.delivered']
        assert delivered == pytest.approx(supply * (later - late), rel=1e-6), tie
        checked += 1
    assert checked


@pytest.mark.deep
def test_no_spares_and_a_late_batch_hold_the_replacement_work():
    """With no replacement controllers in stock and a batch that arrives after the run, a small system's
    replacement work cannot be done, so its work stays outstanding where the default stock lets the crews
    finish it."""
    sid = 'water_controls_wipe:jamestown'
    if sid not in PLACES:
        pytest.skip('the family has no place with a small system')
    model = catalogue_model(sid)
    small = [s for s in family.systems(sid) if model.run_values(RUN).get(f'{s}.replace_load', 0) > 0]
    assert small
    study, values = final(sid, {'set': {'parts.spares_on_hand': 0, 'parts.lead_time': 4000}})
    inputs = study.runs[RUN]['resolved'].values
    assert values['work_remaining'] >= sum(inputs[f'{s}.replace_load'] for s in small) * (1 - 1e-9)
    _study, default = final(sid)
    assert default['work_remaining'] == 0
