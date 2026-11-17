"""The analysis of a structure and of a resolved run (`napkin/model/analysis/`).

`structure_facts` and `value_facts` give the diagnostics and the facts, and write nothing into what
they read: the typed parts of a structure and of a run. The typed parts of a structure take its facts
as a copy (`Structure.with_facts`), and `checked` does the two steps: the checks, then the copy with
the facts. The facts of a resolved run are written
where the run is made (`Resolved.over`). The facts are checked against what follows from the model of
this file: the order of its formulas, the class of each of its triggers, the number of its bound.
"""

import copy
import json
import random

import pytest

from napkin.core import expr as nodes
from napkin.expressions import UnitSystem
from napkin.model.analysis import structure as structure_analysis
from napkin.model.analysis import values as value_analysis
from napkin.model.ir import thaw
from napkin.model.structure import SECTIONS, Resolved, Structure
from tests import build as b


def text(rate='rate'):
    """People leave a queue for a tally at `rate` while the service is on. The queue's upper bound is
    an input; one event is a clock, one watches the tally reach a level that a chain of two formulas
    gives."""
    return b.system(
        b.parameter('cap', 40, 'people', 10, 80),
        b.parameter('rate', 2, 'people/h'),
        b.named('state', 'on', 'off'),
        b.stock('queue', 30, maximum='cap'),
        b.stock('served', 0, kind='tally'),
        b.formula('half', 'cap / 2', 'people'),
        b.formula('quarter', 'half / 2', 'people'),
        b.event('stops', 't >= 6 h', once=True, transition='state "on" -> "off"'),
        b.event('enough', 'served >= quarter', once=True),
        b.flow('serve', b.move('queue', 'served'), f'{rate} if state is "on" else 0 people/h'),
        horizon=24,
        outputs=(b.output('served', 's.served', 'people'),),
    )


@pytest.fixture(scope='module')
def model():
    return b.compiled(text())


def written(value):
    """A mapping as text, with the order of its keys."""
    return json.dumps(value, default=repr)


def test_the_facts_of_a_structure_are_found_with_nothing_written_and_written_in_one_place(model):
    library, units = thaw(model.library), UnitSystem(model.library['units'])
    (built,) = model.structures.values()
    whole = built.plain()
    before = written(whole)
    structure = Structure.of(whole)
    errors, facts = structure_analysis.structure_facts(structure, library, units)
    # Nothing is written: not into the typed parts, which cannot change, and not into their mapping.
    assert errors == [] and written(whole) == before == written(structure.plain())
    # Each formula comes after the one that it reads.
    order = facts['computed_order']
    assert order.index('s.half') < order.index('s.quarter') and set(order) == set(whole['computed'])
    # A clock is a timer with its time; a level on a quantity that moves is a crossing.
    triggers = facts['triggers']
    assert triggers.keys() == whole['rules'].keys()
    kinds = {rule: (trigger.kind, trigger.times, trigger.var) for rule, trigger in triggers.items()}
    assert kinds == {
        's.stops': ('timer', (nodes.read("q(6, 'h')"),), None),
        's.enough': ('crossing', None, 's.served'),
    }
    assert triggers['s.enough'].op == '>=' and triggers['s.enough'].value is nodes.read('s.quarter')
    # The structure holds exactly these facts: its mapping has each one as text, with the keys of
    # a trigger in their order.
    assert whole['computed_order'] == order and all(
        written(whole['rules'][r]['trigger']) == written(t.plain()) for r, t in triggers.items()
    )
    # A structure without them, as the builder makes it, gets them from the checks.
    bare = copy.deepcopy(whole)
    del bare['computed_order']
    for rule in bare['rules'].values():
        rule['trigger'] = {key: rule['trigger'][key] for key in ('when', 'path') if key in rule['trigger']}
    assert written(bare) != before
    unchecked = Structure.of(copy.deepcopy(bare))
    errors, found = structure_analysis.structure_facts(unchecked, library, units)
    # The typed parts write an order of the formulas also when it is empty.
    assert errors == [] and found == facts
    assert written(unchecked.plain()) == written({**bare, 'computed_order': []})
    # The typed parts take the facts as a copy, which is the structure of the checked mapping; the
    # structure that the checks read stays as it was.
    made = unchecked.with_facts(found)
    assert made == structure and written(made.plain()) == before
    assert unchecked.computed_order == () and {r.trigger.kind for r in unchecked.rules.values()} == {None}
    # `checked` does the two steps, and writes nothing into the structure that it reads either.
    errors, typed = structure_analysis.checked(unchecked, library, units)
    assert errors == [] and typed == structure and written(typed.plain()) == before
    assert unchecked.computed_order == () and {r.trigger.kind for r in unchecked.rules.values()} == {None}
    # The copy keeps the parts that the structure leaves out.
    left = Structure.of(copy.deepcopy(bare), left_out={'quantities': {'s.x': 'It cannot act.'}})
    assert structure_analysis.checked(left, library, units)[1].left('quantities') == {'s.x': 'It cannot act.'}


def test_the_facts_of_a_resolved_run_are_found_with_nothing_written_and_written_in_one_place(model):
    library = thaw(model.library)
    resolved = model.resolve('a').plain()
    assert resolved['quantities']['s.queue']['max'] == 40.0
    # The run as the resolution has it before its checks: the bound as it is written, and no proof.
    bare = copy.deepcopy(resolved)
    bare['quantities']['s.queue']['max'] = 's.cap'
    proofs = ('proven_zero_stock_faces', 'proven_monotone_crossings', 'proven_cumulative_outcomes')
    for key in proofs:
        del bare[key]
    run = Resolved.of(bare)
    before = written(run.plain())
    errors, facts = value_analysis.value_facts(run, library)
    assert errors == [] and written(run.plain()) == before == written(bare)
    assert facts['bounds'] == {'s.queue': {'max': 40.0}}
    assert [key for key in facts if key != 'bounds'] == list(proofs)
    # The rate is constant while the service is on, so the crossing of the tally needs no proof.
    assert facts['proven_monotone_crossings'] == [] and facts['proven_zero_stock_faces'] == []
    # The facts are written in one place, where the run is made (`Resolved.over`): the bound in its
    # place, and the three proofs after what is there. From the typed structure, what the run has of
    # its own before its checks and these facts, it is the run that the model resolves, but for the
    # keys that only the model adds.
    own = {key: bare[key] for key in Resolved.ALWAYS if key not in proofs}
    own.update({key: facts[key] for key in value_analysis.PROVED})
    made = Resolved.over(model.structure_of('a'), own, facts['bounds'])
    assert made.plain() == {key: value for key, value in resolved.items() if key not in Resolved.NAMED}
    assert list(made.own())[-3:] == list(proofs) == list(value_analysis.PROVED)
    assert written(made.plain()['quantities']) == written(resolved['quantities'])
    # With another value of the input, the bound has that value: the fact is of the values.
    other = copy.deepcopy(resolved)
    other['quantities']['s.queue']['max'] = 's.cap'
    other['values']['s.cap'] = 55.0
    assert value_analysis.value_facts(Resolved.of(other), library)[1]['bounds'] == {'s.queue': {'max': 55.0}}


def test_a_quantity_that_claims_never_to_fall_is_proved_by_its_own_flows(model):
    """The tally of the served people only fills, so its claim holds. The queue that the service
    empties falls: the same claim of it is refused at its place."""
    library = thaw(model.library)
    resolved = model.resolve('a').plain()
    assert resolved['quantities']['s.served']['kind'] == 'cumulative'
    errors, _ = value_analysis.value_facts(Resolved.of(resolved), library)
    assert [item for item in errors if item['code'] == 'cumulative_proof'] == []
    claimed = copy.deepcopy(resolved)
    claimed['quantities']['s.queue']['kind'] = 'cumulative'
    errors, _ = value_analysis.value_facts(Resolved.of(claimed), library)
    path = claimed['quantities']['s.queue']['path']
    assert [(item['code'], item['path']) for item in errors if item['code'] == 'cumulative_proof'] == [
        ('cumulative_proof', path)
    ]


def test_a_bound_that_cannot_be_a_number_is_a_diagnostic_and_stays_as_it_is_written(model):
    library = thaw(model.library)
    broken = model.resolve('a').plain()
    broken['quantities']['s.queue']['max'] = '1 / (s.cap - s.cap)'
    run = Resolved.of(broken)
    before = written(run.plain())
    errors, facts = value_analysis.value_facts(run, library)
    assert [item['code'] for item in errors] == ['bounds'] and facts == {'bounds': {}}
    assert written(run.plain()) == before == written(broken)


def test_a_crossing_of_a_quantity_with_a_moving_rate_is_proved_by_its_one_direction():
    # The rate falls with the queue, so it is not constant between moments; the tally only rises.
    moving = b.compiled(text('rate * queue / cap'))
    facts = value_analysis.value_facts(moving.resolve('a'), thaw(moving.library))[1]
    assert facts['proven_monotone_crossings'] == ['s.enough']


# ---- the formulas that do not move in a run --------------------------------------------------------


def chains(rng, count):
    """Formulas `f0` to `f{count-1}`, each a sum of some names with a number: of the inputs `a` and
    `b`, of the quantity `q`, which moves, and of formulas before it. They are written in a random
    order, so a formula can come before one that it reads."""
    formulas = {}
    for k in range(count):
        names = rng.sample(['a', 'b', 'q', *(f'f{j}' for j in range(k))], rng.randint(1, min(3, k + 3)))
        formulas[f'f{k}'] = ' + '.join([*names, repr(float(rng.randint(1, 9)))])
    written = list(formulas)
    rng.shuffle(written)
    return {name: {'expr': formulas[name]} for name in written}, [f'f{k}' for k in range(count)]


def run_of(values, formulas, order=None):
    """A resolved run, as typed parts, that has these values of inputs and these formulas, and no
    other part. With no order, it has no order of its formulas."""
    record = {'kind': 'assumption', 'explanation': 'A formula of a test.'}
    item = {section: {} for section in SECTIONS}
    item['computed'] = {
        name: {'entity': 'e', 'unit': 'ratio', 'basis': record, 'path': f'e/{name}', **definition}
        for name, definition in formulas.items()
    }
    item['values'] = values
    if order is not None:
        item['computed_order'] = order
    return Resolved.of(item)


def by_passes(formulas, values):
    """The formulas that do not move, by the definition: a formula is one when each name that it
    reads is an input or such a formula. The value is the sum that the formula writes."""
    found = dict(values)
    changed = True
    while changed:
        changed = False
        for name, definition in formulas.items():
            parts = definition['expr'].split(' + ')
            if name not in found and all(part in found for part in parts[:-1]):
                found[name] = sum(found[part] for part in parts[:-1]) + float(parts[-1])
                changed = True
    return found


@pytest.mark.parametrize('seed', range(12))
def test_the_formulas_that_do_not_move_are_those_of_the_definition_with_any_order_or_none(seed):
    """`static_values` gives the inputs and each formula that reads only inputs and such formulas,
    with its value. The oracle takes passes over the formulas until nothing is new. The result is
    the same with the order of the formulas of the structure, with no order, and with an order
    that does not name every formula."""
    rng = random.Random(seed)
    formulas, order = chains(rng, 14)
    values = {'a': 2.0, 'b': 0.5}
    units = UnitSystem(b.library()['units'])
    expected = by_passes(formulas, values)
    moving = [name for name in formulas if name not in expected]
    for given in (order, None, [], order[:-1], [*order[:-1], 'f0']):
        rs = run_of(values, formulas, given)
        assert value_analysis.static_values(rs, units) == pytest.approx(expected)
    # Each case has both kinds. A formula that is no part of the result reads the moving quantity,
    # or a formula that is no part of the result.
    assert moving and len(expected) > len(values)
    for name in moving:
        parts = formulas[name]['expr'].split(' + ')[:-1]
        assert 'q' in parts or set(parts) & set(moving)


# ---- the facts of a trigger are nodes, written as every expression is -------------------------------


@pytest.mark.parametrize(
    'conditions',
    [
        ["s.state == 'on'"],
        ["s.state == 'on'", 's.count > 0'],
        ['a or b', 'not c', 'd if e else f', 'x + 1 > y * (2 - z)'],
    ],
)
def test_the_conditions_of_a_trigger_together_are_one_expression(conditions):
    """The gate of a trigger is the `and` of its conditions: the node that they make, which is the
    node of the conditions in brackets with `and` between them. Its text reads back to the node."""
    parts = [nodes.read(text) for text in conditions]
    together = structure_analysis._all(parts)
    assert together is nodes.read(' and '.join(f'({text})' for text in conditions))
    assert nodes.read(nodes.text(together)) is together


def test_the_time_of_a_clock_is_one_expression():
    """`t - S >= d` is true from the time S + d: the node of that sum, whatever `d` is. Its text
    reads back to the node."""
    discrete = {'s.wait', 's.extra', 's.open__time'}
    for duration in ('s.wait', 's.wait + s.extra', 's.wait if s.extra > 1 else 2 * s.wait'):
        time = structure_analysis._timer(nodes.read(f't - s.open__time >= ({duration})'), discrete)
        assert time is nodes.read(f's.open__time + ({duration})')
        assert nodes.read(nodes.text(time)) is time
    assert structure_analysis._timer(nodes.read('t >= 2 * s.wait'), discrete) is nodes.read('2 * s.wait')
    assert structure_analysis._timer(nodes.read('t - s.open__time >= q'), discrete) is None
