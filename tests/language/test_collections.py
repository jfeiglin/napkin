"""Templates, members and collections (`napkin/model/semantic.py` and the lowering): links and paths
through them, `Template.instances`, literals, projections and the six reductions, `where` on fixed
fields, `by` and `.at` with their keys, assertions over inputs, members written by hand, and the
order of starting values across members. A source text gives the program that the builder makes of
the same model, and each refusal has its code and its line."""

import textwrap

import pytest

from napkin.engine import read, run
from napkin.model import semantic as s
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import (
    BOOL,
    Builder,
    TemplateHandle,
    assertion,
    count,
    fall,
    fany,
    fmax,
    fmin,
    formula,
    fsum,
    group_of,
    ifelse,
    input_,
    item,
    link,
    literal,
    named,
    q,
    this,
    value,
)
from napkin.program.canonical import program_bytes
from napkin.program.refs import THIS, By, Instances, Literal, Named, Path, Reduce
from tests.program.examples import UNITS


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def same(text, builder):
    return program_bytes(compiled(text).program) == program_bytes(builder.finish())


PUMPS = """
    Pump:
        input flow_max: L/h = 4 in [0,]
        running: bool = false
        rate = formula(this.flow_max if this.running else 0 L/h)

    Station:
        primary: Pump
        backup: Pump
        readonly pumps: <Pump> = <this.primary, this.backup>
        capacity = formula(sum(this.pumps.rate))
        spare = formula(this.backup.flow_max)

    pump_a: Pump
        flow_max = 6 L/h

    pump_b: Pump
        running = true

    station: Station
        primary = pump_a
        backup = pump_b

    total = formula(sum(Pump.instances.flow_max))
    running_count = formula(count(Pump.instances.running))
    pump_count = formula(count(Pump.instances))
    any_running = formula(any(Pump.instances.running))
    all_running = formula(all(Pump.instances.running))
    largest = formula(max(Pump.instances.flow_max))
    smallest = formula(min(Pump.instances.flow_max))
    """


def test_links_literals_projections_and_the_six_reductions_lower_as_the_builder_makes_them():
    b = Builder(UNITS)
    pump = b.template(
        'Pump',
        input_('flow_max', 'L/h', 4, lower=0),
        value('running', BOOL, False),
        value('rate', 'L/h', formula(ifelse(this.running, this.flow_max, q(0, 'L/h')))),
    )
    station = b.template(
        'Station',
        link('primary', 'Pump'),
        link('backup', 'Pump'),
        value('pumps', group_of('Pump'), literal(this.primary, this.backup), readonly=True),
        value('capacity', 'L/h', formula(fsum(this.pumps.rate))),
        value('spare', 'L/h', formula(this.backup.flow_max)),
    )
    b.member(pump, 'pump_a', flow_max=q(6, 'L/h'))
    b.member(pump, 'pump_b', running=True)
    b.member(station, 'station', primary=named('pump_a'), backup=named('pump_b'))
    pumps = pump.instances
    b.root(
        value('total', 'L/h', formula(fsum(pumps.flow_max))),
        value('running_count', '', formula(count(pumps.running))),
        value('pump_count', '', formula(count(pumps))),
        value('any_running', BOOL, formula(fany(pumps.running))),
        value('all_running', BOOL, formula(fall(pumps.running))),
        value('largest', 'L/h', formula(fmax(pumps.flow_max))),
        value('smallest', 'L/h', formula(fmin(pumps.flow_max))),
    )
    assert same(PUMPS, b)


def test_a_path_that_ends_on_a_collection_value_is_that_collection():
    """`count(this.pumps)` counts the members of the station's collection, and `where` and `by` take
    it as they take `Pump.instances`: the program's checker reads the value as its members (S2)."""
    lines = (
        '        held = formula(count(this.pumps))\n'
        '        strong = formula(count(this.pumps.where(flow_max > 5 L/h)))\n'
        '        first = formula(this.pumps.by(flow_max).at(5 L/h).flow_max)\n'
    )
    text = PUMPS.replace('        spare = formula(this.backup.flow_max)\n', lines)
    station = compiled(text).program.template('Station')
    pumps = Path(THIS, ('pumps',))
    held, strong, first = (dict(station.part(name).init.expr.reads) for name in ('held', 'strong', 'first'))
    assert list(held.values()) == [Reduce('count', pumps)]
    ((_, where),) = strong.items()
    assert (where.op, where.source.start.source) == ('count', pumps)
    ((_, lookup),) = first.items()
    assert lookup.start.source.start == By(pumps, 'flow_max')


def test_a_member_written_by_hand_has_its_values_and_the_members_of_its_links():
    model = compiled(PUMPS).declared
    station = model.part('station')
    assert (station.template, station.line) == ('Station', 20)
    assert [(given.name, given.init) for given in station.links] == [
        ('primary', 'pump_a'),
        ('backup', 'pump_b'),
    ]
    pump_a = model.part('pump_a')
    assert pump_a.values == (
        s.Given('flow_max', s.Const(6, s.Num('L/h', (('time', -1), ('volume', 1)))), (), 15),
    )
    # A step from a collection is a projection: a collection of the field's type, with the keys.
    capacity = model.part('Station.capacity')
    assert capacity.init.body.source.type == s.Many(model.part('Pump.rate').type)


ROUTES = """
    Route:
        origin: Place
        destination: Place
        input length: h = 1

    Place:
        input critical: bool = false
        input rank = 1
        need: L/h = 2
        arriving = formula(count(Route.instances.where(destination == this)))

    p1: Place
        critical = true
        rank = 2

    p2: Place

    r1: Route
        origin = p1
        destination = p2
        length = 3 h

    critical_need = formula(sum(Place.instances.where(critical).need))
    second = formula(Place.instances.by(rank).at(2).need)
    long_routes = formula(count(Route.instances.where(length > 2 h)))
    """


def test_where_by_and_at_lower_as_the_builder_makes_them():
    b = Builder(UNITS)
    routes = TemplateHandle('Route').instances
    route = b.template(
        'Route', link('origin', 'Place'), link('destination', 'Place'), input_('length', 'h', 1)
    )
    place = b.template(
        'Place',
        input_('critical', BOOL, False),
        input_('rank', '', 1),
        value('need', 'L/h', 2),
        value('arriving', '', formula(count(routes.where(item.destination == this)))),
    )
    b.member(place, 'p1', critical=True, rank=2)
    b.member(place, 'p2')
    b.member(route, 'r1', origin=named('p1'), destination=named('p2'), length=q(3, 'h'))
    b.root(
        value('critical_need', 'L/h', formula(fsum(place.instances.where(item.critical).need))),
        value('second', 'L/h', formula(place.instances.by('rank').at(2).need)),
        value('long_routes', '', formula(count(route.instances.where(item.length > q(2, 'h'))))),
    )
    assert same(ROUTES, b)


def test_assertions_over_inputs_and_over_state_lower():
    text = """
        Pump:
            input low: L/h = 1
            input high: L/h = 4
            assert this.low < this.high
        assert sum(Pump.instances.high) <= 100 L/h
        """
    b = Builder(UNITS)
    pump = b.template(
        'Pump', input_('low', 'L/h', 1), input_('high', 'L/h', 4), assertion(this.low < this.high)
    )
    b.root(assertion(fsum(pump.instances.high) <= q(100, 'L/h')))
    assert same(text, b)
    assert [item.path for item in compiled(text).declared.asserts] == ['assert[0]']
    assert compiled(text).declared.asserts[0].fixed
    # An assertion over state is checked after every round (S4): it lowers, and it is not fixed.
    over_state = compiled('Pump:\n    level: L = 1\n    assert this.level > 0 L\n')
    (declared,) = [part for part in over_state.declared.entities[0].parts if part.path == 'Pump.assert[0]']
    assert not declared.fixed and len(over_state.program.template('Pump').asserts) == 1


def test_an_assertion_through_a_deep_chain_of_shared_formulas_is_a_check_of_the_inputs():
    """From tests/model/test_shared_formulas.py: each formula reads the one before it twice, so the
    chain has 2^40 ways to its first formula. Read through formulas, the assertion is over inputs when
    the first one is, and over state when it reads a stock; each formula is looked at once."""
    depth = 40
    chain = [f'f{k} = formula(f{k - 1} + f{k - 1})' for k in range(1, depth + 1)]
    text = '\n'.join(['input w: L = 1', 'f0 = formula(w)', *chain, f'assert f{depth} >= 0 L']) + '\n'
    assert [item.path for item in compiled(text).declared.asserts] == ['assert[0]']
    assert compiled(text).declared.asserts[0].fixed
    assert not compiled(text.replace('input w: L = 1', 'w: L = 1')).declared.asserts[0].fixed
    # A member that replaces the formula that an assertion reads may read state with it.
    replaced = 'Pump:\n    input low = 1\n    level = 2\n    ok = formula(this.low > 0)\n    assert this.ok\na: Pump\n'

    def fixed(text):
        return next(
            part.fixed for part in compiled(text).declared.entities[0].parts if part.path == 'Pump.assert[0]'
        )

    assert fixed(replaced) and not fixed(replaced + '    ok = formula(this.level > 0)\n')


# ---- a template's instances, from tests/model/test_template_lists.py -------------------------------


def test_a_template_s_instances_and_a_literal_of_its_members_name_the_same_members():
    text = 'Tank:\n    got: L = 0\na1: Tank\na2: Tank\nby_name = formula(sum(Tank.instances.got))\n'
    written = text.replace('sum(Tank.instances.got)', 'sum(<a1, a2>.got)')
    reads = [dict(compiled(each).program.root[0].init.expr.reads) for each in (text, written)]
    assert list(reads[0].values()) == [Reduce('sum', Path(Instances('Tank'), ('got',)))]
    members = (Path(Named('a1')), Path(Named('a2')))
    assert list(reads[1].values()) == [Reduce('sum', Path(Literal(members), ('got',)))]


def test_a_template_with_no_instances_gives_an_empty_collection():
    found = compiled('Tank:\n    got: L = 0\ntotal = formula(sum(Tank.instances.got))\n').program
    assert found.template('Tank').members == ()


def test_an_empty_literal_takes_its_type_from_its_declaration():
    text = 'Tank:\n    got: L = 0\nHolder:\n    tanks: <Tank>\n    held = formula(sum(this.tanks.got))\n'
    holder = compiled(text + 'holder: Holder\n    tanks = <>\n').program.template('Holder')
    assert dict(holder.members[0].values)['tanks'] == Path(Literal(()))
    found = refused('loose:\n    things = <>\n', 'collection', 2)
    assert 'needs its type' in found.message


# ---- refusals ---------------------------------------------------------------------------------------


def refused(text, code, line=None):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert code in caught.value.codes, caught.value
    found = caught.value.problems[caught.value.codes.index(code)]
    if line is not None:
        assert found.line == line, found
    return found


@pytest.mark.parametrize(
    ('line', 'code', 'words'),
    [
        ('x = formula(count(Pump.instances.flow_max))', 'type', 'sum(c.f) is the total'),
        ('x = formula(sum(Pump.instances))', 'type', 'sum takes numbers'),
        ('x = formula(any(Pump.instances.flow_max))', 'type', 'any takes yes/no'),
        ('x = formula(min(3))', 'collection', 'min of values is min(a, b)'),
        ('x = Pump.instances.flow_max', 'collection', 'a projection is no list'),
        ('x = formula(Pump.instances.flow_max + 1 L/h)', 'type', 'reduce one'),
        ('x = formula(count(Pump.instances.where(running)))', 'where_live', 'running is not'),
        ('x = formula(count(Pump.instances.where(rate > 0 L/h)))', 'where_live', 'rate is not'),
        ('x = formula(Pump.instances.by(running).at(1).rate)', 'type', 'a key is a number'),
        ('x = formula(Pump.instances.by(flow_max).at(2 L).rate)', 'unit', 'reads a key in L/h'),
        ('x = formula(count(<pump_a, station>))', 'collection', 'one template'),
        ('x = formula(count(<pump_a, pump_a>))', 'duplicate_literal', 'each member once'),
        # A template with no instances still checks the names that its collection reads.
        (
            'Spare:\n    size: L = 1\nx = formula(sum(Spare.instances.sise))',
            'unknown_name',
            'did you mean size',
        ),
        ('x = formula(Pump.flow_max)', 'unknown_name', 'Pump.instances names its members'),
        ('x = formula(sum(Pumps.instances.rate))', 'unknown_name', 'did you mean Pump'),
        ('main = pump_a', 'link', 'a link belongs to an entity or a template'),
        ('holder:\n    first: Pump', 'link', 'names no member'),
        ('other: Station\n    primary = pump_a', 'link_unset', 'sets no backup'),
        ('other: Station\n    primary = station\n    backup = pump_b', 'type', 'a member of Pump'),
        (
            'other: Station\n    primary = pump_a.flow_max\n    backup = pump_b',
            'link',
            'a link names a member',
        ),
        ('pump_c: Pump\n    flow_max = 3 L', 'unit', 'flow_max of Pump is L/h'),
        ('pump_c: Pump\n    flow_max = -1 L/h', 'range', 'below the range of flow_max'),
        ('pump_c: Pump\n    rate = 3 L/h', 'formula', 'replaces it with formula'),
        ('pump_c: Pump\n    flow_maxx = 3 L/h', 'unknown_name', 'did you mean flow_max'),
        ('pump_c: Pump\n    running = true\n    running = false', 'property', 'given twice'),
    ],
)
def test_a_collection_a_link_or_a_member_is_refused_with_its_code(line, code, words):
    found = refused(PUMPS.rstrip(' ') + textwrap.indent(line, '    ') + '\n', code)
    assert words in found.message, found


def test_a_starting_value_outside_its_range_is_refused():
    refused('tank:\n    water: L = 30 in [0, 20]\n', 'range', 2)


# ---- the order of starting values ------------------------------------------------------------------


def test_starting_values_follow_their_dependencies_across_members_whatever_the_order_of_the_file():
    text = """
        total = a.y + 1
        Box:
            y = 2
            twice = formula(2 * this.y)
            all_y = formula(sum(Box.instances.y))
        a: Box
            y = c.twice + 1
        c: Box
        both = a.all_y + c.all_y
        """
    assert [item.name for item in compiled(text).declared.root] == ['total', 'both']


@pytest.mark.parametrize(
    ('text', 'line'),
    [
        ('Box:\n    y = 2\na: Box\n    y = b.y + 1\nb: Box\n    y = a.y + 1\n', 4),
        ('Box:\n    x = 1\n    y = this.x\na: Box\n    x = this.y + 1\n', 5),
        ('Box:\n    y = 2\n    s = formula(sum(Box.instances.y))\na: Box\n    y = this.s\n', 5),
        ('Box:\n    y = 2\na: Box\n    y = total\ntotal = sum(Box.instances.y)\n', 5),
    ],
)
def test_a_cycle_of_starting_values_across_members_is_refused_at_a_value_on_it(text, line):
    found = refused(text, 'cycle', line)
    assert 'no order' in found.message


# Every utility's total is its own demand and the totals of its children (PLAN, change 19). The
# template reads itself, and no member does: c reads a and b, b reads a, and a reads nothing.
UTILITIES = """
    scenario "Utilities"
        horizon 1 h
    Utility:
        demand: L/h = 1 L/h
        children: <Utility> = <>
        total: formula(L/h) = formula(this.demand + sum(this.children.total))
        held: L = 1 h * this.demand + sum(this.children.held)
    a: Utility
        demand = 2 L/h
    b: Utility
        demand = 3 L/h
        children = <a>
    c: Utility
        demand = 5 L/h
        children = <a, b>
    """


def test_a_template_that_reads_itself_through_other_members_is_no_cycle():
    """The cycles are checked on the members' connections, which links fix when the model compiles
    (R-A1-30): a formula and a starting value that sum the children's are computed child first. The
    totals are a = 2, b = 3 + 2 = 5 and c = 5 + 2 + 5 = 12 L/h, and the starting values the same
    in litres."""
    model = compiled(UTILITIES)
    record = run(model.program, model.configuration)
    found = read(record, model.program, [f'{m}.{name}' for name in ('total', 'held') for m in 'abc'], [0])
    assert [item.values[0] for item in found] == [2, 5, 12, 2, 5, 12]


def test_a_cycle_among_the_members_is_reported_as_its_chain():
    """a and b are each other's child: a's total reads b's, which reads a's, and so do their starting
    values. Each cycle is one problem, at the line of the template's value."""
    text = UTILITIES.replace('demand = 2 L/h\n', 'demand = 2 L/h\n        children = <b>\n')
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    found = [(item.code, item.line, item.message) for item in caught.value.problems]
    assert found == [
        ('cycle', 7, 'a.total reads b.total reads a.total: the values on a cycle have no order'),
        ('cycle', 8, 'a.held reads b.held reads a.held: the values on a cycle have no order'),
    ]


def test_a_member_that_reads_itself_is_reported_as_its_chain():
    found = refused(UTILITIES.replace('children = <a>', 'children = <b>'), 'cycle')
    assert found.message.startswith('b.total reads b.total: ')


# The ties of the water model (HANDOFF, question 4): what a utility asks of its sellers is its need,
# which counts what its own buyers ask of it. Through the templates, `Utility.asks` reads `Tie.ask`,
# which reads `Utility.need`, which reads `Utility.asks`; member by member, a sells to b and b to c.
TIES = """
    scenario "Ties"
        horizon 1 h
    Utility:
        demand: L/h = 1 L/h
        sells: <Tie> = Tie.instances.where(seller == this)
        asks: formula(L/h) = formula(sum(this.sells.ask))
        need: formula(L/h) = formula(this.demand + this.asks)
    Tie:
        seller: Utility
        buyer: Utility
        ask: formula(L/h) = formula(this.buyer.need)
    a: Utility
        demand = 2 L/h
    b: Utility
        demand = 3 L/h
    c: Utility
        demand = 5 L/h
    ab: Tie
        seller = a
        buyer = b
    bc: Tie
        seller = b
        buyer = c
    """


def test_a_where_over_links_keeps_the_members_that_it_names_when_cycles_are_checked():
    """A where that compares links is decided when the model compiles: a's sales are the tie ab
    alone. So c needs 5, b needs 3 + 5 = 8 and a needs 2 + 8 = 10 L/h, and the ties ask 8 and 5."""
    model = compiled(TIES)
    record = run(model.program, model.configuration)
    found = read(record, model.program, ['a.need', 'b.need', 'c.need', 'ab.ask', 'bc.ask'], [0])
    assert [item.values[0] for item in found] == [10, 8, 5, 8, 5]


def test_a_circle_of_ties_is_reported_as_its_chain():
    found = refused(TIES + 'ca: Tie\n        seller = c\n        buyer = a\n', 'cycle', 7)
    assert found.message == (
        'a.asks reads ab.ask reads b.need reads b.asks reads bc.ask reads c.need reads c.asks reads ca.ask '
        'reads a.need reads a.asks: the values on a cycle have no order'
    )


def test_a_template_whose_every_member_reads_itself_is_one_problem():
    """A cycle of one shape (the template's total reads itself through each member) is reported once,
    at its first member, and not once for each of the three."""
    text = UTILITIES.replace('children: <Utility> = <>', 'children: <Utility> = <this>')
    text = text.replace('        children = <a>\n', '').replace('        children = <a, b>\n', '')
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert [item.message.split(':')[0] for item in caught.value.problems] == [
        'a.total reads a.total',
        'a.held reads a.held',
    ]


def test_a_template_that_reads_itself_declares_the_type_that_its_members_read():
    """Its type is not known before its value, so a template's value that reads itself through its
    members declares its type; the members' connections then decide."""
    found = refused(UTILITIES.replace('total: formula(L/h) =', 'total ='), 'cycle')
    assert found.message.startswith('Utility.total reads Utility.total') and 'declare its type' in found.message


def test_mutual_links_are_no_cycle():
    text = 'Pair:\n    other: Pair\n    x = formula(this.other.x0)\n    x0 = 1\na: Pair\n    other = b\nb: Pair\n    other = a\n'
    found = compiled(text).program.template('Pair')
    assert [dict(member.links) for member in found.members] == [{'other': 1}, {'other': 0}]
