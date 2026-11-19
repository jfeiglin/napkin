"""Tables (`napkin/model/language/tables.py`, and their rows in the declared model): each row of a table
is one member of its template, and each cell that is not empty is the row's value of its column. So
the oracles are independent of the reader: a table lowers to the program of the same members written
by hand, a reordered file with ids gives the same program, the worked network's tables of the spec
lower to the program that the builder makes of the same rows, and a wrong table is refused at the
file and the line of the table, or at the line of the model that names it."""

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from napkin.model.compile import compile_text, load_scenario
from napkin.model.language import tables
from napkin.model.language.format import format_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    flow,
    fmax,
    formula,
    ifelse,
    input_,
    link,
    q,
    t,
    this,
    value,
)
from napkin.program.canonical import program_bytes
from tests.program.examples import PLACES, ROUTES, UNITS

CORPUS = Path(__file__).parent / 'corpus'

# ---- the form of a table ---------------------------------------------------------------------------


def test_a_table_is_its_header_and_its_rows_each_with_its_line():
    text = 'id,rate: L/h @survey @count,owner\nnorth,2,"the city, east"\n\n"south",5,"a ""big"" farm"\n'
    data = tables.read(text, 'tanks.csv')
    assert data.columns == (
        tables.Column('id', None, ()),
        tables.Column('rate', 'L/h', ('survey', 'count')),
        tables.Column('owner', None, ()),
    )
    assert [(row.cells, row.line) for row in data.rows] == [
        (('north', '2', 'the city, east'), 2),
        (('south', '5', 'a "big" farm'), 4),
    ]


def test_a_row_with_a_line_break_in_a_cell_starts_on_its_first_line():
    data = tables.read('id,note\na,"one\ntwo"\nb,three\n', 'notes.csv')
    assert [(row.cells[0], row.line) for row in data.rows] == [('a', 2), ('b', 4)]


@pytest.mark.parametrize(
    ('cell', 'column'),
    [
        ('rate', tables.Column('rate', None, ())),
        ('rate: L/h', tables.Column('rate', 'L/h', ())),
        ('effort: person * year @census', tables.Column('effort', 'person*year', ('census',))),
        ('held @a @b', tables.Column('held', None, ('a', 'b'))),
        ('held episodes', None),
        ('held: 2', None),
        ('held: L/(h)', None),
        (': L', None),
    ],
)
def test_a_header_cell_names_a_column_its_unit_and_its_records(cell, column):
    assert tables.header(cell) == column


@pytest.mark.parametrize(
    ('text', 'words', 'line'),
    [
        ('id,held\nnorth,1,2\n', 'row 1 has 3 cells, and the header has 2', 2),
        ('id,held,held\nnorth,1,2\n', 'two columns give held', 1),
        ('id,held\n', 'the table has no row', 1),
        ('', 'the table has no header', 1),
        ('id,held episodes\nnorth,1\n', 'a header is `name`, or `name: unit`', 1),
        ('id,held\n"north,1\n', 'the table is not read', None),
    ],
)
def test_a_table_of_the_wrong_form_is_refused_at_its_line(text, words, line):
    with pytest.raises(LanguageError) as caught:
        tables.read(text, 'tanks.csv')
    (problem,) = caught.value.problems
    assert (problem.code, problem.file) == ('table', 'tanks.csv') and words in problem.message
    if line is not None:
        assert problem.line == line


# ---- rows and members ------------------------------------------------------------------------------

MODEL = """
    record survey: assumption "A survey of the tanks, made up for the test."

    Pool:
        input factor = 1 in [0, 2]

    east: Pool
    west: Pool
        factor = 0.5

    Tank:
        pool: Pool
        input rate: L/h = 1 in [0, 100]
        input metered: bool = false
        input owner = "nobody"
        held: L = 10 in [0, 1000]
        lost: L = 0
        flow drain: this.held -> this.lost
            request = formula(this.rate * this.pool.factor)

    tanks: Tank from "tanks.csv"
    """
TABLE = """id,rate: L/h @survey,held: L @survey,metered,owner,pool
north,2,30,true,the city,east
south,5,20,false,,west
old,,7.5,true,"a farm, old",east
last,0.5,,,,west
"""
# The same tanks written by hand, in the order of their ids, each cell the line `column = cell`.
BY_HAND = """
    last: Tank
        rate = 0.5 L/h @survey
        pool = west

    north: Tank
        rate = 2 L/h @survey
        held = 30 L @survey
        metered = true
        owner = "the city"
        pool = east

    old: Tank
        held = 7.5 L @survey
        metered = true
        owner = "a farm, old"
        pool = east

    south: Tank
        rate = 5 L/h @survey
        held = 20 L @survey
        metered = false
        pool = west
    """


def compiled(text=MODEL, table=TABLE, **files):
    return compile_text(textwrap.dedent(text), UNITS, tables={'tanks.csv': table, **files})


def refused(text=MODEL, table=TABLE, **files):
    with pytest.raises(LanguageError) as caught:
        compiled(text, table, **files)
    return caught.value.problems


def renamed(program, table):
    """The program with the ids of the rows of a table as the names of members written by hand."""
    templates = tuple(
        replace(
            template,
            members=tuple(replace(m, id=m.id.removeprefix(f'{table}.')) for m in template.members),
        )
        for template in program.templates
    )
    return replace(program, templates=templates)


def test_a_table_lowers_to_the_program_of_its_rows_written_by_hand():
    rows = compiled().program
    hand = compiled(MODEL.replace('    tanks: Tank from "tanks.csv"\n', BY_HAND)).program
    assert program_bytes(renamed(rows, 'tanks')) == program_bytes(hand)


def test_each_row_is_a_member_with_its_cells_its_line_and_its_file():
    model = compiled().declared
    (table,) = model.tables
    assert (table.template, table.origin, table.members) == (
        'Tank',
        'tanks.csv',
        ('tanks.north', 'tanks.south', 'tanks.old', 'tanks.last'),
    )
    south = model.part('tanks.south')
    assert (south.line, south.file, south.table) == (3, 'tanks.csv', 'tanks')
    assert [given.name for given in south.values] == ['rate', 'held', 'metered']
    assert [(given.name, given.init) for given in south.links] == [('pool', 'west')]
    # A column cites its records in its header, for each of its cells.
    assert [cite.name for cite in south.values[0].evidence] == ['survey']


def test_a_cell_writes_its_unit_when_its_header_writes_none():
    table = TABLE.replace('rate: L/h @survey', 'rate @survey')
    for written in ('2', '5', '0.5'):
        table = table.replace(f',{written},', f',{written} L/h,', 1)
    assert program_bytes(compiled(table=table).program) == program_bytes(compiled().program)


def test_a_reordered_file_names_the_same_members():
    head, *rows = TABLE.splitlines()
    reordered = '\n'.join([head, *rows[::-1]]) + '\n'
    assert program_bytes(compiled(table=reordered).program) == program_bytes(compiled().program)


# Each wrong table or model, with the code, the file ('' for the model), the line and the words of the
# problem about it.
WRONG = [
    (TABLE.replace('held: L', 'hold: L'), MODEL, 'unknown_name', 'tanks.csv', 1, 'did you mean held?'),
    (TABLE.replace('\nsouth,5,', '\nsouth,2 * 3,'), MODEL, 'table', 'tanks.csv', 3, 'is not a number'),
    (TABLE.replace('rate: L/h', 'rate: L'), MODEL, 'unit', 'tanks.csv', 1, 'the column rate is in L'),
    (TABLE.replace('held: L', 'held: furlongs'), MODEL, 'unit', 'tanks.csv', 1, 'furlongs is no unit'),
    (TABLE.replace(',owner,', ',owner: L,'), MODEL, 'unit', 'tanks.csv', 1, 'owner takes no number'),
    (TABLE.replace('north,2,', 'north,2 L/h,'), MODEL, 'unit', 'tanks.csv', 2, 'gives its unit'),
    (
        TABLE.replace('the city,east', 'the city,eastt'),
        MODEL,
        'unknown_name',
        'tanks.csv',
        2,
        'did you mean east or west?',
    ),
    (
        TABLE.replace('the city,east', 'the city,tanks.south'),
        MODEL,
        'type',
        'tanks.csv',
        2,
        'a member of Tank',
    ),
    (TABLE.replace('the city,east', 'the city,3'), MODEL, 'link', 'tanks.csv', 2, 'names no member'),
    (TABLE.replace('\nold,', '\nnorth,'), MODEL, 'duplicate_name', 'tanks.csv', 4, 'the first is on line 2'),
    (TABLE.replace('\nold,', '\n,'), MODEL, 'table', 'tanks.csv', 4, 'has no id'),
    (TABLE.replace('\nold,', '\nold tank,'), MODEL, 'table', 'tanks.csv', 4, 'is no name'),
    (TABLE.replace('30,true', '30,yes'), MODEL, 'table', 'tanks.csv', 2, 'true or false'),
    (TABLE.replace('\nsouth,5,', '\nsouth,-5,'), MODEL, 'range', 'tanks.csv', 3, 'below the range of rate'),
    (
        TABLE.replace('north,2,30,', 'north,2,1001,'),
        MODEL,
        'range',
        'tanks.csv',
        2,
        'above the range of held',
    ),
    (TABLE.replace(',pool', ',drain'), MODEL, 'table', 'tanks.csv', 1, 'a column gives a value or a link'),
    (TABLE, MODEL.replace('Tank from', 'Tankk from'), 'unknown_name', '', 21, 'did you mean Tank?'),
    (TABLE, MODEL.replace('"tanks.csv"', '"tank.csv"'), 'table', '', 21, 'is not a table given'),
    (
        TABLE,
        MODEL.replace('        pool: Pool\n', '        pool: Pool\n        input depth: L\n'),
        'no_value',
        'tanks.csv',
        2,
        'gives no depth',
    ),
    (
        '\n'.join(row.rpartition(',')[0] for row in TABLE.splitlines()) + '\n',
        MODEL,
        'link_unset',
        'tanks.csv',
        2,
        'sets no pool',
    ),
    (TABLE, MODEL + 'total = sum(tanks.held)\n', 'unknown_name', '', 22, 'Tank.instances.held'),
    (TABLE, MODEL + 'first = formula(tanks.nort.held)\n', 'unknown_name', '', 22, 'did you mean north?'),
]


@pytest.mark.parametrize(('table', 'text', 'code', 'file', 'line', 'words'), WRONG)
def test_a_wrong_table_is_refused_at_its_file_and_its_line(table, text, code, file, line, words):
    problems = refused(text, table)
    found = [problem for problem in problems if problem.code == code]
    assert found, problems
    assert (found[0].file, found[0].line) == (file, line) and words in found[0].message, found[0]


def test_the_rows_of_a_table_without_ids_have_no_names():
    problems = refused(table='rate,pool\n2,east\n', text=MODEL + 'first = formula(tanks.north.held)\n')
    assert [problem.code for problem in problems] == ['unknown_name']
    assert 'have no ids' in problems[0].message


def test_a_text_with_no_folder_has_no_table():
    with pytest.raises(LanguageError) as caught:
        compile_text(textwrap.dedent(MODEL), UNITS)
    assert caught.value.codes == ['table'] and 'has no folder' in str(caught.value)


def test_the_formatter_keeps_the_line_of_a_table():
    text = 'Tank:\n    held = 1\n\ntanks: Tank from "tanks.csv" @survey\n    "The tanks of the survey."\n'
    assert format_text(text) == text


# ---- a package -----------------------------------------------------------------------------------

PACKAGE = """scenario "Crews"
    horizon 1 day

Crew:
    input size: people = 1 in [0,]

crews: Crew from "{file}"

total = sum(Crew.instances.size)
"""


def test_a_package_reads_its_tables_from_its_folder(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'crews.csv').write_text('id,size: people\nnight,2\nday,4\n')
    (tmp_path / 'model.scn').write_text(PACKAGE.format(file='data/crews.csv'))
    found = load_scenario(tmp_path / 'model.scn')
    (crew,) = found.program.templates
    assert [member.id for member in crew.members] == ['crews.day', 'crews.night']
    assert found.declared.tables[0].origin == (tmp_path / 'data' / 'crews.csv').as_posix()


@pytest.mark.parametrize(
    ('file', 'words'),
    [
        ('../crews.csv', 'is not a path inside the package'),
        ('crews.txt', 'is not a .csv file'),
        ('missing.csv', 'is not a file of the package'),
    ],
)
def test_a_table_is_a_csv_file_of_its_package(tmp_path, file, words):
    (tmp_path / 'crews.txt').write_text('id,size\nday,4\n')
    (tmp_path / 'model.scn').write_text(PACKAGE.format(file=file))
    with pytest.raises(LanguageError) as caught:
        load_scenario(tmp_path / 'model.scn')
    (problem,) = caught.value.problems
    assert (problem.code, problem.line) == ('table', 7) and words in problem.message
    assert problem.file == (tmp_path / 'model.scn').as_posix()


def test_a_problem_of_a_table_of_a_package_is_at_its_file(tmp_path):
    (tmp_path / 'crews.csv').write_text('id,size: people\nday,4\nnight,-2\n')
    (tmp_path / 'model.scn').write_text(PACKAGE.format(file='crews.csv'))
    with pytest.raises(LanguageError) as caught:
        load_scenario(tmp_path / 'model.scn')
    (problem,) = caught.value.problems
    assert (problem.code, problem.file, problem.line) == ('range', (tmp_path / 'crews.csv').as_posix(), 3)


# ---- the worked network ----------------------------------------------------------------------------

# The templates and tables of the spec's worked network ("Using collections in a solver") without
# its route, its event and its solver: the whole network is in `test_solvers.py`.
NETWORK = """
    Reading:
        input hour: h = 0
        input factor = 1

    Place:
        input base_need: W = 0
        input supply_limit: W = 0
        input critical: bool = false
        level = 0 in [-30, 30]
        power: Wh = 0 in [0, 0]
        need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)
        flow supply: SOURCE -> this.power
            capacity = this.supply_limit
        flow use: this.power -> SINK
            request = formula(this.need)
            capacity = formula(this.need)
        unmet = formula(max(0 W, this.use.request - this.use.actual_rate))

    Route:
        origin: Place
        destination: Place
        input strength: W = 1
        input closes_at_two: bool = false
        up: bool = true
        pull = formula(this.strength if this.up else 0 W)

    sites: Place from "places.csv"
    links: Route from "routes.csv"
    readings: Reading from "readings.csv"
    """
# The readings of the spec's file, as a model text writes 0.5: a float.
READINGS = ({'hour': 0, 'factor': 1}, {'hour': 1, 'factor': 0.5}, {'hour': 2, 'factor': 1})


def network_tables():
    """The same templates and rows, by the builder."""
    b = Builder(UNITS)
    readings = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    places = b.template(
        'Place',
        input_('base_need', 'W', 0),
        input_('supply_limit', 'W', 0),
        input_('critical', BOOL, False),
        value('level', '', 0, lower=-30, upper=30),
        value('power', 'Wh', 0, lower=0, upper=0),
        value('need', 'W', formula(this.base_need * readings.instances.by('hour').at(t).factor)),
        flow('supply', SOURCE, this.power, capacity=this.supply_limit),
        flow('use', this.power, SINK, request=formula(this.need), capacity=formula(this.need)),
        value('unmet', 'W', formula(fmax(q(0, 'W'), this.use.request - this.use.actual_rate))),
    )
    routes = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('strength', 'W', 1),
        input_('closes_at_two', BOOL, False),
        value('up', BOOL, True),
        value('pull', 'W', formula(ifelse(this.up, this.strength, q(0, 'W')))),
    )
    b.table('sites', places, PLACES)
    b.table('links', routes, ROUTES)
    b.table('readings', readings, READINGS)
    return b.finish()


def network(**changes):
    files = {name: (CORPUS / name).read_text() for name in ('places.csv', 'routes.csv', 'readings.csv')}
    return compile_text(textwrap.dedent(NETWORK), UNITS, tables={**files, **changes})


def test_the_tables_of_the_worked_network_lower_to_its_rows():
    assert program_bytes(network().program) == program_bytes(network_tables())


def test_a_reordered_network_keeps_its_named_rows_and_their_links():
    def reordered(name):
        head, *rows = (CORPUS / name).read_text().splitlines()
        return '\n'.join([head, *rows[::-1]]) + '\n'

    found = network(**{name: reordered(name) for name in ('places.csv', 'routes.csv')}).program
    assert program_bytes(found) == program_bytes(network().program)
    place, route = found.template('Place'), found.template('Route')
    rows = {member.id: row for row, member in enumerate(place.members)}
    clinic = next(member for member in route.members if member.id == 'links.junction_clinic')
    assert dict(clinic.links) == {'origin': rows['sites.junction'], 'destination': rows['sites.clinic']}


# ---- the setup's reports ---------------------------------------------------------------------------

# Spec, "Collections, keys and projections": for rows, setup reports equal keys within a keyed view
# that `.at(...)` reads, at the row that wins (of equal keys the later-created; rows with ids are
# created in the order of their ids), and a lookup whose key has a known lower bound below the first
# key. The reports refuse nothing.
READ_AT = """
    Reading:
        input hour: h = 0
        input factor = 1
        input valid: bool = true

    readings: Reading from "readings.csv"

    factor_now = formula(Reading.instances.by(hour).at(t).factor)
    """


def reported(text, **files):
    """The setup's reports of a text, without the warnings of the evidence rule (its values cite no
    record: `tests/language/test_evidence_rule.py`)."""
    found = compile_text(textwrap.dedent(text), UNITS, tables=files)
    shown = tuple(item for item in found.reports if item.code != 'no_record')
    return [(item.code, item.file, item.line) for item in shown], shown


def test_equal_keys_under_at_are_reported_at_the_row_that_wins():
    # The ids order the rows late, morning, noon: of the two rows at 10 h, morning is created later.
    table = 'id,hour: h,factor,valid\nmorning,10,2,true\nnoon,0,3,true\nlate,10,4,false\n'
    places, (report,) = reported(READ_AT, **{'readings.csv': table})
    assert places == [('equal_keys', 'readings.csv', 2)]
    assert 'readings.late, readings.morning have the key 10 h' in report.message
    assert 'created later, readings.morning' in report.message


def test_a_where_limits_the_check_of_equal_keys_to_the_rows_that_pass_it():
    table = 'id,hour: h,factor,valid\nmorning,10,2,true\nnoon,0,3,true\nlate,10,4,false\n'
    text = READ_AT.replace('Reading.instances.by', 'Reading.instances.where(valid).by')
    assert reported(text, **{'readings.csv': table})[0] == []


def test_equal_ranks_in_a_view_that_only_priority_reads_are_no_report():
    text = """
        reservoir:
            water: L = 20 in [0, 20]
                outflow.allocation = priority(Customer.instances.by(rank).delivery)
        Customer:
            input rank = 1
            flow delivery: reservoir.water -> SINK
                request = 2 L/h
        customers: Customer from "customers.csv"
        """
    assert reported(text, **{'customers.csv': 'id,rank\na,1\nb,1\n'})[0] == []


def test_a_lookup_below_its_first_key_at_a_known_lower_bound_is_reported_at_its_line():
    # t starts at 0 h, and the first reading is at 2 h: a read at 1 h fails when it is evaluated.
    places, (report,) = reported(READ_AT, **{'readings.csv': 'hour: h,factor\n2,5\n'})
    assert places == [('below_first_key', '', 9)]
    assert 'at 0 h at the least, below the first key 2 h' in report.message
    assert reported(READ_AT, **{'readings.csv': 'hour: h,factor\n0,1\n2,5\n'})[0] == []


@pytest.mark.parametrize(
    ('first', 'lowest', 'words'),
    [(1, 500, '0.5 kWh at the least, below the first key 1 kWh'), (1, 1000, None)],
)
def test_a_key_with_a_lower_bound_is_compared_in_the_unit_of_the_view(first, lowest, words):
    text = f"""
        Tier:
            input threshold: kWh = 0
            input price = 1

        tiers: Tier from "tiers.csv"

        meter:
            input volume: Wh = {lowest} in [{lowest},]
            price = formula(Tier.instances.by(threshold).at(this.volume).price)
        """
    places, found = reported(text, **{'tiers.csv': f'threshold: kWh,price\n{first},2\n3,1\n'})
    assert places == ([] if words is None else [('below_first_key', '', 10)])
    assert words is None or words in found[0].message
