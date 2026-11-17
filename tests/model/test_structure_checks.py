"""The checks of a structure (`napkin/model/analysis/structure.py`), each on its own case.

The front end refuses most wrong models before a structure is made, so a model file cannot show
each check. These tests change one part of the structure of the fixture that writes every construct
once, as the builder writes it, and give the typed parts to the checks. Each case says the rule in
words and names the diagnostics that follow from it: the code, and the place that the changed part
has in the structure. The class of a condition, the names that move and the order of the formulas
are checked against their definitions.
"""

import random

import pytest

from napkin.core import expr as nodes
from napkin.expressions import UnitSystem
from napkin.model.analysis import structure as checks
from napkin.model.ir import thaw
from napkin.model.structure import SECTIONS, Structure, Trigger
from tests import build as b
from tests.acceptance.helpers import LIBRARY, fixture


@pytest.fixture(scope='module')
def model():
    return b.compiled(fixture('F5'), LIBRARY)


def changed(model, change=None):
    """(the typed parts, the units) of the structure of the fixture after `change` has changed the
    plain mapping of it."""
    (mapping,) = (item.plain() for item in model.structures.values())
    if change is not None:
        change(mapping)
    return Structure.of(mapping), UnitSystem(model.library['units'])


def found(model, change):
    """(code, place) of each diagnostic of the checks, in their order."""
    structure, units = changed(model, change)
    errors, _ = checks.structure_facts(structure, thaw(model.library), units)
    return [(item['code'], item['path']) for item in errors]


# ---- one case for each rule ---------------------------------------------------------------------------
#
# A case changes the mapping `m` and gives the diagnostics that the rule asks for.


def as_the_builder_writes_it(m):
    """The fixture is right."""
    return []


def minimum_above_maximum(m):
    """A quantity has its minimum at or below its maximum."""
    calls = m['quantities']['operators.calls']
    assert calls['max'] == 3
    calls['min'] = 5
    return [('bounds', calls['path'])]


def stock_with_a_minimum_below_zero(m):
    """A stock holds no less than nothing. A number that only rules set can be below zero."""
    stock, number = m['quantities']['tank.water'], m['quantities']['basin.logs']
    assert (stock['kind'], number['kind']) == ('stock', 'variable')
    stock['min'] = number['min'] = -1
    return [('bounds', stock['path'])]


def yes_no_state_with_another_range(m):
    """A yes/no state is a number with no unit, from 0 to 1."""
    full = m['quantities']['bucket_a.full']
    assert full['binary']
    full['max'] = 2
    return [('binary_state', full['path'])]


def yes_no_input_with_a_unit(m):
    """A yes/no input has a unit with no dimension and no scale."""
    odds = m['parameters']['operators.close_odds']
    odds['metadata'] = {'control': 'binary'}
    odds['unit'] = 'h'
    return [('binary_control', f'{odds["path"]}/unit')]


def yes_no_input_with_a_plain_unit(m):
    odds = m['parameters']['operators.close_odds']
    assert odds['unit'] == 'fraction'
    odds['metadata'] = {'control': 'binary'}
    return []


def choice_with_a_unit(m):
    """An input with named values is a code with the unit fraction."""
    odds = m['parameters']['operators.close_odds']
    odds['metadata'] = {'control': 'choice', 'values': ['never', 'always']}
    odds['unit'] = 'L'
    return [('choice_control', f'{odds["path"]}/unit')]


def status_that_is_no_health(m):
    """The status of an entity is ok, degraded, failed or inactive: each case, and the last one."""
    m['labels']['tank.health']['cases'][0]['value'] = 'broken'
    m['labels']['basin.health']['default']['value'] = 'worse'
    return [('health', m['labels'][name]['path']) for name in m['labels']]


def unit_that_the_library_does_not_have(m):
    """A part has a unit of the library. A quantity with no unit is no part of a sum."""
    spill = m['quantities']['basin.spill']
    spill['unit'] = 'furlongs'
    total = m['partitions']['simulate.1']
    assert 'basin.spill' in total['parts']
    return [('unit', spill['path']), ('unit', total['path'])]


def output_with_a_unit_that_the_library_does_not_have(m):
    m['outcomes']['harm']['unit'] = 'furlongs'
    return [('unit', 'outcomes/harm')]


def start_value_in_another_unit(m):
    """Each expression has the unit of its place."""
    spill = m['quantities']['basin.spill']
    spill['initial'] = "q(1, 'h')"
    return [('expression', f'{spill["path"]}/initial')]


def bound_in_another_unit(m):
    calls = m['quantities']['operators.calls']
    calls['max'] = 'tank.level0'
    return [('expression', f'{calls["path"]}/max')]


def bound_that_reads_a_state(m):
    """A bound of a quantity reads inputs only."""
    calls = m['quantities']['operators.calls']
    calls['max'] = 'operators.reports + 3'
    return [('expression', f'{calls["path"]}/max')]


def formula_in_another_unit(m):
    fullest = m['computed']['basin.fullest']
    fullest['expr'] = 'tank.drain_rate'
    return [('expression', f'{fullest["path"]}/expr')]


def condition_of_a_status_that_is_a_number(m):
    case = m['labels']['tank.health']['cases'][0]
    case['when'] = 'tank.water'
    return [('expression', f'{case["path"]}/when')]


def rate_of_a_tally_in_another_unit(m):
    """A rate is the unit of its quantity for each unit of time."""
    rate = m['rates']['meters_1.reading']
    rate['expr'] = "q(2, 'L')"
    return [('expression', rate['path'])]


def rate_of_a_flow_in_another_unit(m):
    pump = m['flows']['basin.pump_a']
    pump['rate'] = "q(2, 'L')"
    return [('expression', f'{pump["path"]}/rate')]


def flow_between_two_units(m):
    """The two ends of a flow hold the same kind of thing."""
    out = m['flows']['tank.out.0']
    assert m['quantities'][out['from']]['unit'] == 'L' and m['quantities']['operators.calls']['unit'] != 'L'
    out['to'] = 'operators.calls'
    return [('unit', out['path'])]


def flow_in_a_group_that_is_not_there(m):
    out = m['flows']['tank.out.0']
    out['allocation'] = 'ghost'
    return [('reference', out['path'])]


def two_flows_from_a_stock_and_one_group_for_one_of_them(m):
    """Two flows that drain one stock are in one group, which says how they share the stock. The
    order of that group names each of its flows."""
    del m['flows']['basin.pump_b']['allocation']
    group = m['allocation']['basin.share_water']
    return [('allocation', m['quantities']['basin.water']['path']), ('allocation', group['path'])]


def two_flows_from_a_stock_and_no_group(m):
    for name in ('basin.pump_a', 'basin.pump_b'):
        del m['flows'][name]['allocation']
    del m['allocation']['basin.share_water']
    return [('allocation', m['quantities']['basin.water']['path'])]


def two_flows_from_a_stock_in_two_groups(m):
    group = m['allocation']['basin.share_water']
    m['allocation']['basin.other'] = {**group, 'path': 'basin/other', 'order': ['basin.pump_b']}
    m['flows']['basin.pump_b']['allocation'] = 'basin.other'
    group['order'] = ['basin.pump_a']
    return [('allocation', m['quantities']['basin.water']['path'])]


def two_flows_whose_rates_end_with_their_stock(m):
    """Two flows share a stock with no group when each rate is zero where the stock is empty: the
    stock itself over a time, and a product with the stock."""
    for name in ('basin.pump_a', 'basin.pump_b'):
        del m['flows'][name]['allocation']
    del m['allocation']['basin.share_water']
    m['flows']['basin.pump_a']['rate'] = "basin.water / q(2, 'h')"
    m['flows']['basin.pump_b']['rate'] = 'tank.drain_rate * basin.water / tank.level0'
    return []


def group_with_no_flow(m):
    """A group has a flow, a limit in the unit of its flows, and, when it serves them in order, each
    of them once in its order."""
    m['allocation']['basin.other'] = {**m['allocation']['basin.share_water'], 'path': 'basin/other'}
    return [('allocation', 'basin/other')]


def order_of_a_group_that_leaves_a_flow_out(m):
    group = m['allocation']['basin.share_water']
    assert group['policy'] == 'priority'
    group['order'] = ['basin.pump_a']
    return [('allocation', group['path'])]


def limit_of_a_group_in_another_unit(m):
    group = m['allocation']['basin.share_water']
    group['capacity'] = "q(3, 'L')"
    return [('expression', group['path'])]


def flows_of_a_group_from_two_units(m):
    """The flows of one group drain quantities of one unit."""
    pump = m['flows']['basin.pump_b']
    pump.update({'from': 'operators.calls', 'to': 'operators.reports', 'rate': "q(2, 'per_h')"})
    return [('allocation', m['allocation']['basin.share_water']['path'])]


def flow_in_two_sets_that_move_together(m):
    """A flow moves together with the flows of one set at most."""
    m['coupling']['tank.other'] = {**m['coupling']['tank.out'], 'flows': ['tank.out.0']}
    return [('coupling', 'coupling/tank.other')]


def condition_of_an_event_that_is_a_number(m):
    rule = m['rules']['operators.notice']
    rule['trigger']['when'] = 'operators.calls'
    return [('expression', rule['trigger']['path'])]


def delay_that_is_no_time(m):
    rule = m['rules']['operators.decide']
    rule['delay'] = "q(2, 'L')"
    return [('expression', rule['delay_path'])]


def window_that_reads_a_moving_value(m):
    """A window (`each`) and a waiting condition (`while`) read only values that change at moments."""
    rule = m['rules']['basin.survey']
    rule['each'] = ['tank.water']
    return [('unsupported_condition', rule['each_path'])]


def waiting_condition_that_reads_a_moving_value(m):
    rule = m['rules']['operators.report']
    rule['keep'] = "tank.water > q(1, 'L')"
    return [('unsupported_condition', rule['keep_path'])]


def waiting_condition_that_is_a_number(m):
    rule = m['rules']['operators.report']
    rule['keep'] = 'operators.calls'
    return [('expression', rule['keep_path'])]


def chance_that_reads_a_name_that_is_not_there(m):
    close = m['rules']['operators.decide']['outcomes'][0]
    close['chance'] = 'operators.luck'
    return [('expression', f'{close["path"]}/chance')]


def condition_of_an_outcome_that_is_a_number(m):
    close = m['rules']['operators.decide']['outcomes'][0]
    close['available'] = 'operators.calls'
    return [('expression', f'{close["path"]}/available')]


def outcome_that_fires_an_event_that_is_not_there(m):
    close = m['rules']['operators.decide']['outcomes'][0]
    close['do']['fire'] = ['ghost.event']
    return [('reference', close['path'])]


def value_that_an_outcome_sets_in_another_unit(m):
    line = m['rules']['operators.notice']['outcomes'][0]['do']['set']['operators.calls']
    line['expr'] = "q(1, 'h')"
    return [('expression', line['path'])]


def move_between_two_units(m):
    """A move takes an amount in the unit of its source to a quantity of the same unit."""
    move = m['rules']['basin.log']['outcomes'][0]['do']['transfer'][0]
    assert m['quantities'][move['from']]['unit'] == 'L' and m['quantities']['basin.logs']['unit'] != 'L'
    move['to'] = 'basin.logs'
    return [('unit', move['path'])]


def amount_of_a_move_in_another_unit(m):
    move = m['rules']['basin.log']['outcomes'][0]['do']['transfer'][0]
    move['amount'] = "q(5, 'h')"
    return [('expression', move['path'])]


def delay_of_a_past_value_that_is_no_time(m):
    """A value of the past (`delayed`) is read a time ago."""
    rule = m['rules']['basin.survey']
    past = next(item for item in rule['extras'] if item['kind'] == 'delayed')
    past['delay'] = "q(1, 'L')"
    return [('expression', rule['path'])]


def draw_of_a_share_added_to_a_count(m):
    """A draw of a beta distribution is a share: a number with no unit, which a count takes."""
    rule = m['rules']['basin.survey']
    draw = next(item for item in rule['extras'] if item['kind'] == 'draw')
    draw.update({'family': 'beta', 'args': {'a': '2', 'b': '3'}})
    step = rule['outcomes'][0]['do']
    del step['set']['basin.noise']
    step['set']['basin.logs'] = {'expr': f'basin.logs + {draw["name"]}', 'path': 'basin/survey/done/9'}
    return []


def draw_of_a_share_added_to_litres(m):
    rule = m['rules']['basin.survey']
    draw = next(item for item in rule['extras'] if item['kind'] == 'draw')
    draw.update({'family': 'beta', 'args': {'a': '2', 'b': '3'}})
    line = rule['outcomes'][0]['do']['set']['basin.noise']
    assert draw['name'] in line['expr'] and m['quantities']['basin.noise']['unit'] == 'L'
    return [('expression', line['path'])]


def event_that_fires_again_and_keeps_its_crossing(m):
    """An event that can fire again and watches a level changes, in each of its outcomes, a value
    that its condition tests."""
    alarm = m['rules']['tank.alarm']
    assert not alarm['once'] and all(o['do']['set'] for o in alarm['outcomes'])
    alarm['outcomes'][1]['do']['set'] = {}
    return [('unsupported_condition', alarm['trigger']['path'])]


def event_that_fires_once_and_keeps_its_crossing(m):
    alarm = m['rules']['tank.alarm']
    alarm['outcomes'][1]['do']['set'] = {}
    alarm['once'] = True
    return []


def lag_of_an_output_that_is_no_tally(m):
    """A lag is for an output that counts up. Its delays are times that read inputs only, and the
    shares of a mixture add up to one."""
    water = m['outcomes']['basin_water']
    assert water['kind'] != 'cumulative'
    water['lag'] = {'type': 'fixed', 'delay': "q(2, 'h')"}
    return [('lag', 'outcomes/basin_water')]


def lag(first, second):
    return {
        'type': 'mixture',
        'components': [{'weight': first, 'delay': "q(1, 'h')"}, {'weight': second, 'delay': "q(2, 'h')"}],
    }


def shares_of_a_lag_that_add_up_to_less_than_one(m):
    assert m['outcomes']['pumped']['kind'] == 'cumulative'
    m['outcomes']['pumped']['lag'] = lag(0.5, 0.4)
    return [('lag', 'outcomes/pumped')]


def shares_of_a_lag_that_add_up_to_one(m):
    m['outcomes']['pumped']['lag'] = lag(0.25, 0.75)
    return []


def delay_of_a_lag_that_is_no_time(m):
    m['outcomes']['pumped']['lag'] = {'type': 'uniform', 'min': "q(1, 'h')", 'max': "q(2, 'L')"}
    return [('expression', 'outcomes/pumped/lag/1')]


def delay_of_a_lag_that_reads_a_state(m):
    m['outcomes']['pumped']['lag'] = {'type': 'fixed', 'delay': 'basin.water / tank.drain_rate'}
    return [('expression', 'outcomes/pumped/lag/0')]


def outputs_that_read_each_other(m):
    m['outcomes']['fullest']['expr'] = 'emptiest'
    m['outcomes']['emptiest']['expr'] = 'fullest'
    return [('cycle', 'outcomes')]


def formulas_that_read_each_other(m):
    m['computed']['basin.fullest']['expr'] = 'basin.emptiest'
    m['computed']['basin.emptiest']['expr'] = 'basin.fullest'
    return [('cycle', 'computed')]


def people(m):
    """The two meters count people, and the output adds them."""
    for meter in ('meters_1', 'meters_2'):
        m['quantities'][f'{meter}.reading'].update({'unit': 'people', 'initial': '0'})
        m['parameters'][f'{meter}.step']['unit'] = 'people/h'
    m['outcomes']['metered']['unit'] = 'people'
    return ['meters_1.reading', 'meters_2.reading']


def output_that_adds_people_of_no_one_sum(m):
    """An output that adds counts of people adds different people: the parts of one sum check, or
    counts that the file says are distinct."""
    people(m)
    return [('additive', 'outcomes/metered')]


def output_that_adds_people_and_a_record_says_distinct(m):
    people(m)
    m['outcomes']['metered']['additive'] = {'kind': 'assumption', 'explanation': 'Two towns.'}
    return []


def output_that_adds_people_and_says_distinct_with_no_record(m):
    """The builder writes the key of a line `distinct` with no record, with no value."""
    people(m)
    m['outcomes']['metered']['additive'] = None
    return []


def output_that_adds_the_parts_of_one_sum(m):
    parts = people(m)
    total = {**m['partitions']['simulate.1'], 'total': "q(5, 'people')", 'tolerance': None}
    m['partitions']['simulate.9'] = {**total, 'parts': parts, 'path': 'assert:/9'}
    return []


def output_that_adds_a_part_of_a_sum_and_another_count(m):
    parts = people(m)
    total = {**m['partitions']['simulate.1'], 'total': "q(5, 'people')", 'tolerance': None}
    m['partitions']['simulate.9'] = {**total, 'parts': parts[:1], 'path': 'assert:/9'}
    return [('additive', 'outcomes/metered')]


def link_that_a_condition_reads_with_no_basis(m):
    """What an entity acts on of another entity has a basis: the link that the condition of its
    event reads."""
    survey = m['rules']['basin.survey']
    assert survey['entity'] == 'basin' and 'bucket_a.full' in survey['trigger']['when']
    m['links']['basin']['bucket_a.full']['basis'] = None
    return [('link_basis', 'entities/basin/links/bucket_a.full')]


def check_of_the_inputs_that_reads_a_state(m):
    """A check before the run reads inputs, and formulas of inputs, only."""
    check = m['input_checks']['simulate.0']
    check['expr'] = "tank.water >= q(100, 'L')"
    return [('expression', check['path'])]


def check_of_the_state_that_is_a_number(m):
    check = m['state_checks']['simulate.2']
    check['expr'] = 'basin.water'
    return [('expression', check['path'])]


def sum_of_parts_in_two_units(m):
    """The parts of a sum check have one unit, and so have its total and its tolerance."""
    total = m['partitions']['simulate.1']
    total['parts'].append('operators.calls')
    return [('unit', total['path'])]


def total_of_a_sum_in_another_unit(m):
    total = m['partitions']['simulate.1']
    total['total'] = 'operators.close_odds'
    return [('expression', f'{total["path"]}/total')]


def tolerance_of_a_sum_in_another_unit(m):
    total = m['partitions']['simulate.1']
    total['tolerance'] = "q(1, 'h')"
    return [('expression', f'{total["path"]}/tolerance')]


CASES = [value for name, value in list(globals().items()) if getattr(value, '__code__', None) is not None]
CASES = [case for case in CASES if case.__module__ == __name__ and case.__code__.co_varnames[:1] == ('m',)]
CASES.remove(people)


@pytest.mark.parametrize('case', CASES, ids=lambda case: case.__name__)
def test_each_check_gives_its_code_at_the_place_of_the_part(model, case):
    expected = []
    assert found(model, lambda m: expected.extend(case(m))) == expected


# ---- the names that move, and the names that change only at moments ---------------------------------


def test_the_quantities_that_move_are_the_ends_of_the_flows_and_those_with_a_rate(model):
    (mapping,) = (item.plain() for item in model.structures.values())
    ends = {flow[end] for flow in mapping['flows'].values() for end in ('from', 'to') if end in flow}
    structure, _ = changed(model)
    assert checks.evolving_parts(structure) == ends | set(mapping['rates'])
    # Each kind is there: a quantity that a flow only fills, one that it only drains, one with a rate.
    assert {'bucket_a.water', 'tank.water', 'meters_1.reading'} <= checks.evolving_parts(structure)
    assert 'bucket_a.water' not in {flow.get('from') for flow in mapping['flows'].values()}

    # A rate that is written as zero moves nothing; a rate with a name can be other than zero.
    def stopped(m):
        m['rates']['meters_1.reading']['expr'] = '0'
        m['rates']['meters_2.reading']['expr'] = '0.0'

    structure, _ = changed(model, stopped)
    assert checks.evolving_parts(structure) == ends
    assert {'meters_1.reading', 'meters_2.reading'} <= checks.discrete_names(structure)


def test_the_names_that_change_only_at_moments_read_nothing_that_moves(model):
    """An input, a named state, a quantity that does not move and the count of an event change only at
    moments. So does a formula or a status that reads no name that moves, through the formulas."""

    def more(m):
        record = m['computed']['basin.held']
        m['computed']['tank.half'] = {**record, 'expr': 'tank.level0 / 2', 'path': 'tank/half'}
        m['computed']['tank.spare'] = {**record, 'expr': 'tank.half - basin.held', 'path': 'tank/spare'}
        # One case of the status of the basin reads the water of the basin, which moves.
        m['labels']['basin.health']['cases'][1]['when'] = "basin.water > q(1, 'L')"

    structure, _ = changed(model, more)
    names = checks.discrete_names(structure)
    assert {'tank.level0', 'tank.drain', 'operators.calls', 'operators.notice__count'} <= names
    assert {'tank.half', 'tank.health'} <= names
    # The formula of the fixture reads the water of the buckets, and `spare` reads that formula.
    moving = {'tank.water', 'basin.held', 'tank.spare', 'basin.health', 't', 'operators.notice__time'}
    assert not names & moving
    assert names.isdisjoint(checks.evolving_parts(structure))


# ---- the class of a condition ----------------------------------------------------------------------------

OPEN = "tank.drain == 'open'"
# (the condition; its kind; the gate; the times; the quantity, the comparison and the level of a
# crossing; the face), by the definitions of `classify`: a gate reads only values that change at
# moments, a clock is `t >= X` or `t - S >= d`, a crossing is `q >= v` or `q <= v` with `q` moving
# and `v` not, and any other condition on a value that moves is a face.
CLASSES = [
    (f'{OPEN} and operators.calls > 0', 'discrete', f'{OPEN} and operators.calls > 0', None, None, None),
    ('t >= bucket_a.fill_time', 'timer', 'True', ['bucket_a.fill_time'], None, None),
    ('bucket_a.fill_time <= t', 'timer', 'True', ['bucket_a.fill_time'], None, None),
    (
        't - operators.notice__time >= bucket_a.fill_time',
        *('timer', 'True', ['operators.notice__time + bucket_a.fill_time'], None, None),
    ),
    (
        f"{OPEN} and q(2, 'h') <= t - tank.drain__entered",
        *('timer', OPEN, ["tank.drain__entered + q(2, 'h')"], None, None),
    ),
    (
        'tank.water <= tank.level0 / 2',
        'crossing',
        'True',
        None,
        ('tank.water', '<=', 'tank.level0 / 2'),
        None,
    ),
    (
        'tank.level0 / 2 >= tank.water',
        'crossing',
        'True',
        None,
        ('tank.water', '<=', 'tank.level0 / 2'),
        None,
    ),
    ('tank.water >= tank.level0', 'crossing', 'True', None, ('tank.water', '>=', 'tank.level0'), None),
    ('tank.level0 <= tank.water', 'crossing', 'True', None, ('tank.water', '>=', 'tank.level0'), None),
    (
        f'{OPEN} and tank.water >= tank.level0 and t >= bucket_a.fill_time',
        *('crossing', OPEN, ['bucket_a.fill_time'], ('tank.water', '>=', 'tank.level0'), None),
    ),
    # The level moves too: no crossing.
    ('tank.water >= basin.water', 'face', 'True', None, None, 'tank.water >= basin.water'),
    # No `>=` and no `<=`: no crossing.
    ('tank.water > tank.level0', 'face', 'True', None, None, 'tank.water > tank.level0'),
    # A time that moves is no clock.
    ('t >= tank.water / tank.drain_rate', 'face', 'True', None, None, 't >= tank.water / tank.drain_rate'),
    (
        f'{OPEN} and tank.water + basin.water > tank.level0 and basin.water > tank.water',
        *('face', OPEN, None, None, 'tank.water + basin.water > tank.level0 and basin.water > tank.water'),
    ),
]
# Each one reads only what the tank has: its water and its tally of drained water both move.
REFUSED = [
    'tank.water >= tank.level0 and tank.drained >= tank.level0',  # two crossings
    'tank.water >= tank.level0 and tank.water > tank.drained',  # a crossing with a face
    't >= tank.level0 / tank.drain_rate and tank.water > tank.drained',  # a clock with a face
]


def with_condition(structure, when):
    """A rule of the structure with another condition, and no class."""
    return structure.rules['tank.alarm'].changed(trigger=Trigger.of({'when': when, 'path': 'a/place'}))


@pytest.mark.parametrize(('when', 'kind', 'gate', 'times', 'crossing', 'face'), CLASSES)
def test_the_class_of_a_condition_is_that_of_its_definition(model, when, kind, gate, times, crossing, face):
    structure, _ = changed(model)
    discrete, moving = checks.discrete_names(structure), checks.evolving_parts(structure)
    assert {'tank.water', 'basin.water'} <= moving and {'tank.level0', 'bucket_a.fill_time'} <= discrete
    trigger = checks.classify(with_condition(structure, when), structure, discrete, moving)
    assert (trigger.when, trigger.path, trigger.kind) == (nodes.read(when), 'a/place', kind)
    assert trigger.gate is nodes.read(gate)
    assert trigger.times == (None if times is None else tuple(map(nodes.read, times)))
    var, op, level = crossing or (None, None, None)
    assert (trigger.var, trigger.op) == (var, op)
    assert trigger.value is (None if level is None else nodes.read(level))
    assert trigger.face is (None if face is None else nodes.read(face))
    # The time that moves, as a name that the engine holds, changes nothing: the plan gives it.
    assert checks.classify(with_condition(structure, when), structure, discrete, moving | {'t'}) == trigger


@pytest.mark.parametrize('when', REFUSED)
def test_a_condition_with_no_class_is_refused(model, when):
    structure, _ = changed(model)
    discrete, moving = checks.discrete_names(structure), checks.evolving_parts(structure)
    with pytest.raises(ValueError, match='a level rule'):
        checks.classify(with_condition(structure, when), structure, discrete, moving)

    def refused(m):
        m['rules']['tank.alarm']['trigger']['when'] = when

    place = structure.rules['tank.alarm'].trigger.path
    assert found(model, refused) == [('unsupported_condition', place)]


def test_an_event_with_no_condition_has_the_place_of_its_rule(model):
    """The builder writes no place of a condition for an event that only a line fires. The typed
    parts take that trigger, and the checks give it the place of its rule."""
    (mapping,) = (item.plain() for item in model.structures.values())
    rule = mapping['rules']['basin.log']
    assert rule['named'] and rule['trigger']['path'] == rule['path']
    rule['trigger'] = {'when': rule['trigger']['when']}
    structure = Structure.of(mapping)
    assert structure.rules['basin.log'].trigger == Trigger.of({'when': 'False'})
    assert structure.rules['basin.log'].trigger.path is None
    library = thaw(model.library)
    errors, facts = checks.structure_facts(structure, library, UnitSystem(library['units']))
    assert errors == []
    assert facts['triggers']['basin.log'] == model.structures[()].rules['basin.log'].trigger
    assert (
        facts['triggers']['basin.log'].plain()
        == model.structures[()].plain()['rules']['basin.log']['trigger']
    )


# ---- the order of the formulas ----------------------------------------------------------------------------


def formulas(definitions):
    """The typed parts of a structure with the inputs `a` and `b`, the quantity `q` and these
    formulas, and no other part."""
    record = {'kind': 'assumption', 'explanation': 'A part of a test.'}
    part = {'entity': 'e', 'unit': 'fraction', 'basis': record}
    item = {section: {} for section in SECTIONS}
    item['parameters'] = {
        name: {**part, 'label': name, 'value': 1.0, 'adjust': {'mode': 'fixed'}, 'path': f'e/{name}'}
        for name in ('a', 'b')
    }
    item['quantities'] = {'q': {**part, 'kind': 'variable', 'initial': '0', 'path': 'e/q'}}
    item['computed'] = {
        name: {**part, 'expr': text, 'path': f'e/{name}'} for name, text in definitions.items()
    }
    return Structure.of(item)


def after_what_it_reads(order, definitions):
    """Whether each formula of an order comes after each formula that it reads."""
    place = {name: k for k, name in enumerate(order)}
    return all(
        place[read] < place[name]
        for name, text in definitions.items()
        for read in text.split(' + ')
        if read in definitions
    )


def test_each_formula_comes_after_the_formulas_that_it_reads():
    """Formulas `f0` to `f13`, each a sum of names before it, written in a random order. The order of
    the checks has each formula once, after each formula that it reads. The order of the names is
    no such order in some case (`f10` reads `f2`), so the property is not empty."""
    library = b.library()
    units = UnitSystem(library['units'])
    by_name = []
    for seed in range(12):
        rng = random.Random(seed)
        definitions = {}
        for k in range(14):
            reads = rng.sample(['a', 'b', 'q', *(f'f{j}' for j in range(k))], rng.randint(1, min(3, k + 3)))
            definitions[f'f{k}'] = ' + '.join([*reads, repr(float(rng.randint(1, 9)))])
        names = list(definitions)
        rng.shuffle(names)
        definitions = {name: definitions[name] for name in names}
        errors, facts = checks.structure_facts(formulas(definitions), library, units)
        order = facts['computed_order']
        assert errors == [] and sorted(order) == sorted(definitions)
        assert after_what_it_reads(order, definitions)
        by_name.append(after_what_it_reads(sorted(definitions), definitions))
    assert not all(by_name)


def test_formulas_on_a_circle_have_no_order():
    library = b.library()
    circle = formulas({'x': 'y + 1.0', 'y': 'z + 1.0', 'z': 'x + a', 'free': 'a + b'})
    errors, facts = checks.structure_facts(circle, library, UnitSystem(library['units']))
    assert [(item['code'], item['path']) for item in errors] == [('cycle', 'computed')]
    assert facts['computed_order'] == []
