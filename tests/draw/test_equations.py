"""The equations of a card (napkin/draw/equations.py): each line says what the model and its structures
say, read here from the structures and the semantic model by searches of the test's own.

- Balance: the signed terms of each stock's balance are the structure's flows into and out of it, and
  the flows of its tally rate, each once; the right side is the signed sum of the terms' symbols, and
  each symbol is the one of the line that gives its pair's rate.
- Rate: the right side of each rate line is the flow's rate (or the formula's, for a bare name), with
  the `while` case exactly when the flow has a condition.
- Depth: the formulas of a block are those that a breadth-first search of the test reaches from the
  rates, each once, at its number of hops.
- Bounds, shares and `together`: the structure's `quantities`, `allocation` and `coupling`.
- Jumps: each line of an event that changes a value of the entity, once; records: the records of the
  part that each line shows.
- Templates: blocks that are the same up to the instance, and the counterexamples that are not.
- The LaTeX of each tree reads back to the tree (`latex_subset.py`).
"""

from __future__ import annotations

import itertools
import re
from collections import Counter

import pytest

from napkin.core import expr as typed
from napkin.draw import equations, notation
from napkin.draw.equations import WORDS, Equations, Line, generic, same
from napkin.draw.notation import Cases, Cmp, Deriv, Neg, Num, Op, Sym, key_of, split
from napkin.model import resolved
from napkin.model.ir import thaw
from napkin.model.semantic import Assign, Move, Ref, flat_entity, flat_key
from tests.build import (
    BASIS,
    check,
    compiled,
    document,
    entity,
    event,
    flow,
    formula,
    named,
    option,
    options,
    parameter,
    runs,
    share,
    stock,
    template,
)
from tests.draw.test_notation import canonical, latex_back, shape
from tests.helpers import SCENARIO_IDS, catalogue_model

# ---- typed nodes and names ------------------------------------------------------------------------


def node_of(expression):
    """The typed nodes of a semantic expression: its nodes, or its written number or yes/no."""
    if notation.literal(expression):
        return typed.const(thaw(expression.written))
    return expression.node


def refs_in(node):
    """The keys of the values that the typed nodes of an expression name, a list's members too."""
    return [
        key_of(part.entity, part.member)
        for part in resolved.breadth_first(node)
        if isinstance(part, resolved.Ref)
    ]


def signed_leaves(node, sign=1):
    """The (sign, key) of each symbol of a sum of symbols, `a + b - c` or `-a - b`."""
    if isinstance(node, Sym):
        return [(sign, node.key)]
    if isinstance(node, Neg):
        return signed_leaves(node.x, -sign)
    if isinstance(node, Op) and node.op in '+-':
        right = sign if node.op == '+' else -sign
        return signed_leaves(node.left, sign) + signed_leaves(node.right, right)
    raise AssertionError(f'{node!r} is not a sum of symbols')


PAIR = re.compile(r'^(?P<flow>.*)\[(?P<k>\d+)\]$')


def flow_of(scenario, flow_key):
    entity, name = split(flow_key)
    return next(item for item in scenario.entity(entity).flows if item.name == name)


def fid(scenario, flow_key, k):
    """The structure's name of pair k of a flow (docs/python-api.md, the names of the structure):
    `host.flow`, or `host.flow.k` for a flow of several pairs."""
    entity, name = split(flow_key)
    several = len(flow_of(scenario, flow_key).pairs) > 1
    return f'{flat_entity(entity)}.{name}' + (f'.{k}' if several else '')


def member_fid(scenario, member):
    """The structure's name of a pair that a share or `together` names: `entity.flow` or
    `entity.flow[k]`."""
    found = PAIR.match(member)
    return fid(scenario, found['flow'], int(found['k'])) if found else fid(scenario, member, 0)


def rate_key(scenario, flow_key, k):
    """The key of what gives pair k its rate: the pair, with a rate of its own, else the flow."""
    pair = flow_of(scenario, flow_key).pairs[k]
    return f'{flow_key}[{k}]' if pair.rate is not None else flow_key


def held_flow(structure, entity, item):
    """Whether a structure holds a flow: a pair of it, or a tally's rate."""
    name = f'{flat_entity(entity.name)}.{item.name}'
    return (
        name in structure.flows
        or f'{name}.0' in structure.flows
        or any(name in rate.flows for rate in structure.rates.values())
    )


def own_formulas(structure, entity):
    """{key: value} of the formulas of an entity that a structure holds."""
    host = flat_entity(entity.name)
    return {
        key_of(entity.name, value.name): value
        for value in entity.values
        if value.kind == 'formula'
        and value.formula is not None
        and (f'{host}.{value.name}' in structure.computed or host in structure.entities)
    }


def bare(entity, item, rate, formulas):
    """The key of the formula that a rate names alone, of the flow's own entity, with no `while`."""
    node = rate.node
    if item.condition is None and isinstance(node, resolved.Ref) and node.entity == entity.name:
        key = key_of(node.entity, node.member)
        return key if key in formulas else None
    return None


def records(*parts):
    """The records of `.records` values, each once, in order."""
    found = []
    for part in parts:
        for item in [] if part is None else list(part) if isinstance(part, tuple) else [part]:
            if item not in found:
                found.append(item)
    return tuple(found)


# ---- the checks of one structure ------------------------------------------------------------------


def run_of(model, starts):
    return next(run for run, item in model.runs.items() if item['starts'] == starts)


def rate_symbols(blocks):
    """{what moves at a rate: the symbol of the line that gives it}, over every block."""
    return {item: line.lhs for block in blocks.values() for line in block.of('rate') for item in line.flows}


def check_balances(model, structure, blocks, symbols):
    scenario = model.scenario
    for thing in scenario.entities:
        found = blocks[thing.name].of('balance')
        host = flat_entity(thing.name)
        stocks = [
            key_of(thing.name, value.name)
            for value in thing.values
            if value.kind in ('stock', 'tally') and f'{host}.{value.name}' in structure.quantities
        ]
        assert [line.part for line in found] == stocks
        for line in found:
            qid = flat_key(line.part)
            expected = Counter()
            for name, item in structure.flows.items():
                expected[(1, name)] += item.target == qid
                expected[(-1, name)] += item.source == qid
            for name in getattr(structure.rates.get(qid), 'flows', ()):
                expected[(1, name)] += 1
            got = Counter((term.sign, fid(scenario, term.flow, term.pair)) for term in line.terms)
            assert +got == +expected, line.part
            assert set(got.values()) <= {1}, line.part
            assert line.lhs == Deriv(line.part)
            if line.terms:
                leaves = signed_leaves(line.rhs)
                assert leaves == [(term.sign, term.node.key) for term in line.terms]
                # Into the stock first, then out of it.
                assert [term.sign for term in line.terms] == sorted(
                    (t.sign for t in line.terms), reverse=True
                )
            else:
                assert line.rhs == Num(0)
            for term in line.terms:
                assert term.node == symbols[rate_key(scenario, term.flow, term.pair)]


def check_rates(model, structure, blocks):
    for thing in model.scenario.entities:
        found = blocks[thing.name].of('rate')
        formulas = own_formulas(structure, thing)
        moving = Counter(item for line in found for item in line.flows)
        expected = {}
        for item in thing.flows:
            if not held_flow(structure, thing, item):
                continue
            key = key_of(thing.name, item.name)
            if any(pair.rate is None for pair in item.pairs):
                expected[key] = (item, item.rate)
            for k, pair in enumerate(item.pairs):
                if pair.rate is not None:
                    expected[f'{key}[{k}]'] = (item, pair.rate)
        assert moving == Counter(list(expected)), thing.name
        for key, (item, rate) in expected.items():
            (line,) = [line for line in found if key in line.flows]
            taken = bare(thing, item, rate, formulas)
            if taken is not None:
                assert line.lhs == Sym(taken) and line.part == taken
                assert notation.to_node(line.rhs) is node_of(formulas[taken].formula)
                continue
            assert line.lhs == Sym(key) and line.part == key
            want = node_of(rate)
            if item.condition is not None:
                want = typed.if_else(item.condition.node, want, typed.const(0))
            assert notation.to_node(line.rhs) is want, key


def reached(structure, thing, depth):
    """{formula: hops}: the formulas of the entity that a breadth-first search over the names of the
    typed nodes reaches from the rates of its flows within `depth` hops. A rate that names a formula
    alone is that formula's nodes."""
    formulas = own_formulas(structure, thing)
    level, seen = [], set()
    for item in thing.flows:
        if not held_flow(structure, thing, item):
            continue
        rates = [item.rate] if any(pair.rate is None for pair in item.pairs) else []
        rates += [pair.rate for pair in item.pairs if pair.rate is not None]
        for rate in rates:
            taken = bare(thing, item, rate, formulas)
            if taken is not None:
                seen.add(taken)
            level.append(formulas[taken].formula.node if taken is not None else node_of(rate))
        if item.condition is not None:
            level.append(item.condition.node)
    found = {}
    for hop in range(1, depth + 1):
        following = []
        for node in level:
            for key in refs_in(node):
                if key in formulas and key not in seen:
                    seen.add(key)
                    found[key] = hop
                    following.append(node_of(formulas[key].formula))
        level = following
    return found


def check_depth(model, structure, equations_of, depths=(0, 1, 2, 5)):
    for thing in model.scenario.entities:
        for depth in depths:
            found = equations_of.block(thing.name, depth=depth).of('formula')
            assert Counter(line.part for line in found) == Counter(list(reached(structure, thing, depth)))
            assert {line.part: line.hop for line in found} == reached(structure, thing, depth)
            values = own_formulas(structure, thing)
            for line in found:
                assert line.lhs == Sym(line.part)
                assert notation.to_node(line.rhs) is node_of(values[line.part].formula)


def number(node, unit):
    """The number of a bound's tree in the quantity's unit, or None for another unit or an expression."""
    if isinstance(node, Neg):
        found = number(node.x, unit)
        return None if found is None else -found
    if isinstance(node, Num) and node.unit in (None, unit):
        return node.value
    return None


def edges(cmp, key):
    """(low, high) of a bound `lo <= S <= hi`, `S >= lo` or `S <= hi` of the value `key`, None for an
    edge that it lacks."""
    forms = {('<=', '<='): (0, 1, 2), ('>=',): (1, 0, None), ('<=',): (None, 0, 1)}
    low, middle, high = forms[cmp.ops]
    assert cmp.items[middle] == Sym(key)
    return (None if low is None else cmp.items[low]), (None if high is None else cmp.items[high])


def check_bounds(model, structure, blocks):
    for thing in model.scenario.entities:
        found = blocks[thing.name].of('bound')
        lines = {line.part: line for line in found}
        assert len(lines) == len(found)
        for value in thing.values:
            key = key_of(thing.name, value.name)
            quantity = structure.quantities.get(flat_key(key))
            if quantity is None or quantity.binary or (quantity.minimum is None and quantity.maximum is None):
                assert key not in lines, key
                continue
            line = lines.pop(key)
            (cmp,) = line.math
            low, high = edges(cmp, key)
            limits = (quantity.minimum is not None, quantity.maximum is not None)
            assert (low is not None, high is not None) == limits, key
            for node, edge, bound in ((low, 'minimum', value.minimum), (high, 'maximum', value.maximum)):
                if node is None:
                    continue
                if bound is None:
                    # The builder's own minimum of a stock and a tally.
                    assert edge == 'minimum' and node == Num(0) and quantity.minimum == 0
                    continue
                assert notation.to_node(node) is node_of(bound.expression)
                given = number(node, quantity.unit)
                if given is not None and isinstance(getattr(quantity, edge), (int, float)):
                    assert given == pytest.approx(getattr(quantity, edge), rel=1e-12)
            qid = flat_key(key)
            moved = any(qid in (item.source, item.target) for item in structure.flows.values())
            assert line.words == WORDS['bound_flows' if moved else 'bound_stops']
        assert not lines, list(lines)


def owner_of(scenario, name, part):
    """(the entity, the part) whose structure name is `name`: an allocation or a flow."""
    for thing in scenario.entities:
        for item in getattr(thing, part):
            if f'{flat_entity(thing.name)}.{item.name}' == name:
                return thing, item
    raise AssertionError(name)


def check_shares(model, structure, blocks, symbols):
    scenario = model.scenario
    shares = [line for block in blocks.values() for line in block.of('share')]
    assert len(shares) == len(structure.allocation)
    for name, group in structure.allocation.items():
        thing, allocation = owner_of(scenario, name, 'allocations')
        (line,) = [
            line
            for line in blocks[thing.name].of('share')
            if line.part == key_of(thing.name, allocation.name)
        ]
        members = [flow for flow, item in structure.flows.items() if item.allocation == name]
        got = [member_fid(scenario, item) for item in line.flows]
        assert sorted(got) == sorted(members)
        if group.policy == 'priority':
            assert got == list(group.order)
        assert line.words == WORDS[group.policy]
        (cmp,) = line.math
        assert cmp.ops == ('<=',)
        assert notation.to_node(cmp.items[1]) is node_of(allocation.limit)
        pairs = [PAIR.match(item) for item in line.flows]
        keys = [
            rate_key(scenario, found['flow'], int(found['k'])) if found else rate_key(scenario, item, 0)
            for found, item in zip(pairs, line.flows)
        ]
        assert [(1, symbols[key].key) for key in keys] == signed_leaves(cmp.items[0])


def check_together(model, structure, blocks, symbols):
    scenario = model.scenario
    found = [line for block in blocks.values() for line in block.of('together')]
    assert len(found) == len(structure.coupling)
    for name, group in structure.coupling.items():
        thing, item = owner_of(scenario, name, 'flows')
        (line,) = [
            line for line in blocks[thing.name].of('together') if line.part == key_of(thing.name, item.name)
        ]
        assert [member_fid(scenario, member) for member in line.flows] == list(group.flows)
        key = key_of(thing.name, item.name)
        wanted = [symbols[rate_key(scenario, key, int(PAIR.match(member)['k']))] for member in line.flows]
        assert line.math == tuple(dict.fromkeys(wanted))
        assert line.words == WORDS['together']


def operator(line):
    """(the operator of a line, the typed nodes of what it sets, adds or takes)."""
    if not line.augmented:
        return '=', line.value
    return {'Add': '+=', 'Sub': '-='}[line.operator], line.value.right


def check_jumps(model, structure, blocks):
    expected = {thing.name: Counter() for thing in model.scenario.entities}
    for owner in model.scenario.entities:
        for item in owner.events:
            if f'{flat_entity(owner.name)}.{item.name}' not in structure.rules:
                continue
            event_key = key_of(owner.name, item.name)
            for outcome in item.outcomes:
                name = outcome.name if len(item.outcomes) > 1 else None
                for line in outcome.lines:
                    if isinstance(line, Assign) and isinstance(line.target, Ref):
                        op, value = operator(line)
                        target = key_of(line.target.entity, line.target.member)
                        expected[line.target.entity][(event_key, name, ((target, op, value),))] += 1
                    elif isinstance(line, Move):
                        ends = {}
                        for (_, end), op in zip(line.ends, ('-=', '+=')):
                            ends.setdefault(end.entity, []).append(
                                (key_of(end.entity, end.member), op, line.amount)
                            )
                        for thing, changes in ends.items():
                            expected[thing][(event_key, name, tuple(changes))] += 1
    for thing in model.scenario.entities:
        got = Counter(
            (
                line.event,
                line.outcome,
                tuple((node.target, node.op, notation.to_node(node.value)) for node in line.math),
            )
            for line in blocks[thing.name].of('jump')
        )
        assert got == expected[thing.name], thing.name


def check_records(model, blocks):
    scenario = model.scenario
    values = {key_of(thing.name, value.name): value for thing in scenario.entities for value in thing.values}

    def moving(item):
        """The records of a flow or a pair that a rate line names."""
        found = PAIR.match(item)
        if found is None:
            return flow_of(scenario, item).records
        pair = flow_of(scenario, found['flow']).pairs[int(found['k'])]
        return pair.records if pair.records is not None else flow_of(scenario, found['flow']).records

    for thing in scenario.entities:
        block = blocks[thing.name]
        checks = iter(thing.checks)
        for line in block.lines:
            kind = line.kind
            if kind in ('balance', 'formula'):
                want = records(values[line.part].records)
            elif kind == 'rate':
                own = values[line.part].records if line.part in values else None
                want = records(own, *(moving(item) for item in line.flows))
            elif kind == 'bound':
                value = values[line.part]
                written = value.minimum is not None or value.maximum is not None
                want = records(value.records) if written else ()
            elif kind == 'share':
                want = records(
                    next(a for a in thing.allocations if key_of(thing.name, a.name) == line.part).records
                )
            elif kind == 'together':
                want = records(flow_of(scenario, line.part).together.value)
            elif kind == 'jump':
                item = scenario.event(line.event)
                outcome = item.outcome(line.outcome) if line.outcome is not None else item.outcomes[0]
                want = records(outcome.records if outcome.records is not None else item.records)
            else:
                want = records(next(checks).records)
            assert line.records == want, (thing.name, kind, line.part)


def check_lines(blocks):
    """Each line's keys are the keys of its trees (a jump names its event in words, not as a key); its
    trees are of the notation, and their LaTeX reads back to them."""
    for block in blocks.values():
        assert [line.kind for line in block.lines] == sorted(
            (line.kind for line in block.lines), key=equations.KINDS.index
        )
        for line in block.lines:
            named = []
            for tree in line.trees:
                for part in notation.nodes(tree):
                    if isinstance(part, (Sym, Deriv, notation.Elapsed)):
                        named.append(part.key)
                    elif isinstance(part, (notation.Assign, notation.Since, notation.Count)):
                        named.append(part.target)
            assert set(line.keys) == set(named)
            assert len(set(line.keys)) == len(line.keys)
            for tree in line.trees:
                text, back = latex_back(tree)
                assert shape(canonical(back)) == shape(canonical(tree)), text


def check_relations(model, blocks):
    """A formula whose value is a yes/no is written `⇔`; every other equation `=`."""
    types = {
        key_of(thing.name, value.name): value.type
        for thing in model.scenario.entities
        for value in thing.values
    }
    for block in blocks.values():
        for line in block.lines:
            yes_no = line.kind == 'formula' and types.get(line.part) == 'bool'
            assert line.relation == ('⇔' if yes_no else '='), (line.kind, line.part)


def check_structure(model, starts, checks=True, latex=False):
    """Every check above on the structure of `starts`, with the blocks of one of its runs."""
    structure = model.structures[starts]
    found = Equations(model, run_of(model, starts))
    blocks = {thing.name: found.block(thing.name, checks=checks) for thing in model.scenario.entities}
    symbols = rate_symbols(blocks)
    check_balances(model, structure, blocks, symbols)
    check_rates(model, structure, blocks)
    check_depth(model, structure, found)
    check_bounds(model, structure, blocks)
    check_shares(model, structure, blocks, symbols)
    check_together(model, structure, blocks, symbols)
    check_jumps(model, structure, blocks)
    check_records(model, blocks)
    check_relations(model, blocks)
    if latex:
        check_lines(blocks)
    return blocks


# ---- a synthetic model ----------------------------------------------------------------------------


def line(text, records=BASIS):
    return f'{text}  {records}'


OTHER_RECORD = 'record other: identity "Another record of the fixture."'

# A template whose instances share their trees (north, south, the copies), one whose formula is its own
# (east), one that another thing's flow and move reach (west), one whose stock has a record of its own
# (rim); and a thing with every part.
FIXTURE = document(
    'Equations fixture',
    template(
        'Zone',
        parameter('k', 0.5, 'fraction', 0, 1),
        stock('level', 10, 'people', maximum=100, size=None),
        stock('done', 0, 'people', size=None),
        formula('crowd', 'sum(Zone.level) + 1 people', 'people'),
        formula('pull', 'k * level * level / crowd / (1 h)', 'people/h'),
        flow('drain', 'level -> done', 'pull'),
    ),
    entity('north', template='Zone'),
    entity('south', template='Zone'),
    entity('east', line('let pull: people/h = 2 * k * level / (1 h)'), template='Zone'),
    entity('west', template='Zone'),
    entity('rim', line('level = 20 people', '@other'), template='Zone'),
    entity('waves', template='Zone', copies=2),
    entity(
        'hub',
        parameter('x', 2, 'people/h', 1, 9),
        named('mode', 'idle', 'busy'),
        stock('store', 50, 'people', size=None),
        stock('spare', 5, 'people', size=None),
        stock('used', 0, 'people', size=None),
        stock('tally', 0, 'people', size=None),
        stock('n', 0, 'people', minimum=0, maximum=10, size=None),
        stock('free', 1, 'people', minimum=None, size=20),
        formula('f1', 'f2 + x', 'people/h'),
        formula('f2', 'f3 * 2', 'people/h'),
        formula('f3', 'f4 + x', 'people/h'),
        formula('f4', 'x * 1.5', 'people/h'),
        formula('give', 'x / 2', 'people/h'),
        flow('feed', 'store -> spare', 'give'),
        flow('send', 'spare -> used', 'give'),
        flow('pump', 'store -> used', 'f1', condition='mode is "busy"'),
        flow('pull', 'store -> west.level', 'west.pull'),
        flow('tap', 'store ->', 'x'),
        flow('fill', '-> tally', 'x'),
        flow(
            'both',
            ['spare -> used', line('store -> spare at 0.5 * x', '@other'), 'west.done -> east.done'],
            'x',
            condition='mode is "busy"',
        ),
        share('store', '3 * x', ['pump', 'pull', 'feed', 'tap', 'both']),
        share('spare', '2 * x'),
        event('go', 'mode is "busy" and t >= 1 h', 'n += 2 people', 'store -= 1 people'),
        event(
            'swap', 't >= 2 h', 'move 1 people from store to spare', 'move 2 people from spare to west.level'
        ),
        event('fix', 't >= 3 h', 'free = 3 people'),
        event('pick', 't >= 4 h', 'n += 1 people', condition='x > 3 people/h'),
        check('store + spare + used is 100 people', 'A sum', within='1 people'),
        check('n <= 10 people', 'A bound'),
    ),
    option_groups=(
        options(
            'Response', option('Idle', 'It waits.'), option('Busy', 'It works.', line('hub.mode = "busy"'))
        ),
    ),
    run_lines=runs(a=['Idle'], b=['Busy']),
    records=(OTHER_RECORD,),
)


@pytest.fixture(scope='module')
def model():
    return compiled(FIXTURE)


def test_the_fixture_has_each_part_that_a_block_shows(model):
    kinds = {value.kind for thing in model.scenario.entities for value in thing.values}
    assert {'stock', 'tally', 'state', 'formula'} <= kinds
    hub = model.scenario.entity('hub')
    assert any(len(item.pairs) > 1 and any(p.rate is not None for p in item.pairs) for item in hub.flows)
    assert {a.serve is None for a in hub.allocations} == {True, False}
    assert any(len(item.outcomes) > 1 for item in hub.events)
    assert {item.kind for item in hub.checks} >= {'sum', 'always'}
    # A run that leaves out a part that the other run keeps.
    assert len(model.structures) == 2


@pytest.mark.parametrize('starts', [(), ('Busy',)])
def test_each_line_of_a_synthetic_model_says_what_its_structure_says(model, starts):
    check_structure(model, starts, latex=True)


def test_a_flow_between_two_stocks_of_one_card_is_in_both_balances_with_opposite_signs(model):
    found = equations.block(model, 'hub')
    balances = {line.part: line for line in found.of('balance')}
    into = {(term.flow, term.pair) for term in balances['hub.spare'].terms if term.sign == 1}
    out = {(term.flow, term.pair) for term in balances['hub.store'].terms if term.sign == -1}
    assert ('hub.feed', 0) in into & out
    # A flow out of one card into another: in each card's own balance, once.
    west = {line.part: line for line in equations.block(model, 'west').of('balance')}
    assert [(t.sign, t.flow) for t in west['west.level'].terms].count((1, 'hub.pull')) == 1
    assert [(t.sign, t.flow) for t in balances['hub.store'].terms].count((-1, 'hub.pull')) == 1


def test_a_stock_that_no_flow_moves_is_constant_between_moments():
    # A stock and a tally that only a move changes: between moments, nothing moves them.
    synthetic = compiled(
        document(
            'Moves only',
            entity(
                'box',
                stock('a', 5, 'people', size=None),
                stock('b', 0, 'people', size=None),
                event('shift', 't >= 1 h', 'move 1 people from a to b'),
            ),
        )
    )
    (a, b) = equations.block(synthetic, 'box').of('balance')
    assert (a.rhs, b.rhs, a.terms, b.terms) == (Num(0), Num(0), (), ())


def test_a_rate_that_names_a_formula_alone_takes_its_symbol_and_its_line(model):
    found = equations.block(model, 'hub')
    (give,) = [line for line in found.of('rate') if line.part == 'hub.give']
    assert give.lhs == Sym('hub.give') and give.flows == ('hub.feed', 'hub.send')
    # Defined once: not again among the formulas.
    assert 'hub.give' not in {line.part for line in found.of('formula')}
    # With `while`, the formula is a name of the rate, and the formula's own line follows it.
    (pump,) = [line for line in found.of('rate') if line.part == 'hub.pump']
    assert isinstance(pump.rhs, Cases) and pump.rhs.pairs[0][1] == Sym('hub.f1')
    # A formula of another card is a name only: its line is in its own card's block.
    (pull,) = [line for line in found.of('rate') if line.part == 'hub.pull']
    assert pull.rhs == Sym('west.pull')
    assert 'west.pull' in {line.part for line in equations.block(model, 'west').of('rate')}


def test_the_depth_follows_the_formulas_of_the_card(model):
    found = Equations(model)
    hops = {line.part: line.hop for line in found.block('hub', depth=5).of('formula')}
    assert hops == {'hub.f1': 1, 'hub.f2': 2, 'hub.f3': 3, 'hub.f4': 4}
    for depth in range(6):
        assert {line.part for line in found.block('hub', depth=depth).of('formula')} == {
            key for key, hop in hops.items() if hop <= depth
        }


def test_a_size_alone_is_no_bound_and_a_bound_of_a_number_state_shows(model):
    found = {line.part: line for line in equations.block(model, 'hub').of('bound')}
    assert 'hub.free' not in found
    assert found['hub.n'].math == (Cmp(('<=', '<='), (Num(0), Sym('hub.n'), Num(10, 'people'))),)
    assert found['hub.n'].words == WORDS['bound_stops']
    assert found['hub.store'].words == WORDS['bound_flows']


def test_a_move_with_both_ends_on_the_card_is_one_line_with_both_changes(model):
    found = [line for line in equations.block(model, 'hub').of('jump') if line.event == 'hub.swap']
    assert [[(node.target, node.op) for node in line.math] for line in found] == [
        [('hub.store', '-='), ('hub.spare', '+=')],
        [('hub.spare', '-=')],
    ]
    (west,) = [line for line in equations.block(model, 'west').of('jump') if line.event == 'hub.swap']
    assert [(node.target, node.op) for node in west.math] == [('west.level', '+=')]
    (pick,) = [line for line in equations.block(model, 'hub').of('jump') if line.event == 'hub.pick']
    assert pick.outcome == 'done'


def test_a_pair_with_its_own_records_carries_them_and_not_the_flows(model):
    found = equations.block(model, 'hub')
    (own,) = [line for line in found.of('rate') if line.part == 'hub.both[1]']
    (flow_line,) = [line for line in found.of('rate') if line.part == 'hub.both']
    assert own.records == records(model.scenario.entity('hub').flows[-1].pairs[1].records)
    assert own.records != flow_line.records


def test_a_run_leaves_out_the_parts_that_its_structure_leaves_out(model):
    assert 'hub.go' not in model.structure_of('a').rules
    assert 'hub.go' in model.structure_of('b').rules
    events = {
        run: {line.event for line in equations.block(model, 'hub', run=run).of('jump')}
        for run in ('a', 'b', None)
    }
    assert 'hub.go' not in events['a'] and 'hub.go' in events['b'] and 'hub.go' in events[None]
    assert events[None] == events['a'] | events['b']


def test_the_checks_show_only_when_asked(model):
    found = Equations(model)
    assert not found.block('hub').of('check')
    shown = found.block('hub', checks=True).of('check')
    assert len(shown) == len(model.scenario.entity('hub').checks)
    gap, _ = shown[0].math[0].items
    assert isinstance(gap, notation.Call) and gap.name == 'abs'


def test_instances_with_the_same_trees_are_the_same_and_a_changed_formula_is_not(model):
    found = Equations(model)
    names = ('north', 'south', 'east', 'west', 'rim', 'waves.1', 'waves.2')
    blocks = {name: found.block(name) for name in names}
    assert same(blocks['north'], blocks['south'])
    assert same(blocks['waves.1'], blocks['waves.2'])
    assert same(blocks['north'], blocks['waves.1'])
    # A formula of the instance's own, and another thing's flow and move into the instance.
    assert not same(blocks['north'], blocks['east'])
    assert not same(blocks['north'], blocks['west'])
    # The same trees, but a record of the instance's own: its reference marks differ.
    trees = {
        name: [(line.kind, line.trees) for line in generic(blocks[name], 'Zone').lines]
        for name in ('north', 'rim')
    }
    assert trees['north'] == trees['rim']
    assert not same(blocks['north'], blocks['rim'])
    # A list keeps its members: the same list for every instance.
    (crowd,) = [line for line in blocks['north'].of('formula') if line.part == 'north.crowd']
    (listed,) = [node for node in notation.nodes(crowd.rhs) if isinstance(node, notation.Sum)]
    assert len(listed.terms) == 7
    groups = found.template('Zone')
    assert [group.members for group in groups] == [
        ('north', 'south', 'waves.1', 'waves.2'),
        ('east',),
        ('west',),
        ('rim',),
    ]
    for group in groups:
        assert group.name == 'Zone' and group.block.entity == 'Zone'
        for member, own in zip(group.members, group.blocks):
            assert own == found.block(member)
            assert generic(own, 'Zone') == group.block
        # Written with the template's keys: no key of a member, outside a list.
        owners = {
            split(key)[0] for line in group.block.lines for tree in line.trees for key in outside_lists(tree)
        }
        assert 'Zone' in owners and not owners & set(group.members)


def outside_lists(node):
    """The keys of the symbols of a tree that are not members of a list (`Sum`)."""
    if isinstance(node, notation.Sum):
        return []
    found = [node.key] if isinstance(node, (Sym, Deriv)) else []
    if isinstance(node, notation.Assign):
        found.append(node.target)
    for child in notation.children(node):
        found += outside_lists(child)
    return found


def test_a_changed_number_of_an_event_line_makes_two_instances_differ():
    def fixture(second):
        return compiled(
            document(
                'Two cells',
                template(
                    'Cell', stock('level', 5, 'people', size=None), flow('leak', 'level ->', '1 people/h')
                ),
                entity('c1', template='Cell'),
                entity('c2', template='Cell'),
                entity('ops', event('top', 't >= 1 h', 'c1.level += 1 people', f'c2.level += {second}')),
            )
        )

    alike = Equations(fixture('1 people'))
    assert same(alike.block('c1'), alike.block('c2'))
    differ = Equations(fixture('2 people'))
    assert not same(differ.block('c1'), differ.block('c2'))
    assert [group.members for group in differ.template('Cell')] == [('c1',), ('c2',)]


def test_a_line_is_one_form_or_the_other():
    with pytest.raises(ValueError):
        Line('rate', None, None, (Sym('a.b'),), None, 'a.b', ())
    with pytest.raises(ValueError):
        Line('bound', Sym('a.b'), Num(0), (), None, 'a.b', ())
    with pytest.raises(ValueError):
        Line('other', None, None, (Sym('a.b'),), None, 'a.b', ())


def test_a_wrong_entity_depth_run_or_template_is_an_error(model):
    with pytest.raises(ValueError):
        Equations(model, run='missing')
    found = Equations(model)
    for call in (
        lambda: found.block('missing'),
        lambda: found.block('hub', depth=-1),
        lambda: found.block('hub', depth=1.5),
        lambda: found.template('Missing'),
    ):
        with pytest.raises(ValueError):
            call()


# ---- the catalogue --------------------------------------------------------------------------------


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_each_block_of_a_catalogue_model_says_what_its_structures_say(scenario_id):
    model = catalogue_model(scenario_id)
    for k, starts in enumerate(dict.fromkeys(item['starts'] for item in model.runs.values())):
        check_structure(model, starts, latex=k == 0)
    # Joined, a block holds what any of the runs holds.
    joined = Equations(model)
    each = [
        Equations(model, run_of(model, starts))
        for starts in dict.fromkeys(i['starts'] for i in model.runs.values())
    ]
    for thing in model.scenario.entities:
        lines = joined.block(thing.name).lines
        parts = {
            (line.kind, line.part, line.event) for found in each for line in found.block(thing.name).lines
        }
        assert {(line.kind, line.part, line.event) for line in lines} == parts
    # The groups of a template partition its instances, and each group's members are the same.
    for name in model.scenario.templates:
        groups = joined.template(name)
        members = [member for group in groups for member in group.members]
        assert members == [thing.name for thing in model.scenario.entities if thing.template == name]
        for group in groups:
            assert all(same(group.blocks[0], other) for other in group.blocks[1:])
        for a, b in itertools.combinations(groups, 2):
            assert not same(a.blocks[0], b.blocks[0])
