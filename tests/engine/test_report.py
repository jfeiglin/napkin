"""The report of a run (`napkin/engine/report.py`): the values that a caller selects at the times that it
selects (D10), each with its unit and its label; status displays; reporting lags and their proof; the
evidence trail; the near-ties of the run; and a run that stopped. It ports the old reporting, timeline
report, evidence trail, run evidence, paused result and output category tests onto the record. Every
expected value is worked by hand: a rate times a time, the closed form of an exponential, the mean of a
ramp over a window.
"""

from __future__ import annotations

import math
import textwrap

import pytest

from napkin.engine import run
from napkin.engine.report import Lag, Shown, report
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint
from napkin.program.config import Configuration, InputValue, Request
from napkin.program.record import Unavailable
from tests.engine.test_checkpoints import SCENARIOS
from tests.program.examples import EXAMPLES, UNITS


def compiled(text, units=UNITS):
    return compile_text(textwrap.dedent(text), units)


def reported(model, paths, times, configuration=None, **settings):
    configuration = configuration or model.configuration
    record = run(model.program, configuration)
    return report(record, model.program, configuration, paths, times, model=model.declared, **settings)


TANK = """
    scenario "Tank"
        horizon 4 h
    tank:
        water: kL = 8 kL in [0 kL,]  @measured
            "Water in the tank"
    clinic:
        flow delivery: tank.water -> SINK
            "Delivery to the clinic"
            request = 1.5 kL/h
    record measured: source "A gauge reading."
    """


def test_a_value_comes_in_its_declared_unit_with_its_label():
    """The tank holds 8 kL and delivers 1.5 kL/h: 5 kL at 2 h. A field of a flow takes the flow's text."""
    model = compiled(TANK, {**UNITS, 'kL': ({'volume': 1}, 1000)})
    found = reported(model, ['tank.water', 'clinic.delivery.actual_rate'], [0, 2])
    water, rate = found.values
    assert (water.unit, water.label, water.values) == ('kL', 'Water in the tank', pytest.approx((8, 5)))
    assert (rate.unit, rate.label, rate.values) == (
        'kL/h',
        'Delivery to the clinic',
        pytest.approx((1.5, 1.5)),
    )
    assert found.times == (0.0, 2.0) and found.end == 4 and found.stopped is None
    assert water.lag is None and water.note is None


def test_a_label_changes_no_value():
    """The old output categories were tags that changed no value; so is a label now."""
    units = {**UNITS, 'kL': ({'volume': 1}, 1000)}
    plain = reported(compiled(TANK, units), ['tank.water'], [1, 3]).values[0]
    other = reported(compiled(TANK.replace('Water in the tank', 'Tank water'), units), ['tank.water'], [1, 3])
    assert other.values[0].values == plain.values and other.values[0].label == 'Tank water'


def test_a_time_outside_the_run_is_refused():
    model = compiled(TANK, {**UNITS, 'kL': ({'volume': 1}, 1000)})
    with pytest.raises(ValueError, match='from 0 h to the horizon'):
        reported(model, ['tank.water'], [5])
    with pytest.raises(ValueError, match='which the report does not select'):
        reported(model, ['tank.water'], [1], lags={'clinic.delivery.actual_rate': Lag(2, 6)})


DECAY = """
    scenario "Decay"
        horizon 20 h
    s:
        pending: person = 100 person in [0 person,]
        finished: person = 0 person in [0 person,]
            "People who finished"
        flag: person = 0 person
        flow finish: this.pending -> this.finished
            request = formula(this.pending / (10 h))
        mark = event():
            after 7 h:
                this.flag = 1 person
    s.mark.start()
    """


def test_a_uniform_lag_is_the_mean_of_its_window_in_closed_form():
    """A decaying stock fills a tally, finished = 100 (1 - e^(-t/10)), and a moment at 7 h splits the
    history. The lag of 2 h to 6 h is the mean of finished over [t - 6, t - 2], which holds its value at
    time 0, zero, before it. With C(x) = 100 (x + 10 (e^(-x/10) - 1)), the integral of finished from 0
    to x, the mean is (C(max(0, t - 2)) - C(max(0, t - 6))) / 4."""
    times = [0, 1, 2, 3, 5, 6, 7, 8, 9.5, 13, 20]

    def integral(x):
        x = max(0.0, x)
        return 100 * (x + 10 * math.expm1(-x / 10))

    found = reported(compiled(DECAY), ['s.finished'], times, lags={'s.finished': Lag(2, 6)}).values[0]
    assert found.lag == Lag(2, 6) and 's.finish of s' in found.note
    for t, value in zip(times, found.values, strict=True):
        assert value == pytest.approx((integral(t - 2) - integral(t - 6)) / 4, rel=1e-8, abs=1e-7), t


SERVICE = """
    scenario "Service"
        horizon 24 h
    service:
        stock: person = 100 person in [0 person,]
        served: person = 0 person in [0 person,]
        flow serve: this.stock -> this.served
            request = 1 person/h
        impulse = event():
            after 5 h:
                move 2 person from this.stock to this.served
    service.impulse.start()
    """


def test_a_fixed_delay_and_a_window_over_a_ramp_and_a_jump():
    """One person is served an hour and two more at once at 5 h: served(s) = s + 2 [s >= 5]. At 7 h a
    fixed 3 h delay reads served(4) = 4; a window of 1 h to 3 h is the mean over [4, 6], (10 + 2) / 2 =
    6, half of the jump; at 1 h a fixed 3 h delay reads the value at time 0."""
    paths = ['service.served']
    model = compiled(SERVICE)
    fixed = reported(model, paths, [1, 7], lags={'service.served': Lag(3, 3)}).values[0]
    window = reported(model, paths, [7], lags={'service.served': Lag(1, 3)}).values[0]
    assert fixed.values == pytest.approx((0, 4))
    assert window.values == pytest.approx((6,))


def test_a_lag_of_a_value_that_can_fall_is_refused_and_the_plain_read_stays():
    """Spec: `unserved_now` falls when service returns, so its lag has a diagnostic; `unserved_volume`
    qualifies. North misses 10 L/h until 5 h."""
    example = EXAMPLES['water_service_returns']()
    record = run(example.program, example.configuration)
    lags = {'unserved_now': Lag(2, 6), 'unserved_volume': Lag(2, 6)}
    found = report(record, example.program, example.configuration, list(lags), [4, 6], lags=lags)
    now, volume = found.values
    assert now.lag is None and now.values == pytest.approx((10, 0))
    assert now.note.startswith('the lag is refused: unserved_now can fall: ')
    # The volume is 10 s until 5 h: its mean over [-2, 2] is 20 / 4 and over [0, 4] is 80 / 4.
    assert volume.lag == Lag(2, 6) and volume.values == pytest.approx((5, 20))


CREW = """
    scenario "Crews"
        horizon 6 h
    Crew:
        work_state: enum[WAITING, WORKING, DONE] = WAITING
        status ok when this.work_state == DONE
            "Repairs are complete."
        status degraded when this.work_state == WORKING
            "Crews are carrying out repairs."
        status degraded
            "Crews are waiting for access."
        work = event():
            after 2 h:
                this.work_state = WORKING
            after 2 h:
                this.work_state = DONE
    north: Crew
    south: Crew
    north.work.start()
    """


def test_a_status_display_reads_the_rating_and_the_text_of_its_case():
    """Spec: the last two cases share a rating and give different explanations. North starts its work,
    south waits all along; each member has its own display."""
    found = reported(
        compiled(CREW), ['north.status', 'south.status'], [1, 3, 5], lags={'north.status': Lag(2, 6)}
    )
    north, south = found.values
    waiting = Shown('degraded', 'Crews are waiting for access.', 'Crew.status.case[2]')
    assert north.values == (
        waiting,
        Shown('degraded', 'Crews are carrying out repairs.', 'Crew.status.case[1]'),
        Shown('ok', 'Repairs are complete.', 'Crew.status.case[0]'),
    )
    assert south.values == (waiting, waiting, waiting)
    assert north.lag is None and 'a lag averages a number' in north.note


def test_a_stopped_run_reads_up_to_its_stop_and_says_so():
    """A tank of 10 L drains at 2 L/h and the run stops at a breakpoint at 2 h: the report of its record
    so far reads 8 L and 6 L at 1 h and 2 h, and a time after the stop is unavailable with the reason."""
    case = SCENARIOS['family']()
    stopped = run(case.program, case.configuration, (Breakpoint('tank.tick.step[1]'),))
    found = report(stopped.record, case.program, case.configuration, ['tank.water'], [1, 2, 3])
    assert found.end == 2 and found.stopped.startswith(
        'the run stopped at 2 h at the breakpoint tank.tick.step[1]'
    )
    one, two, three = found.values[0].values
    assert (one, two) == pytest.approx((8, 6))
    assert isinstance(three, Unavailable) and three.reason == found.stopped


def test_a_failed_run_reads_up_to_its_failure():
    """The tank fills at 1 L/h and must hold at most 5 L: the run fails at 5 h."""
    model = compiled(
        """
        scenario "Fill"
            horizon 10 h
        tank:
            water: L = 0 L in [0 L,]
            flow fill: SOURCE -> this.water
                request = 1 L/h
            assert this.water <= 5 L
                "At most five litres"
        """
    )
    found = reported(model, ['tank.water'], [4, 5, 6])
    assert found.end == pytest.approx(5) and found.stopped.startswith('the run failed at 5 h: ')
    four, five, six = found.values[0].values
    assert (four, five) == pytest.approx((4, 5)) and isinstance(six, Unavailable)


PLANT = """
    scenario "Plant"
        horizon 4 h
    plant:
        input open: bool = false  @fixture
            "The access road is open"
        input cap: L = 10 L in [0 L,]  @fixture
        stock: L = 10 L in [0 L, this.cap]  @fixture
            "Spare parts"
        used: L = 0 L in [0 L,]
            "Parts used"
        flow idle: this.stock -> SINK
            request = 0 L/h
        repair = event():
            when this.open and t >= 1 h:
                this.repair.start()
                reset when false
            after 1 h:
                move 2 L from this.stock to this.used
    record fixture: assumption "A fixture."
    """


def trail_of(found):
    return {(used.kind, used.origin): used for used in found.trail}


def test_an_event_that_cannot_start_is_no_part_that_the_run_exercised():
    """D16: with the road closed the repair cannot start (a proof); its stage did not commit (the
    trace); its trigger is read only through them. The idle flow moved nothing."""
    model = compiled(PLANT)
    found = reported(model, ['plant.used', 'plant.stock'], [4])
    used, stock = (trail_of(value) for value in found.values)
    repair = used['event', 'plant.repair']
    assert not repair.exercised and repair.why.startswith('it cannot start under this configuration: ')
    assert not used['stage', 'plant.repair.step[0]'].exercised
    assert used['stage', 'plant.repair.step[0]'].why == 'it did not commit in this run'
    assert (
        used['trigger', 'plant.repair.when[0]'].why
        == 'it is read only through parts that the run did not exercise'
    )
    assert used['value', 'plant.used'].exercised
    idle = stock['flow', 'plant.idle']
    assert (idle.exercised, idle.why) == (False, 'it moved nothing in this run')


def test_the_same_parts_are_exercised_when_the_event_can_start():
    model = compiled(PLANT)
    open_road = Configuration(Request(4), inputs=(InputValue('plant', 'open', True),))
    found = trail_of(reported(model, ['plant.used'], [4], configuration=open_road).values[0])
    assert (found['event', 'plant.repair'].exercised, found['event', 'plant.repair'].why) == (
        True,
        'it started at 1 h',
    )
    assert found['stage', 'plant.repair.step[0]'].why == 'it committed at 2 h'
    assert found['trigger', 'plant.repair.when[0]'].why == 'it fired at 1 h'
    assert found['value', 'plant.open'].exercised and found['value', 'plant.stock'].exercised


def test_a_trail_keeps_the_records_of_each_part_and_the_bounds_that_a_store_reads():
    """The stock cites its record and rests on the input that its upper bound reads."""
    found = reported(compiled(PLANT), ['plant.stock'], [4])
    trail = trail_of(found.values[0])
    assert trail['value', 'plant.stock'].records == ('fixture',)
    assert trail['value', 'plant.cap'].records == ('fixture',) and trail['value', 'plant.cap'].exercised
    assert found.records == (('fixture', 'assumption', 'A fixture.'),)
    assert found.values[0].label == 'Spare parts'


TOP_UP = """
    scenario "Top up"
        horizon 3 h
    tank:
        level: L = 0 L in [0 L,]
        filled: L = 0 L in [0 L,]
        flow fill: SOURCE -> this.filled
            request = 1 L/h
        top = event():
            after 1 h:
                this.level += 0.1 L
                this.level += 0.2 L
        alarm = event():
            when this.level >= 0.3 L:
                this.alarm.start()
            after 0 h
        full = event():
            when this.filled >= 2 L:
                this.full.start()
            after 0 h
    tank.top.start()
    """


def test_the_report_lists_each_near_tie_of_the_run():
    """In floats 0.1 + 0.2 exceeds 0.3 by one unit in the last place, far inside the level's tolerance,
    1e-10 of its size of 1 L: the alarm fired within tolerance of its threshold. The tally crosses 2 L
    at 2 h, moving through it, which is no near-tie."""
    found = reported(compiled(TOP_UP), ['tank.level'], [3])
    (tie,) = found.near_ties
    assert (tie.t, tie.kind, tie.part, tie.owner) == (1, 'fire', 'tank.alarm.when[0]', 'tank')
    assert tie.difference == (0.1 + 0.2) - 0.3 and tie.tolerance == pytest.approx(1e-10)
    assert 'this trigger fired within tolerance of its threshold' in tie.message


def test_a_count_of_occurrences_rests_on_its_event_and_trigger_and_can_be_lagged():
    """The siren fills at 1 L/h and rings once, when it reaches 2 L at 2 h. The count of its rings
    never falls (an occurrence stays in its event's collection), so a fixed delay of 1 h reads 0 at
    2.5 h and 1 at 3 h; the count rests on the event, the trigger, the level and the flow."""
    model = compiled(
        """
        scenario "Alarms"
            horizon 4 h
        siren:
            level: L = 0 L in [0 L,]
            flow fill: SOURCE -> this.level
                request = 1 L/h
            ring = event():
                when this.level >= 2 L:
                    this.ring.start()
                after 0 h
        rings = formula(count(siren.ring.occurrences))
            "Rings so far"
        """
    )
    (rings,) = reported(model, ['rings'], [2.5, 3], lags={'rings': Lag(1, 1)}).values
    assert rings.values == (0, 1) and rings.label == 'Rings so far' and rings.lag == Lag(1, 1)
    assert 'the occurrences of siren.ring only add to their count' in rings.note
    trail = trail_of(rings)
    assert trail['event', 'siren.ring'].why == 'it started at 2 h'
    assert trail['trigger', 'siren.ring.when[0]'].why == 'it fired at 2 h'
    assert trail['value', 'siren.level'].exercised and trail['flow', 'siren.fill'].why == 'it moved material'
