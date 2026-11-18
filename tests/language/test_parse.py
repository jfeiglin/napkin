"""The lexer and the parser (`napkin/model/language/lex.py`, `parse.py`): the lines and tokens of a
text, one tree for one text, the units of D12, ranges with a side left empty, `if`/`else`, guarded
cases, categorical draws and actor choices, and each refusal with its code and its place."""

import textwrap

import pytest

from napkin.model.language import nodes as n
from napkin.model.language.lex import lines
from napkin.model.language.parse import parse, parse_expression
from napkin.model.language.problems import SyntaxProblem


def tree(text):
    return parse(textwrap.dedent(text))


def only(text):
    """The one line of a text at the top level."""
    (item,) = tree(text).items
    return item


def stage(body):
    """The statements of one stage of an event of an entity."""
    text = 'holder:\n    act = event():\n        after 0 h:\n' + textwrap.indent(
        textwrap.dedent(body), ' ' * 12
    )
    (entity,) = parse(text).items
    return entity.members[0].steps[0].body


def refused(text, code, line=None, alone=False):
    with pytest.raises(SyntaxProblem) as caught:
        parse_expression(text) if alone else parse(textwrap.dedent(text))
    assert caught.value.code == code, caught.value
    if line is not None:
        assert caught.value.line == line
    return caught.value


def q(value, *unit):
    """A quantity with its unit run: q(5, 'L', '/h') is `5 L/h`."""
    return n.Quantity(value, (('', unit[0]), *((item[0], item[1:]) for item in unit[1:])))


# ---- the lexer ---------------------------------------------------------------------------------------


def test_comments_end_a_row_and_stay_with_their_line():
    found = lines('x = 1  # one\n# alone\n\ny = "a # b"\n')
    assert [line.kind for line in found] == ['line', 'comment', 'blank', 'line']
    assert found[0].comments == [(1, '# one')]
    assert found[3].tokens[2].value == 'a # b'


def test_a_text_has_two_escapes_and_goes_on_deeper_rows():
    item = only('x = "a \\"quoted\\" \\\\ word"\n')
    assert item.value == n.Text('a "quoted" \\ word')
    item = only('x = 1\n    "first row\n        second row\n\n        after an empty row"\n')
    assert item.text == 'first row second row\nafter an empty row'


def test_an_expression_goes_on_inside_brackets_only():
    item = only('x = max(1,\n    2)\n')
    assert item.value == n.Call('max', (n.Number(1), n.Number(2)))
    refused('x = 1 +\n    2\n', 'continue', 1)


@pytest.mark.parametrize(
    ('text', 'code', 'line'),
    [
        ('x = 1\n\ty = 2\n', 'tab', 2),
        ('tank:\n   water = 1\n', 'indent', 2),
        ('x = "open\n', 'text', 1),
        ('x = "a \\n b"\n', 'text', 1),
        ('x = (1\n', 'bracket', 1),
        ('x = 1)\n', 'bracket', 1),
        ('x = 1 ; 2\n', 'character', 1),
        ('rate: L/h^2 = 1\n', 'unit', 1),
        ('state = OPEN | CLOSED\n', 'retired', 1),
    ],
)
def test_the_lexer_refuses_with_a_code_and_a_line(text, code, line):
    refused(text, code, line)


# ---- units (D12) ----------------------------------------------------------------------------------


def test_a_unit_runs_through_star_and_slash_and_stops_at_a_number():
    # `48 h/2` and `48 h / 2` are one tree: the quantity 48 h divided by the number 2.
    halved = n.Binary('/', q(48, 'h'), n.Number(2))
    assert parse_expression('48 h/2') == parse_expression('48 h / 2') == halved
    assert parse_expression('5 L/h') == q(5, 'L', '/h')
    assert parse_expression('6 person * year') == q(6, 'person', '*year')
    assert parse_expression('5 L/h/h') == q(5, 'L', '/h', '/h')


def test_a_unit_stops_at_a_bracket_and_at_a_value_with_a_dot():
    product = parse_expression('(3 person) * (2 year)')
    assert product == n.Binary('*', q(3, 'person'), q(2, 'year'))
    assert parse_expression('2 h * this.crews') == n.Binary('*', q(2, 'h'), n.Member(n.Name('this'), 'crews'))
    assert parse_expression('x / (2 h)') == n.Binary('/', n.Name('x'), q(2, 'h'))


def test_a_value_whose_name_is_a_unit_needs_brackets():
    # Without brackets the name continues the unit; with them it is a value.
    assert parse_expression('2 h * hour') == q(2, 'h', '*hour')
    assert parse_expression('(2 h) * hour') == n.Binary('*', q(2, 'h'), n.Name('hour'))


def test_a_power_ends_a_unit_run():
    assert parse_expression('2 h ** 2') == n.Binary('**', q(2, 'h'), n.Number(2))
    raised = n.Binary('**', n.Name('x'), n.Number(2))
    assert parse_expression('2 h * x ** 2') == n.Binary('*', q(2, 'h'), raised)


def test_a_type_composes_units_with_brackets():
    item = only('rate: tunings / (tuner * year) = 1\n')
    assert item.type == n.UnitType(n.UnitOp('/', 'tunings', n.UnitOp('*', 'tuner', 'year')))
    assert only('area: m * m = 1\n').type == n.UnitType(n.UnitOp('*', 'm', 'm'))
    assert only('water: L = 1\n').type == n.NamedType('L')


@pytest.mark.parametrize(
    ('text', 'code'),
    [
        ('3 person-years', 'unit'),
        ('48h', 'unit'),
        ('3 tank.water', 'syntax'),
        ('8 size 20 L', 'retired'),
    ],
)
def test_old_units_are_refused(text, code):
    refused(text, code, alone=True)


def test_a_hyphen_in_the_unit_of_a_type_is_refused():
    refused('effort: person-year = 1\n', 'unit', 1)


# ---- declarations -----------------------------------------------------------------------------------


def test_a_declaration_has_its_type_value_range_scale_and_records():
    item = only('due: tunings = this.need in [0,] scale 20000 tunings @counts\n    "Still needed"\n')
    assert item == n.Declaration(
        '',
        'due',
        n.NamedType('tunings'),
        n.Member(n.Name('this'), 'need'),
        n.Range(n.Number(0), None),
        q(20000, 'tunings'),
        cites=(n.Cite('counts'),),
        text='Still needed',
    )


def test_a_range_can_leave_either_side_empty_and_stand_on_its_own_row():
    assert only('x: L = 1 in [, 10 L]\n').range == n.Range(None, q(10, 'L'))
    assert only('input delay: h = 3\n    in [0.5, 12]\n').range == n.Range(n.Number(0.5), n.Number(12))
    refused('x = 1 in [,]\n', 'syntax', 1)


def test_in_after_a_declaration_starts_its_range_and_in_brackets_tests_membership():
    item = only('ok: bool = (x in [0, 10])\n')
    assert item.value == n.Within(n.Name('x'), n.Number(0), n.Number(10)) and item.range is None
    assert parse_expression('x in [0,]') == n.Within(n.Name('x'), n.Number(0), None)


def test_entities_templates_tables_and_instances():
    file = tree(
        """
        tank:
            "A tank."
            title "The tank"
            role environment
            readonly water: L = 8 in [0, 20]
        Place:
            origin: Place
        sites: Place from "places.csv"
        first_pump: Pump
        """
    )
    tank, place, sites, pump = file.items
    assert (tank.name, tank.text, tank.title, tank.role) == ('tank', 'A tank.', 'The tank', 'environment')
    assert tank.members[0].modifier == 'readonly'
    assert place.members[0] == n.Declaration('', 'origin', n.NamedType('Place'))
    assert (sites.template, sites.file) == ('Place', 'places.csv')
    assert pump == n.Declaration('', 'first_pump', n.NamedType('Pump'))


def test_a_flow_has_its_ends_properties_and_legs():
    entity = only(
        """
        site:
            flow delivery: tank.water -> SINK
                capacity = 5 L/h
                request = formula(this.need)
            flow link: west.water <-> east.water
            flow restore:
                flow labor: this.crew.hours -> this.crew.used
                    request = 4 crew_h/h
        """
    )
    delivery, link, restore = entity.members
    assert (delivery.source, delivery.arrow, delivery.sink) == (('tank', 'water'), '->', ('SINK',))
    assert delivery.properties[1].value == n.Formula(n.Member(n.Name('this'), 'need'))
    assert link.arrow == '<->'
    assert restore.legs[0].source == ('this', 'crew', 'hours')


# ---- stages ------------------------------------------------------------------------------------------


def test_if_and_else_branch_inside_a_stage():
    branch, after = stage(
        """
        if this.passes_test:
            this.operational = true
        else:
            this.failed_tests += 1
        this.inspections += 1
        """
    )
    assert isinstance(branch, n.If) and len(branch.then) == 1 and len(branch.orelse) == 1
    assert after == n.Assign(n.Member(n.Name('this'), 'inspections'), '+=', n.Number(1))


def test_a_switch_on_a_draw_has_guarded_cases():
    (switch,) = stage(
        """
        switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
            FIXED when this.parts >= 1:
                this.operational = true
            FAILED:
                this.repair.start()
            else:
                this.waits += 1
        """
    )
    draw = n.Method(n.Call('categorical', (), (('FIXED', n.Number(0.7)), ('FAILED', n.Number(0.3)))), 'draw')
    assert switch.selector == draw
    assert switch.cases[0].guard == n.Compare(('>=',), (n.Member(n.Name('this'), 'parts'), n.Number(1)))
    assert isinstance(switch.cases[1].body[0], n.Start) and switch.orelse is not None


def test_an_actor_choice_is_a_selector():
    (switch,) = stage('switch dispatcher.choose(dispatcher.forecast):\n    SEND:\n        this.sent += 1\n')
    forecast = n.Member(n.Name('dispatcher'), 'forecast')
    assert switch.selector == n.Method(n.Name('dispatcher'), 'choose', (forecast,))


def test_a_write_to_a_live_occurrence_and_a_move():
    write, move = stage('this.repair.occurrences.at(t).crew_size = 3\nmove 3 L from this.supply to batch\n')
    occurrence = n.Method(n.Member(n.Member(n.Name('this'), 'repair'), 'occurrences'), 'at', (n.Name('t'),))
    assert write.target == n.Member(occurrence, 'crew_size')
    assert move == n.Move(q(3, 'L'), n.Member(n.Name('this'), 'supply'), n.Name('batch'))


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ('ok = this.x in [0, 1]\n', 'in'),
        ('x = this.repair.start()\n', 'start'),
        ('elif this.x:\n    this.y = 1\n', 'syntax'),
        ('gap: L = 1\n', 'syntax'),
    ],
)
def test_a_stage_refuses_with_a_code(body, code):
    with pytest.raises(SyntaxProblem) as caught:
        stage(body)
    assert caught.value.code == code


# ---- refusals at the top level and in expressions ----------------------------------------------


@pytest.mark.parametrize(
    ('text', 'code'),
    [
        ('weekly_unserved: people = none\n', 'none'),
        ('output tunings_done = 3\n', 'retired'),
        ('report:\n    tunings_done\n', 'retired'),
        ('scale = 3\n', 'reserved'),
        ('assert x is 2\n', 'retired'),
        ('assert x == 2 within 0.1\n', 'retired'),
        ('x = a < b > c\n', 'chain'),
        ('Rate = 3\n', 'name'),
        ('x = chance(A: 1)\n', 'retired'),
        # Copies of a template, from tests/model/test_copies_and_start.py: write the instances or a table.
        ('couriers: Courier * 3\n', 'retired'),
        ('couriers: Courier * 3 from "couriers.csv"\n', 'retired'),
    ],
)
def test_the_parser_refuses_with_a_code(text, code):
    refused(text, code, 1)


def test_the_scenario_line_and_records():
    file = tree(
        """
        scenario "Pumps"
            summary "Two pumps."
            horizon 5 days
        record timing: source_transfer "Applied from another setting."
            assumption A-TIMING
            claims:
                E-REPAIR-STUDY
                    datum: hours
        """
    )
    scenario, record = file.items
    assert (scenario.role, scenario.title, scenario.horizon) == ('scenario', 'Pumps', q(5, 'days'))
    assert record.relations == (('assumption', 'A-TIMING'),)
    assert record.claims == (n.Claim('E-REPAIR-STUDY', 'hours'),)


def test_a_record_in_place_under_a_value():
    item = only('input staff = 3 tuner\n    @assumption "Three tuners."\n        assumption A-STAFF\n')
    assert item.evidence == (n.Inline('assumption', 'Three tuners.', (('assumption', 'A-STAFF'),)),)
