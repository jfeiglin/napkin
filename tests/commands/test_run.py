"""`napkin run`: the values of named paths at chosen times, from source, on the new engine.

Each expected value is worked out independently: the median of a PERT distribution with mpmath, the
lines of the tank of the spec by hand, the window of a yes/no by hand.
"""

from __future__ import annotations

from pathlib import Path

import mpmath
import pytest

from tests.commands.call import TANK, UNITS, napkin, package

ROOT = Path(__file__).resolve().parents[2]
PIANO_TUNERS = ROOT / 'examples' / 'piano_tuners'


def pert_median(low, mode, high):
    """The median of `pert(low, mode, high)`: low + (high - low) x, where x is the median of the beta
    distribution with alpha = 1 + 4 (mode - low) / (high - low) and beta = 1 + 4 (high - mode) /
    (high - low)."""
    with mpmath.workdps(40):
        span = mpmath.mpf(high - low)
        alpha, beta = 1 + 4 * (mode - low) / span, 1 + 4 * (high - mode) / span
        x = mpmath.findroot(
            lambda x: mpmath.betainc(alpha, beta, 0, x, regularized=True) - mpmath.mpf(1) / 2,
            (mode - low) / span,
        )
        return float(low + span * x)


def test_the_piano_tuners_do_three_tuner_years_at_the_median_rate():
    """A median run draws the median of pert(600, 1000, 1200) tunings per tuner-year; 3 tuners for
    1 year do 3 times it, which is under the 5,000 tunings that the pianos need, so the flow never
    reaches the bound of `due`."""
    median = pert_median(600, 1000, 1200)
    assert median == pytest.approx(974.5124957975274, rel=1e-12)  # mpmath at 40 digits
    done = 3 * median
    assert done < 5000


def test_napkin_run_gives_the_closed_form_of_the_piano_tuners(capsys):
    median = pert_median(600, 1000, 1200)
    found = napkin(capsys, 'run', PIANO_TUNERS, '--json', '--at', '0h,6months,1year')
    assert found.code == 0, found.err
    doc = found.doc
    assert doc['title'] == 'Piano tuners'
    assert doc['mode'] == 'median'
    assert doc['times'] == [0, 4380, 8760]
    values = doc['values']
    assert values['tuners.rate']['unit'] == 'tunings/tuner/year'
    assert values['tuners.rate']['values'] == pytest.approx([median] * 3, rel=1e-12)
    assert values['tunings_done']['unit'] == 'tunings'
    assert values['tunings_done']['values'] == pytest.approx([0, 1.5 * median, 3 * median], rel=1e-9)
    assert values['tuners.done']['values'] == pytest.approx([0, 1.5 * median, 3 * median], rel=1e-9)
    assert values['tuners.due']['values'] == pytest.approx(
        [5000, 5000 - 1.5 * median, 5000 - 3 * median], rel=1e-9
    )
    assert values['tuners.need']['values'] == [5000, 5000, 5000]
    assert values['tunings_done']['label'] == 'Tunings done in the year'
    assert doc['diagnostics'] == []


def test_napkin_run_prints_every_named_value_in_the_order_of_the_file(capsys):
    """With no --value and no --at: each value at the start and the horizon, a flow's actual rate,
    request and capacity under its line, the top-level formula last as the file writes it."""
    found = napkin(capsys, 'run', PIANO_TUNERS)
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    assert lines[0] == 'Piano tuners: a median run to 8760 h'
    assert lines[1].split() == ['unit', '0', 'h', '8760', 'h']
    rows = {line.split()[0]: line.split()[1:] for line in lines[2:]}
    assert list(rows) == [
        'tuners.rate',
        'tuners.staff',
        'tuners.need',
        'tuners.due',
        'tuners.done',
        'tuners.tune.actual_rate',
        'tuners.tune.request',
        'tuners.tune.capacity',
        'tunings_done',
    ]
    # Six significant figures: 3 times the median is 2923.537...
    assert rows['tunings_done'] == ['tunings', '0', f'{3 * pert_median(600, 1000, 1200):.6g}']
    assert rows['tunings_done'][-1] == '2923.54'
    assert rows['tuners.staff'] == ['tuner', '3', '3']


ROUTE_AND_LEGS = """\
scenario "Route and legs"
    horizon 2 h

west:
    water: L = 10 in [0, 20]

east:
    water: L = 10 in [0, 20]

channel:
    flow link: west.water <-> east.water
        request = -3 L/h
    after_link: L = 0

store:
    water: L = 100 in [0,]
    used: L = 0 in [0,]

site:
    store = store
    charge: Wh = 100 in [0,]
    flow restore:
        flow labor: this.store.water -> this.store.used
            request = 4 L/h
            capacity = 2 L/h
        flow pour: this.charge -> SINK
            request = 8 W
"""
# Litres, and watts so that the two legs of `restore` are of two units.
ROUTE_AND_LEGS_UNITS = {
    'L': UNITS['L'],
    'Wh': {'dimensions': {'energy': 1}, 'scale': 1, 'description': 'A watt hour.'},
    'W': {'dimensions': {'energy': 1, 'time': -1}, 'scale': 1, 'description': 'A watt.'},
}


def test_napkin_run_lists_a_route_and_a_flow_with_legs_in_the_order_of_the_file(tmp_path, capsys):
    """Spec, "Flows and algebraic solvers": a route's signed rate, request and capacity, then its
    legs `forward` and `backward`, each the positive part in its direction (-3 L/h reads 0 forward
    and 3 backward); a flow with legs' `served_fraction`, then each leg in its own unit (legs of 4
    L/h and 8 W at half service carry 2 L/h and 4 W); a link prints the member it names. A route
    or a leg with no capacity written lists none."""
    model = package(tmp_path / 'legs', ROUTE_AND_LEGS, ROUTE_AND_LEGS_UNITS)
    found = napkin(capsys, 'run', model)
    assert found.code == 0, found.err
    rows = {line.split()[0]: line.split()[1:] for line in found.out.splitlines()[2:]}
    assert list(rows) == [
        'west.water',
        'east.water',
        'channel.link.actual_rate',
        'channel.link.request',
        'channel.link.forward.actual_rate',
        'channel.link.forward.request',
        'channel.link.backward.actual_rate',
        'channel.link.backward.request',
        'channel.after_link',
        'store.water',
        'store.used',
        'site.store',
        'site.charge',
        'site.restore.served_fraction',
        'site.restore.labor.actual_rate',
        'site.restore.labor.request',
        'site.restore.labor.capacity',
        'site.restore.pour.actual_rate',
        'site.restore.pour.request',
    ]
    assert rows['channel.link.actual_rate'] == ['L/h', '-3', '-3']
    assert rows['channel.link.forward.actual_rate'] == ['L/h', '0', '0']
    assert rows['channel.link.backward.actual_rate'] == ['L/h', '3', '3']
    assert rows['east.water'] == ['L', '10', '4']
    assert rows['site.store'] == ['store', 'store']
    assert rows['site.restore.served_fraction'] == ['0.5', '0.5']
    assert rows['site.restore.labor.actual_rate'] == ['L/h', '2', '2']
    assert rows['site.restore.pour.actual_rate'] == ['W', '4', '4']
    assert rows['site.charge'] == ['Wh', '100', '92']


DELIVERIES = """\
scenario "Deliveries"
    horizon 5 h

tank:
    water: L = 100 in [0,]
    deliver = event():
        flow pipe: this.water -> SINK
            request = 2 L/h
        after 1 h
        when t >= 1 h:
            this.deliver.start()
            reset when false
        when t >= 3 h:
            this.deliver.start()
            reset when false

started = formula(count(tank.deliver.occurrences))
current = formula(count(tank.water.outflow.flows))
requested = formula(sum(tank.water.outflow.flows.request))
"""


def test_napkin_run_lists_no_occurrence_and_reads_one_by_its_id(tmp_path, capsys):
    """Spec, "Occurrences and their history": two deliveries of 2 L/h, each for an hour, from 1 h and
    3 h. The default listing holds the named values only (the history table of the spec: 0, 1, 0, 1
    current flows); `--value` reads the second start, `tank.deliver#1`, which is `unavailable`
    before it starts and keeps its request after it finishes."""
    model = package(tmp_path / 'deliveries', DELIVERIES, UNITS)
    found = napkin(capsys, 'run', model, '--at', '0h,1h,2h,3h,4h')
    assert found.code == 0, found.err
    rows = {line.split()[0]: line.split()[1:] for line in found.out.splitlines()[2:]}
    assert list(rows) == [
        'tank.water',
        'started',
        'current',
        'requested',
        'tank.water.outflow.request',
        'tank.water.outflow.actual_rate',
    ]
    assert rows['tank.water'] == ['L', '100', '100', '98', '98', '96']
    assert rows['current'] == ['0', '1', '0', '1', '0']
    assert rows['requested'] == ['L/h', '0', '2', '0', '2', '0']
    second = napkin(
        capsys, 'run', model, '--json', '--value', 'tank.deliver#1.pipe.request', '--at', '2h,3h,5h'
    )
    assert second.code == 0, second.err
    assert second.doc['values']['tank.deliver#1.pipe.request']['values'] == [
        {'unavailable': 'tank.deliver#1 has not started at 2 h'},
        2,
        2,
    ]


def test_the_tank_of_the_spec_delivers_3_litres_an_hour_until_2_h_40_min(tmp_path, capsys):
    """8 L at 3 L/h: empty at 8/3 h = 2 h 40 min; the request stays 3 L/h and the capacity 5 L/h."""
    model = package(tmp_path / 'tank', TANK, UNITS)
    found = napkin(capsys, 'run', model, '--json', '--at', '0h,1h,159min,160min,161min,3h,4h')
    assert found.code == 0, found.err
    values = found.doc['values']
    rate, water = values['clinic.delivery.actual_rate'], values['tank.water']
    assert (rate['unit'], water['unit']) == ('L/h', 'L')
    assert rate['values'][:3] == pytest.approx([3, 3, 3])
    assert rate['values'][4:] == [0, 0, 0]
    assert water['values'] == pytest.approx([8, 5, 0.05, 0, 0, 0, 0], abs=1e-9)
    assert values['clinic.delivery.request']['values'] == [3] * 7
    assert values['clinic.delivery.capacity']['values'] == [5] * 7


def test_the_tank_holds_0_litres_after_it_empties(tmp_path, capsys):
    model = package(tmp_path / 'tank', TANK, UNITS)
    found = napkin(capsys, 'run', model, '--value', 'tank.water', '--value', 'clinic.delivery.actual_rate')
    assert found.code == 0, found.err
    rows = [line.split() for line in found.out.splitlines()[2:]]
    assert rows == [['tank.water', 'L', '8', '0'], ['clinic.delivery.actual_rate', 'L/h', '3', '0']]


def test_a_formula_reads_its_value_at_the_time_asked(tmp_path, capsys):
    """`water` is 8 - 3t, so the yes/no below is true only while t is in [0.9, 0.90333] h: a window
    narrower than the points at which a fit of the formula is checked. A read evaluates the formula
    at the time asked, so it sees the window."""
    text = TANK.replace(
        'readonly water: L = 8 in [0, 20]\n',
        'readonly water: L = 8 in [0, 20]\n'
        '    narrow: formula(bool) = formula(this.water <= 5.3 L and this.water >= 5.29 L)\n',
    )
    model = package(tmp_path / 'narrow', text, UNITS)
    found = napkin(capsys, 'run', model, '--json', '--value', 'tank.narrow', '--at', '0.89h,0.9017h,0.91h')
    assert found.code == 0, found.err
    narrow = found.doc['values']['tank.narrow']
    assert (narrow['unit'], narrow['label'], narrow['values']) == ('', None, [False, True, False])


def test_a_model_that_does_not_compile_prints_its_problem_with_its_place(tmp_path, capsys):
    model = package(tmp_path / 'tank', TANK.replace('water: L =', 'water: Lx ='), UNITS)
    found = napkin(capsys, 'run', model)
    assert found.code == 1
    # `    readonly water: Lx`: Lx starts at the 21st column of the 5th line.
    assert found.err.splitlines() == [
        f'{model / "model.scn"}:5:21: error: Lx is no unit and no template [unknown_name]'
    ]
    as_json = napkin(capsys, 'run', model, '--json')
    assert as_json.code == 1
    (problem,) = as_json.doc['diagnostics']
    assert (problem['code'], problem['line'], problem['column']) == ('unknown_name', 5, 21)


def test_a_run_that_stops_prints_the_values_before_it_stopped_then_why(tmp_path, capsys):
    """A request of 3 L/h * 2 L / (water - 2 L) has no bound as the tank nears 2 L: (water - 2 L)^2
    is 36 - 12 t, so 2 L at 3 h, and the run stops before its horizon (the engine times a failure
    in a numerical segment at the segment's start). At the start the request is 3 * 2 / 6 = 1 L/h."""
    text = TANK.replace(
        '        capacity = 5 L/h\n        request = 3 L/h\n',
        '        request = formula(3 L/h * (2 L / (tank.water - 2 L)))\n',
    )
    model = package(tmp_path / 'stops', text, UNITS)
    found = napkin(capsys, 'run', model, '--json', '--at', '0h,3.5h')
    assert found.code == 1
    doc = found.doc
    (problem,) = doc['diagnostics']
    assert problem['code'] == 'run'
    assert problem['message'].startswith('the run failed at ')
    assert doc['stopped'] == problem['message']
    assert doc['times'][0] == 0
    assert 3.5 not in doc['times']
    assert doc['values']['tank.water']['values'][0] == 8
    assert doc['values']['clinic.delivery.request']['values'][0] == pytest.approx(1, rel=1e-12)
    text_mode = napkin(capsys, 'run', model)
    assert text_mode.code == 1
    assert text_mode.err.splitlines()[-1].endswith('[run]')


@pytest.mark.parametrize(
    'argv, message',
    [
        (('--value', 'tank.waterr'), 'no named value of the model; did you mean tank.water?'),
        (('--at', '2 minutes'), 'minutes is not a unit of time of the model'),
        (('--at', '2L'), 'L is not a unit of time of the model'),
        (('--at', '3'), 'give the unit of time'),
        (('--at', '5h'), 'the run goes from 0 h to 4 h'),
        (('--at', 'soon'), 'give a number and a unit of time'),
    ],
)
def test_a_path_or_a_time_that_the_model_does_not_have_is_a_usage_error(tmp_path, capsys, argv, message):
    """Without `min`, the tank's units of time are the prelude's (h, day, week, ...), which have no
    `minutes`; `L` is a unit of volume; the run ends at 4 h."""
    model = package(tmp_path / 'tank', TANK, {'L': UNITS['L']})
    found = napkin(capsys, 'run', model, *argv)
    assert found.code == 2
    assert message in found.err


def test_a_model_that_is_not_there_is_a_usage_error(tmp_path, capsys):
    assert napkin(capsys, 'run', tmp_path / 'nowhere').code == 2
    (tmp_path / 'notes.txt').write_text('no model', encoding='utf-8')
    assert napkin(capsys, 'run', tmp_path / 'notes.txt').code == 2
    assert napkin(capsys, 'run', tmp_path).code == 2


WELLS = """\
scenario "Wells"
    horizon 2 h

Well:
    input depth: m = 0 m
    water: L = 10 L in [0 L,]
    flow draw: this.water -> SINK
        request = 1 L/h

wells: Well from "wells.csv"
"""


def test_the_rows_of_a_table_are_listed_by_their_ids(tmp_path, capsys):
    """Each row of the table is a member, named by its id; a well drains 1 L/h from 10 L, so 8 L at
    2 h, and keeps the depth of its row."""
    model = package(tmp_path / 'wells', WELLS, {**UNITS, 'm': {'dimensions': {'length': 1}, 'scale': 1}})
    (model / 'wells.csv').write_text('id,depth: m\nnorth,10\nsouth,30\n', encoding='utf-8')
    found = napkin(capsys, 'run', model)
    assert found.code == 0, found.err
    rows = {line.split()[0]: line.split()[1:] for line in found.out.splitlines()[2:]}
    assert rows['wells.north.depth'] == ['m', '10', '10']
    assert rows['wells.south.depth'] == ['m', '30', '30']
    assert rows['wells.north.water'] == rows['wells.south.water'] == ['L', '10', '8']
    assert rows['wells.south.draw.actual_rate'] == ['L/h', '1', '1']


def test_a_row_that_names_a_member_with_a_title_shows_it(tmp_path, capsys):
    """The tank's title is in brackets after the paths of its values, in the table and in the JSON
    document; the clinic has none. 8 L at 3 L/h hold 2 L at 2 h."""
    model = package(tmp_path / 'tank', TANK.replace('tank:\n', 'tank:\n    title "Main tank"\n'), UNITS)
    found = napkin(capsys, 'run', model, '--value', 'tank.water,clinic.delivery.request', '--at', '0h,2h')
    assert found.code == 0, found.err
    rows = found.out.splitlines()[2:]
    assert rows[0].split() == ['tank.water', '(Main', 'tank)', 'L', '8', '2']
    assert rows[1].split() == ['clinic.delivery.request', 'L/h', '3', '3']
    doc = napkin(capsys, 'run', model, '--json', '--value', 'tank.water,clinic.delivery.request').doc
    assert [doc['values'][path]['title'] for path in ('tank.water', 'clinic.delivery.request')] == [
        'Main tank',
        None,
    ]
