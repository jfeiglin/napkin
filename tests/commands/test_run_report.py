"""`napkin run` through the report: a named run and an edit document, reporting lags and their proof,
status displays, near-ties, and how a number and a unit show.

Each expected value is worked by hand: a tank that drains at a constant rate, the closed form of an
exponential and the mean of it over a window, the case of a display by its times, a sum of floats.
"""

from __future__ import annotations

import json
import math
import textwrap

import pytest

from tests.commands.call import UNITS, napkin, package
from tests.language.test_solvers import network

# The tank of the spec, with the clinic's pace an input that two options and two runs set.
PACED = """\
scenario "Paced tank"
    horizon 4 h

tank:
    readonly water: L = 8 in [0, 20]

clinic:
    input pace: L/h = 3 L/h in [0 L/h, 10 L/h]  @pace
        "Pace of the clinic"
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = formula(this.pace)

options "Pace":
    "Fast":
        "The clinic draws fast."
        clinic.pace = 4 L/h  @pace
    "Slow":
        "The clinic draws slowly."
        clinic.pace = 1 L/h  @pace

runs:
    fast = "Fast"
    slow = "Slow"

record pace: assumption "The paces of a test."
"""


def water(found):
    """The text row of `tank.water`: its cells after the path and the unit."""
    row = next(line.split() for line in found.out.splitlines() if line.startswith('tank.water '))
    return row[2:]


def test_a_named_run_takes_its_option(tmp_path, capsys):
    """8 L at 4 L/h is empty at 2 h; at 1 L/h it holds 7 L at 1 h and 4 L at 4 h; the default run
    draws 3 L/h, so 5 L at 1 h and 0 L from 8/3 h."""
    model = package(tmp_path / 'paced', PACED, UNITS)
    found = napkin(capsys, 'run', model, '--run', 'fast', '--at', '1h,2h,4h')
    assert found.code == 0, found.err
    assert found.out.splitlines()[0] == 'Paced tank: the run fast, a median run to 4 h'
    assert water(found) == ['4', '0', '0']
    assert water(napkin(capsys, 'run', model, '--run', 'slow', '--at', '1h,2h,4h')) == ['7', '6', '4']
    assert water(napkin(capsys, 'run', model, '--at', '1h,2h,4h')) == ['5', '2', '0']
    doc = napkin(capsys, 'run', model, '--run', 'slow', '--json', '--value', 'clinic.pace').doc
    assert (doc['run'], doc['values']['clinic.pace']['values']) == ('slow', [1, 1])
    assert doc['values']['clinic.pace']['label'] == 'Pace of the clinic'


def test_a_run_that_the_model_does_not_have_is_a_usage_error(tmp_path, capsys):
    model = package(tmp_path / 'paced', PACED, UNITS)
    found = napkin(capsys, 'run', model, '--run', 'fats')
    assert found.code == 2
    assert '--run fats: no run of the model; did you mean fast?' in found.err
    plain = package(tmp_path / 'plain', PACED.split('options')[0] + 'record pace: assumption "P."\n', UNITS)
    assert 'it has no named run' in napkin(capsys, 'run', plain, '--run', 'fast').err


def edits(tmp_path, body):
    path = tmp_path / 'edits.json'
    path.write_text(json.dumps(body), encoding='utf-8')
    return path


def test_an_edit_document_sets_an_input_and_the_narrower_edit_wins(tmp_path, capsys):
    """`set` gives every run 2 L/h: 6 L at 1 h. An edit of the run `fast` wins over its option and
    over `set`: 0.5 L/h leaves 7.5 L at 1 h. A document with no hash is this model's."""
    model = package(tmp_path / 'paced', PACED, UNITS)
    path = edits(tmp_path, {'set': {'clinic.pace': 2}, 'runs': {'fast': {'clinic.pace': 0.5}}})
    found = napkin(capsys, 'run', model, '--edits', path, '--at', '1h')
    assert found.code == 0, found.err
    assert found.out.splitlines()[0] == f'Paced tank: a median run to 4 h, with the edits of {path}'
    assert water(found) == ['6']
    assert water(napkin(capsys, 'run', model, '--edits', path, '--run', 'fast', '--at', '1h')) == ['7.5']
    assert water(napkin(capsys, 'run', model, '--edits', path, '--run', 'slow', '--at', '1h')) == ['6']


def test_an_edit_document_that_does_not_hold_is_refused_at_its_file(tmp_path, capsys):
    """A document of another revision keeps its hash and is refused; a value outside the input's
    range is refused at its place in the document; a file that is not JSON, at its line."""
    model = package(tmp_path / 'paced', PACED, UNITS)
    other = edits(tmp_path, {'schema_version': '0.0.1', 'model_hash': 'another', 'set': {}})
    found = napkin(capsys, 'run', model, '--edits', other)
    assert found.code == 1
    assert found.err.splitlines() == [
        f'{other}: error: the edits are for another revision of the model [model_hash]'
    ]
    wide = edits(tmp_path, {'set': {'clinic.pace': 11}})
    (problem,) = napkin(capsys, 'run', model, '--edits', wide, '--json').doc['diagnostics']
    assert (problem['file'], problem['message'].split(':')[0]) == (str(wide), 'set/clinic.pace')
    broken = tmp_path / 'broken.json'
    broken.write_text('{\n  "set": {"clinic.pace": 2,}\n}\n', encoding='utf-8')
    found = napkin(capsys, 'run', model, '--edits', broken)
    assert found.code == 1
    assert found.err.startswith(f'{broken}:2:')
    assert found.err.rstrip().endswith('[edits]')
    assert napkin(capsys, 'run', model, '--edits', tmp_path / 'nowhere.json').code == 1


# A decaying stock fills a tally: finished = 100 (1 - e^(-t/10)) person, which never falls; pending
# = 100 e^(-t/10) person falls.
DECAY = """\
scenario "Decay"
    horizon 20 h

s:
    pending: person = 100 person in [0 person,]
    finished: person = 0 person in [0 person,]
        "People who finished"
    flow finish: this.pending -> this.finished
        request = formula(this.pending / (10 h))
"""


def mean_finished(t, shortest=2, longest=6):
    """The mean of finished over [t - longest, t - shortest], which holds 0 before time 0: with
    C(x) = 100 (x + 10 (e^(-x/10) - 1)), the integral of finished from 0 to x, the mean is
    (C(max(0, t - shortest)) - C(max(0, t - longest))) / (longest - shortest)."""

    def integral(x):
        x = max(0.0, x)
        return 100 * (x + 10 * math.expm1(-x / 10))

    return (integral(t - shortest) - integral(t - longest)) / (longest - shortest)


def test_a_lag_of_a_value_that_never_falls_is_the_mean_of_its_window(tmp_path, capsys):
    model = package(tmp_path / 'decay', DECAY)
    found = napkin(capsys, 'run', model, '--json', '--at', '0h,1h,8h,20h', '--lag', 's.finished=2h..6h')
    assert found.code == 0, found.err
    finished = found.doc['values']['s.finished']
    assert finished['lag'] == {'shortest': 2, 'longest': 6}
    assert finished['values'] == pytest.approx([mean_finished(t) for t in (0, 1, 8, 20)], rel=1e-8, abs=1e-7)
    assert 's.finish of s' in finished['note']
    text = napkin(capsys, 'run', model, '--at', '8h', '--lag', 's.finished=2h..6h', '--value', 's.finished')
    assert text.code == 0 and text.err == ''
    lines = text.out.splitlines()
    assert lines[2].split() == ['s.finished', '(lag', '2', 'h..6', 'h)', 'person', f'{mean_finished(8):.6g}']
    assert lines[3].startswith(
        's.finished (lag 2 h..6 h): the mean of its history from 6 h to 2 h before each time; it never falls: '
    )


def test_a_fixed_delay_reads_the_value_that_long_before(tmp_path, capsys):
    """One delay of 3 h: at 5 h the value at 2 h, 100 (1 - e^(-0.2)); at 1 h the value at time 0."""
    model = package(tmp_path / 'decay', DECAY)
    found = napkin(capsys, 'run', model, '--json', '--at', '1h,5h', '--lag', 's.finished=3h')
    values = found.doc['values']['s.finished']['values']
    assert values == pytest.approx([0, 100 * -math.expm1(-0.2)], rel=1e-8, abs=1e-9)


def test_a_lag_of_a_value_that_can_fall_is_a_warning_and_the_plain_read_stays(tmp_path, capsys):
    model = package(tmp_path / 'decay', DECAY)
    found = napkin(capsys, 'run', model, '--at', '0h,10h', '--value', 's.pending', '--lag', 's.pending=2h..6h')
    assert found.code == 0
    assert found.err.splitlines() == [
        'warning: the lag is refused: s.pending can fall: s.finish of s takes from what it counts [lag]'
    ]
    row = found.out.splitlines()[2].split()
    assert row[:2] == ['s.pending', 'person']
    assert [float(cell) for cell in row[2:]] == pytest.approx([100, 100 * math.exp(-1)], rel=1e-5)


@pytest.mark.parametrize(
    'lag, message',
    [
        ('s.finished', '--lag takes PATH=FROM..TO'),
        ('s.finishd=2h..6h', 'no named value of the model; did you mean s.finished'),
        ('s.finished=6h..2h', 'from the shorter delay to the longer'),
        ('s.finished=2h..4h..6h', 'from the shorter delay to the longer'),
        ('s.finished=2..6h', 'give the unit of time'),
    ],
)
def test_a_lag_that_is_not_one_is_a_usage_error(tmp_path, capsys, lag, message):
    model = package(tmp_path / 'decay', DECAY)
    found = napkin(capsys, 'run', model, '--lag', lag)
    assert found.code == 2
    assert message in found.err


CREW = """\
scenario "Crews"
    horizon 6 h

crew:
    work_state: enum[WAITING, WORKING, DONE] = WAITING
        "Crew work state"
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

crew.work.start()
"""


def test_a_status_display_shows_the_rating_and_the_text_of_its_case(tmp_path, capsys):
    """The crew waits until 2 h (the fallback), works until 4 h (the second case, which shares its
    rating with the fallback and has its own text), and is done from 4 h (spec, "Model text, status
    cases and evidence")."""
    model = package(tmp_path / 'crew', CREW)
    found = napkin(capsys, 'run', model, '--at', '1h,3h,4h,6h')
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    rows = {line.split()[0]: line.split()[1:] for line in lines[2:4]}
    assert rows == {
        'crew.work_state': ['WAITING', 'WORKING', 'DONE', 'DONE'],
        'crew.status': ['degraded', 'degraded', 'ok', 'ok'],
    }
    assert lines[4:] == [
        'crew.status at 1 h: degraded: Crews are waiting for access.',
        'crew.status at 3 h: degraded: Crews are carrying out repairs.',
        'crew.status at 4 h, 6 h: ok: Repairs are complete.',
    ]
    doc = napkin(capsys, 'run', model, '--json', '--value', 'crew.status', '--at', '3h').doc
    assert doc['values']['crew.status']['values'] == [
        {'rating': 'degraded', 'text': 'Crews are carrying out repairs.', 'case': 'crew.status.case[1]'}
    ]


# 0.1 L and then 0.2 L reach the level 0.3 L of the alarm: in floats, one unit in the last place
# above it.
TOP_UP = """\
scenario "Top up"
    horizon 3 h

tank:
    level: L = 0 L in [0 L,]
    top = event():
        after 1 h:
            this.level += 0.1 L
            this.level += 0.2 L
    alarm = event():
        when this.level >= 0.3 L:
            this.alarm.start()
        after 0 h

tank.top.start()
"""


def test_a_near_tie_of_the_run_is_listed_under_the_table(tmp_path, capsys):
    model = package(tmp_path / 'top', TOP_UP, UNITS)
    found = napkin(capsys, 'run', model, '--at', '3h')
    assert found.code == 0, found.err
    (line,) = [line for line in found.out.splitlines() if line.startswith('near-tie: ')]
    assert line.startswith('near-tie: tank.alarm.when[0] at 1 h: this trigger fired within tolerance')
    (tie,) = napkin(capsys, 'run', model, '--json', '--at', '3h').doc['near_ties']
    assert (tie['t'], tie['kind'], tie['part'], tie['owner']) == (1, 'fire', 'tank.alarm.when[0]', 'tank')
    assert tie['difference'] == (0.1 + 0.2) - 0.3


def worked_network(tmp_path):
    """The worked network of the spec ("Worked network data and expected rates"), in W and Wh, to
    4 h: the garden route closes at 2 h."""
    text, tables = network()
    folder = package(
        tmp_path / 'network',
        'scenario "Network"\n    horizon 4 h\n' + textwrap.dedent(text),
        {
            'Wh': {'dimensions': {'energy': 1}, 'scale': 1, 'description': 'A watt hour.'},
            'W': {'dimensions': {'energy': 1, 'time': -1}, 'scale': 1, 'description': 'A watt.'},
        },
    )
    for name, body in tables.items():
        (folder / name).write_text(body, encoding='utf-8')
    return folder


def test_a_rate_between_stores_in_wh_shows_in_w_and_a_residue_of_the_solver_as_0(tmp_path, capsys):
    """Spec: the garden sends 4 W to the junction at 0 h and 3 W at 1 h, as the needs halve; once its
    route closes, the route carries 0 W, since its pull is 0. A flow between stores in Wh has its
    rate in Wh/h, which the table of units names W: the number is the same. The solver leaves a
    residue where the answer is 0, far below the run's tolerance of 1e-10 of the 4 W that the rate
    reaches: the text shows 0, and the JSON the record's number."""
    model = worked_network(tmp_path)
    path = 'links.garden_junction.carried.actual_rate'
    found = napkin(capsys, 'run', model, '--value', path, '--at', '0h,1h,3h')
    assert found.code == 0, found.err
    assert found.out.splitlines()[2].split() == [path, 'W', '-4', '-3', '0']
    doc = napkin(capsys, 'run', model, '--json', '--value', path, '--at', '3h').doc
    assert doc['values'][path]['unit'] == 'W'
    (residue,) = doc['values'][path]['values']
    assert abs(residue) <= 1e-10 * 4


@pytest.mark.parametrize(
    'spelling, shown',
    [('Wh/h', 'W'), ('kWh/h', 'kW'), ('L/h', 'L/h'), ('Wh', 'Wh'), ('Wh/Wh', 'Wh/Wh'), ('W*h/h', 'W')],
)
def test_a_composed_unit_shows_as_the_name_of_an_equal_unit(spelling, shown):
    """An equal unit has one dimension and one scale: kWh/h is 1000 Wh per hour, a kW. A plain
    ratio stays as it is written."""
    from napkin.commands.common import unit_shown
    from napkin.model.semantic import Units

    units = Units(
        {
            'h': ({'time': 1}, 1),
            'L': ({'volume': 1}, 1),
            'Wh': ({'energy': 1}, 1),
            'kWh': ({'energy': 1}, 1000),
            'W': ({'energy': 1, 'time': -1}, 1),
            'kW': ({'energy': 1, 'time': -1}, 1000),
            'fraction': ({}, 1),
        }
    )
    assert unit_shown(units, spelling) == shown
