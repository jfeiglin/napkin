"""The equations of a card (D-53, napkin/draw/equations.py): each line of a block says what the model
says, in the trees of the notation.

The model of these tests writes each part that a block shows once. Each expected tree is worked out by
hand from the text of the model and the rules of the module's text: a balance is the flows in minus
the flows out, a route takes from its first end and gives to its second, a request is what a flow
asks, a capacity bounds it, a formula follows the requests within `depth` hops, a range is a bound, an
endpoint's settings are a share, the legs of a flow move together, and each assignment and move of a
stage is a jump. The catalogue test (`test_catalogue.py`, for stage M) checks the same properties on
every model.
"""

from __future__ import annotations

import pytest

from napkin.draw import notation
from napkin.draw.equations import KINDS, WORDS, Equations, Line, generic, same
from napkin.draw.notation import Assign, Call, Cases, Cmp, Deriv, Neg, Num, Op, Sym, Text
from napkin.draw.things import Things
from tests.draw.models import compiled

MODEL = """\
scenario "Equations"
    horizon 10 h

options "Timing":
    "Early":
        "Early."
    "Late":
        "Late."
        plant.late = true  @fixture

runs:
    early = "Early"
    late = "Late"

plant:
    "The plant."
    raw: L = 50 L in [0 L, 100 L]
    clean: L = 0 L in [0 L,]
        outflow.capacity = 8 L/h
        outflow.allocation = priority(town.take, this.waste)
    total: L = 0 L in [0 L,]
    input speed: L/h = 4 L/h in [0 L/h, 20 L/h]
    input late: bool = false  @fixture
    busy: bool = false
    spares = 3 in [0, 5]
    pace = formula(this.speed * this.factor)
    factor = formula(2 if this.busy else 1)
    deep = formula(this.pace + 1 L/h)
    flow intake: SOURCE -> this.raw
        request = 6 L/h
    flow treat: this.raw -> this.clean
        request = this.deep
        capacity = 10 L/h
    flow waste: this.clean -> SINK
        request = 1 L/h
    flow count: SOURCE -> this.total
        request = this.pace
    shift = event():
        after 1 h:
            move 5 L from this.raw to this.clean
            this.spares -= 1
            this.busy = true
    rain = event():
        when this.late and t >= 2 h:
            this.rain.start()
            reset when false
        flow drip: SOURCE -> this.raw
            request = 2 L/h
        after 1 h:
            this.spares += 2
    assert this.raw <= 100 L

town:
    stored: L = 0 L in [0 L,]
    flow take: plant.clean -> this.stored
        request = 5 L/h

west:
    water: L = 10 L in [0 L, 20 L]

east:
    water: L = 10 L in [0 L, 20 L]

channel:
    flow link: west.water <-> east.water
        request = -3 L/h
        capacity = 4 L/h

site:
    work: L = 100 L in [0 L,]
    done: L = 0 L in [0 L,]
    flow restore:
        flow labor: this.work -> this.done
            request = 4 L/h
        flow spend: this.work -> SINK
            request = 1 L/h

crews:
    fix = event():
        after 0 h:
            plant.spares += 1
            switch categorical(GOOD: 0.5, BAD: 0.5).draw():
                GOOD:
                    plant.busy = false
                BAD:
                    plant.spares -= 1

Zone:
    input need: L = 1 L in [0 L,]
    level: L = 0 L in [0 L,]
    flow fill: town.stored -> this.level
        request = this.need / (1 h)

north: Zone

south: Zone
    need = 2 L  @fixture

Pipe:
    home: Zone
    held: L = 0 L in [0 L,]
    seen = formula(this.home.need / (1 h))
    flow drain: this.held -> SINK
        request = this.seen

p1: Pipe
    home = north

p2: Pipe
    home = south

plant.shift.start()
crews.fix.start()

record fixture: assumption "A synthetic test fixture."
"""


@pytest.fixture(scope='module')
def found():
    return Things(compiled(MODEL))


@pytest.fixture(scope='module')
def joined(found):
    return Equations(found)


def lines(block, kind):
    return block.of(kind)


def S(key):
    return Sym(key)


def test_a_balance_is_the_flows_in_minus_the_flows_out(joined):
    block = joined.block('plant')
    balances = {line.part: line.rhs for line in lines(block, 'balance')}
    # The rain's drip fills the raw water while its occurrence lasts: a run with the option "Late" can
    # start it, so the joined runs hold it.
    assert balances == {
        'plant.raw': Op('-', Op('+', S('plant.intake'), S('plant.rain.drip')), S('plant.treat')),
        'plant.clean': Op('-', Op('-', S('plant.treat'), S('plant.waste')), S('town.take')),
        'plant.total': S('plant.count'),
    }
    assert all(line.lhs == Deriv(line.part) for line in lines(block, 'balance'))
    # The terms keep their signs and their flows, in the order of the right side.
    (clean,) = [line for line in lines(block, 'balance') if line.part == 'plant.clean']
    assert [(term.sign, term.flow) for term in clean.terms] == [
        (1, 'plant.treat'),
        (-1, 'plant.waste'),
        (-1, 'town.take'),
    ]


def test_a_route_takes_from_its_first_end_and_gives_to_its_second(joined):
    (west,) = lines(joined.block('west'), 'balance')
    (east,) = lines(joined.block('east'), 'balance')
    assert (west.rhs, east.rhs) == (Neg(S('channel.link')), S('channel.link'))
    # Its capacity bounds its magnitude, and its request is signed.
    channel = joined.block('channel')
    assert [line.rhs for line in lines(channel, 'rate')] == [Neg(Num(3, 'L/h'))]
    assert [line.math for line in lines(channel, 'bound')] == [
        (Cmp(('<=',), (Call('abs', (S('channel.link'),)), Num(4, 'L/h'))),)
    ]


def test_a_request_is_what_a_flow_asks_and_a_capacity_bounds_it(joined):
    block = joined.block('plant')
    requests = {line.part: line.rhs for line in lines(block, 'rate')}
    assert requests == {
        'plant.intake': Num(6, 'L/h'),
        'plant.treat': S('plant.deep'),
        'plant.waste': Num(1, 'L/h'),
        'plant.count': S('plant.pace'),
        'plant.rain.drip': Num(2, 'L/h'),
    }
    assert all(line.lhs == Call('request', (S(line.part),)) for line in lines(block, 'rate'))
    capacity = [line for line in lines(block, 'bound') if line.part == 'plant.treat']
    assert [line.math for line in capacity] == [(Cmp(('<=',), (S('plant.treat'), Num(10, 'L/h'))),)]


def test_the_formulas_follow_the_requests_within_depth_hops(found, joined):
    def formulas(depth):
        return [
            (line.part, line.hop, line.rhs) for line in lines(joined.block('plant', depth=depth), 'formula')
        ]

    deep = ('plant.deep', 1, Op('+', S('plant.pace'), Num(1, 'L/h')))
    pace = ('plant.pace', 1, Op('*', S('plant.speed'), S('plant.factor')))
    factor = ('plant.factor', 2, Cases(((S('plant.busy'), Num(2)),), Num(1)))
    assert formulas(0) == []
    assert formulas(1) == [deep, pace]
    assert formulas(2) == [deep, pace, factor]
    # An input is a name in the line: the search goes through formulas only.
    assert formulas(5) == formulas(2)


def test_a_range_is_a_bound_with_the_words_of_what_moves_it(joined):
    bounds = {
        line.part: (line.math, line.words) for line in lines(joined.block('plant'), 'bound') if line.words
    }
    assert bounds == {
        'plant.raw': (
            (Cmp(('<=', '<='), (Num(0, 'L'), S('plant.raw'), Num(100, 'L'))),),
            WORDS['bound_flows'],
        ),
        'plant.clean': ((Cmp(('>=',), (S('plant.clean'), Num(0, 'L'))),), WORDS['bound_flows']),
        'plant.total': ((Cmp(('>=',), (S('plant.total'), Num(0, 'L'))),), WORDS['bound_flows']),
        # A number that no flow moves: past its bound the run stops.
        'plant.spares': ((Cmp(('<=', '<='), (Num(0), S('plant.spares'), Num(5))),), WORDS['bound_stops']),
    }


def test_the_settings_of_an_endpoint_are_a_share(joined):
    (share,) = lines(joined.block('plant'), 'share')
    assert share.math == (
        Cmp(('<=',), (Call('outflow', (S('plant.clean'),)), Num(8, 'L/h'))),
        Call('priority', (S('town.take'), S('plant.waste'))),
    )
    assert share.words == WORDS['priority'] and share.flows == ('town.take', 'plant.waste')


def test_the_legs_of_a_flow_move_together(joined):
    block = joined.block('site')
    (together,) = lines(block, 'together')
    assert together.math == (S('site.restore.labor'), S('site.restore.spend'))
    assert together.words == WORDS['together']
    balances = {line.part: line.rhs for line in lines(block, 'balance')}
    assert balances == {
        'site.work': Op('-', Neg(S('site.restore.labor')), S('site.restore.spend')),
        'site.done': S('site.restore.labor'),
    }


def test_each_assignment_and_move_of_a_stage_is_a_jump(joined):
    jumps = [(line.event, line.outcome, line.math) for line in lines(joined.block('plant'), 'jump')]
    assert jumps == [
        # A move with both ends on the member is one line with both changes.
        (
            'plant.shift',
            None,
            (Assign('plant.raw', '-=', Num(5, 'L')), Assign('plant.clean', '+=', Num(5, 'L'))),
        ),
        ('plant.shift', None, (Assign('plant.spares', '-=', Num(1)),)),
        ('plant.shift', None, (Assign('plant.busy', '=', Text(True)),)),
        ('plant.rain', None, (Assign('plant.spares', '+=', Num(2)),)),
        # Another card's event, and the case of a switch.
        ('crews.fix', None, (Assign('plant.spares', '+=', Num(1)),)),
        ('crews.fix', 'GOOD', (Assign('plant.busy', '=', Text(False)),)),
        ('crews.fix', 'BAD', (Assign('plant.spares', '-=', Num(1)),)),
    ]


def test_a_run_leaves_out_the_events_that_it_cannot_start(found):
    early, late = Equations(found, 'early'), Equations(found, 'late')
    # Without the option "Late" the rain never starts: no jump, and no drip in the balance.
    assert [line.event for line in lines(early.block('plant'), 'jump')].count('plant.rain') == 0
    assert [line.event for line in lines(late.block('plant'), 'jump')].count('plant.rain') == 1
    (raw,) = [line for line in lines(early.block('plant'), 'balance') if line.part == 'plant.raw']
    assert raw.rhs == Op('-', S('plant.intake'), S('plant.treat'))
    assert 'plant.rain.drip' not in {line.part for line in lines(early.block('plant'), 'rate')}


def test_the_checks_show_only_when_asked(joined):
    assert lines(joined.block('plant'), 'check') == ()
    (check,) = lines(joined.block('plant', checks=True), 'check')
    assert check.math == (Cmp(('<=',), (S('plant.raw'), Num(100, 'L'))),)


def test_the_kinds_of_a_block_are_in_their_order(joined):
    block = joined.block('plant', checks=True)
    order = [KINDS.index(line.kind) for line in block.lines]
    assert order == sorted(order)
    assert {line.kind for line in block.lines} == set(KINDS) - {'together'}


def test_the_keys_of_a_line_are_those_of_its_trees(joined):
    (clean,) = [line for line in lines(joined.block('plant'), 'balance') if line.part == 'plant.clean']
    assert clean.keys == ('plant.clean', 'plant.treat', 'plant.waste', 'town.take')
    keys = joined.block('plant').keys
    assert keys == tuple(dict.fromkeys(key for line in joined.block('plant').lines for key in line.keys))


def test_members_with_the_same_trees_are_one_block_and_a_link_to_another_member_is_not(found, joined):
    # A member's own value is a symbol of the line: north and south have one block.
    (zones,) = joined.template('Zone')
    assert zones.members == ('north', 'south')
    assert same(joined.block('north'), joined.block('south'))
    assert generic(zones.blocks[0], 'Zone') == zones.block
    (balance,) = lines(zones.block, 'balance')
    assert balance.rhs == S('Zone.fill') and balance.part == 'Zone.level'
    # A formula that reads through a link names the member that the link names: p1 reads north, p2
    # south, so the two blocks differ.
    pipes = joined.template('Pipe')
    assert [group.members for group in pipes] == [('p1',), ('p2',)]
    (seen,) = lines(joined.block('p1'), 'formula')
    assert seen.rhs == Op('/', S('north.need'), Num(1, 'h'))


def test_a_line_is_one_form_or_the_other():
    with pytest.raises(ValueError):
        Line('rate', None, None, (), None, None, ())
    with pytest.raises(ValueError):
        Line('bound', S('a.x'), Num(1), (), None, None, ())
    with pytest.raises(ValueError):
        Line('bound', None, None, (), None, None, ())
    with pytest.raises(ValueError):
        Line('rate', S('a.x'), Num(1), (), None, None, (), relation='⇔')
    with pytest.raises(ValueError):
        Line('jumps', None, None, (Num(1),), None, None, ())
    assert Line('formula', S('a.x'), Num(1), (), None, None, (), relation='⇔').relation == '⇔'


def test_a_wrong_member_depth_run_or_template_is_an_error(found, joined):
    with pytest.raises(ValueError, match='member'):
        joined.block('nowhere')
    with pytest.raises(ValueError, match='depth'):
        joined.block('plant', depth=-1)
    with pytest.raises(ValueError, match='run'):
        Equations(found, 'nowhere')
    with pytest.raises(ValueError, match='template'):
        joined.template('plant')


def test_each_tree_of_each_block_writes_its_latex(found, joined):
    for member in found.template_of:
        for line in joined.block(member, depth=3, checks=True).lines:
            for tree in line.trees:
                assert notation.latex(tree, lambda key: key.replace('_', r'\_'))
