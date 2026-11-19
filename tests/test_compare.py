"""The comparison of two runs by names, values and traces (`tools/compare.py`, D16), on made-up captures
and on the tank of the spec, whose values follow its closed form: 8 L drained at 3 L/h hold 8 - 3t
until 8/3 h, then 0.
"""

from __future__ import annotations

import copy
import json

import pytest

from tests.commands.call import TANK, UNITS, package
from tools import compare


def made(**values):
    """A capture at 0 h and 2 h with the given values ({path: [a, b]}) and a trace of two entries."""
    return {
        'model': 'made',
        'run': None,
        'horizon': 2.0,
        'times': [0.0, 2.0],
        'values': {path: {'unit': 'L', 'values': list(found)} for path, found in values.items()},
        'trace': [
            {'t': 0.0, 'kind': 'start', 'part': 'tank.fill', 'owner': 'tank.fill#0'},
            {'t': 1.5, 'kind': 'commit', 'part': 'tank.fill.step[0]', 'owner': 'tank.fill#0'},
        ],
    }


def differences(base, other, **settings):
    return compare.compare(base, other, **settings)[0]


def test_a_capture_agrees_with_itself_and_counts_what_it_compared():
    base = made(**{'tank.water': [8, 2], 'tank.full': [False, True]})
    found, counts = compare.compare(base, copy.deepcopy(base))
    assert found == []
    assert counts == {'names': 2, 'values': 4, 'extra': 0, 'entries': 2}


@pytest.mark.parametrize(
    'other, agrees',
    [
        (2 * (1 + 0.9e-6), True),  # within the relative tolerance of 1e-6
        (2 * (1 + 1.1e-6), False),
        (2 + 1e-3, False),
    ],
)
def test_two_numbers_agree_within_the_tolerances(other, agrees):
    found = differences(made(**{'tank.water': [8, 2]}), made(**{'tank.water': [8, other]}))
    assert (found == []) == agrees
    if not agrees:
        assert found == [f'tank.water at 2 h: 2, and the other {other!r}']


def test_a_zero_agrees_with_a_residue_within_the_absolute_tolerance():
    assert differences(made(x=[0, 0]), made(x=[4e-26, 0])) == []
    assert differences(made(x=[0, 0]), made(x=[1e-8, 0])) != []
    assert differences(made(x=[0, 0]), made(x=[1e-8, 0]), absolute=1e-7) == []


def test_a_yes_no_a_text_and_an_unavailable_value_agree_only_with_the_same():
    base = made(flag=[True, False], link=['north', 'south'], late=[{'unavailable': 'not started'}, 1.0])
    assert differences(base, copy.deepcopy(base)) == []
    other = made(flag=[True, True], link=['north', 'north'], late=[0.0, 1.0])
    assert differences(base, other) == [
        'flag at 2 h: False, and the other True',
        "link at 2 h: 'south', and the other 'north'",
        'late at 0 h: unavailable (not started), and the other 0.0',
    ]
    # True is no number: it does not agree with 1.
    assert differences(made(flag=[True, True]), made(flag=[1, 1])) != []


def test_each_name_of_the_base_is_in_the_other_and_a_name_of_the_other_alone_is_counted():
    base, other = made(a=[1, 1], b=[2, 2]), made(a=[1, 1], c=[3, 3])
    found, counts = compare.compare(base, other)
    assert found == ['b: the other has no value of this name']
    assert counts['extra'] == 1


def test_a_rename_maps_whole_dotted_paths_from_the_left():
    rename = compare.renamer({'tank': 'store', 'tank.deliver': 'store.send'})
    assert rename('tank.water') == 'store.water'
    assert rename('tank') == 'store'
    assert rename('tank.deliver#1.pipe.request') == 'store.send#1.pipe.request'
    assert rename('tanks.water') == 'tanks.water'
    base = made(**{'tank.water': [8, 2]})
    other = made(**{'store.water': [8, 2]})
    for entry in other['trace']:
        entry['part'] = entry['part'].replace('tank', 'store')
        entry['owner'] = entry['owner'].replace('tank', 'store')
    assert differences(base, other) != []
    assert differences(base, other, renames={'tank': 'store'}) == []


def test_two_units_differ_unless_one_side_gives_none():
    base, other = made(x=[1, 1]), made(x=[1, 1])
    other['values']['x']['unit'] = 'kL'
    assert differences(base, other) == ['x: in L, and the other in kL']
    other['values']['x']['unit'] = None
    assert differences(base, other) == []


def test_the_first_entry_of_the_trace_that_differs_is_the_difference():
    base = made(x=[1, 1])
    later = copy.deepcopy(base)
    later['trace'][1]['t'] = 1.6
    assert differences(base, later) == [
        'trace entry 1: commit tank.fill.step[0] of tank.fill#0 at 1.5 h, '
        'and the other commit tank.fill.step[0] of tank.fill#0 at 1.6 h'
    ]
    shorter = copy.deepcopy(base)
    shorter['trace'].pop()
    assert differences(base, shorter) == [
        'trace entry 1: only the base has it, commit tank.fill.step[0] at 1.5 h'
    ]
    # A side with no trace, such as a published result, is compared by its values.
    untraced = copy.deepcopy(base)
    untraced['trace'] = None
    assert differences(untraced, base) == [] and compare.compare(untraced, base)[1]['entries'] == 0


def test_times_that_only_one_side_holds_are_not_compared():
    base, other = made(x=[1, 5]), made(x=[1, 7])
    other['times'] = [0.0, 3.0]
    assert differences(base, other) == []
    other['times'] = [1.0, 3.0]
    assert differences(base, other) == ['no time of the base is a time of the other']


RESULTS = {
    'scenario': 'pumps:east',
    'horizon_h': 48,
    'rows': [
        {'run': 'fast', 'outcomes': {'served': {'value': 12.5, 'status': 'estimated'}}},
        {'run': 'slow', 'outcomes': {'served': {'value': None, 'status': 'unestimated'}}},
    ],
}


def test_published_results_give_the_outcomes_of_one_run_at_the_horizon():
    fast = compare.published(RESULTS, 'fast')
    assert (fast['times'], fast['values'], fast['trace']) == (
        [48.0],
        {'served': {'unit': None, 'values': [12.5]}},
        None,
    )
    slow = compare.published(RESULTS, 'slow')
    assert slow['values']['served']['values'] == [{'unavailable': 'unestimated'}]
    with pytest.raises(ValueError, match='give --run NAME'):
        compare.published(RESULTS)
    with pytest.raises(ValueError, match='no run medium'):
        compare.published(RESULTS, 'medium')
    assert compare.published({**RESULTS, 'rows': RESULTS['rows'][:1]})['run'] == 'fast'


def test_the_capture_of_the_tank_follows_its_closed_form(tmp_path):
    """8 L at 3 L/h: 8, 5 and 2 L at 0, 1 and 2 h, empty from 8/3 h; the delivery's rate is 3 L/h until
    then and 0 after it; no event, so no trace."""
    model = package(tmp_path / 'tank', TANK, UNITS)
    found = compare.capture(model / 'model.scn', times=[0, 1, 2, 3, 4])
    assert found['model'] == 'tank' and found['horizon'] == 4
    assert found['values']['tank.water'] == {'unit': 'L', 'values': pytest.approx([8, 5, 2, 0, 0], abs=1e-9)}
    assert found['values']['clinic.delivery.actual_rate']['values'] == pytest.approx(
        [3, 3, 3, 0, 0], abs=1e-9
    )
    assert found['trace'] == []
    # Sixteenths of the horizon by default.
    assert compare.capture(model / 'model.scn')['times'] == [k / 4 for k in range(17)]


def test_a_capture_after_a_run_stops_holds_no_value(tmp_path):
    """The request 3 L/h * 2 L / (water - 2 L) has no bound as the tank nears 2 L, at 3 h."""
    text = TANK.replace(
        '        capacity = 5 L/h\n        request = 3 L/h\n',
        '        request = formula(3 L/h * (2 L / (tank.water - 2 L)))\n',
    )
    model = package(tmp_path / 'stops', text, UNITS)
    found = compare.capture(model / 'model.scn', times=[0, 3.5])
    water = found['values']['tank.water']['values']
    assert water[0] == 8 and water[1]['unavailable'].startswith('the run stopped at ')
    assert found['trace'][-1]['kind'] == 'failure'


def test_the_command_writes_a_capture_and_compares_two_sides(tmp_path, capsys):
    model = package(tmp_path / 'tank', TANK, UNITS)
    kept = tmp_path / 'tank.json'
    assert compare.main([str(model), '--write', str(kept), '--at', '0,1,2']) == 0
    assert json.loads(kept.read_text(encoding='utf-8'))['times'] == [0, 1, 2]
    assert compare.main([str(kept), str(model), '--at', '0,1,2']) == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith('0 differences: ')
    faster = package(tmp_path / 'faster', TANK.replace('request = 3 L/h', 'request = 4 L/h'), UNITS)
    assert compare.main([str(kept), str(faster), '--at', '0,1,2']) == 1
    out = capsys.readouterr().out
    assert 'tank.water at 1 h: 5.0, and the other 4.0' in out
    with pytest.raises(SystemExit) as wrong:
        compare.main([str(model)])
    assert wrong.value.code == 2
