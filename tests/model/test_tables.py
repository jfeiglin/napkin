"""The instances of a template from a table (docs/language.md, §2.3): `name: Template from "file.csv"`.

Each row of the table is one instance, and each cell that is not empty is the line `member = cell` of
that instance. So the oracles are independent of the reader of the table:

- the model of a table is the model of the same instances written out by hand, line by line: the same
  structure but for the names and the places, and the same run, bit for bit;
- each tank drains at a constant rate until it is empty, so the water that it loses in a run is
  `min(held, rate * factor * horizon)`, or nothing when its valve is shut, and it is empty at the time
  `held / (rate * factor)`;
- a wrong table is an error at the file and the line of the table, or at the line that names it.
"""

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.language.evidence import identity
from napkin.model.language.format import format_text
from napkin.model.model import build_model
from tests.build import library
from tests.owned import write_family

HORIZON = 10

HEAD = f"""    summary "Tanks that drain. A synthetic fixture for tests only."
    horizon {HORIZON} h
    scope "Fixture"
    library "../library"
"""

TEMPLATES = """Pool:  @fixture
    "A pool that slows the tanks that it serves."
    role environment
    input factor: fraction = 1 in 0 to 2  @fixture
        "The part of its rate that a tank of the pool keeps"

Tank:  @fixture
    "A tank that drains."
    role environment
    let pool: Pool
    input rate: episodes/h = 1 episodes/h in 0 episodes/h to 100 episodes/h  @fixture
        "How fast the tank drains"
    input metered: bool = false  @fixture
        "Whether the tank has a meter"
    input owner = "nobody"
    var valve: "open" | "shut" = "open"
        "The valve of the tank"
    var held: episodes = 10 episodes in 0 episodes to 1000 episodes  @fixture
        "Water in the tank"
    var lost: episodes = 0 episodes size 1000 episodes  @fixture
        "Water that the tank lost"
    flow drain: held -> lost at rate * pool.factor while valve is "open"  @fixture
    event empty once when held <= 0 episodes:  @fixture
        "The tank of {owner} is empty."

east: Pool  @fixture
    "The east pool."

west: Pool  @fixture
    "The west pool."
    factor = 0.5  @fixture
"""

REST = """output lost: episodes = sum(Tank.lost)  @fixture
    "Water that the tanks lost"
    level

options "Response":
    "Default":
        "The defaults."

runs:
    a = "Default"

record fixture: identity "Analytic contract fixture."
record survey: assumption "A survey of the tanks, made up for the fixture."
"""

# The tanks: (title, rate in episodes/h or None for the template's, water held or None, valve, whether
# metered or None, owner or None, pool).
TANKS = (
    ('North tank', 2, 30, 'open', True, 'the city', 'east'),
    ('South tank', 5, 20, 'open', False, None, 'west'),
    ('Old, small tank', None, 7.5, 'shut', True, 'a farm', 'east'),
    ('Last tank', 0.5, None, 'open', None, None, 'west'),
)
DEFAULT_RATE, DEFAULT_HELD = 1, 10
FACTORS = {'east': 1, 'west': 0.5}
HEADER = 'title,rate: episodes/h @survey,held: episodes @survey,valve,metered @survey,owner,pool'


def cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    text = str(value)
    return f'"{text}"' if ',' in text else text


def table(tanks=TANKS, header=HEADER):
    return '\n'.join([header, *(','.join(cell(value) for value in tank) for tank in tanks)]) + '\n'


def with_table(line='tanks: Tank from "tanks.csv"  @fixture\n    "The tanks of the survey."\n'):
    return f'scenario "Tanks"\n{HEAD}\n{TEMPLATES}\n{line}\n{REST}'


def by_hand(tanks=TANKS):
    """The same tanks, each an instance with its own lines."""
    things = []
    for k, (title, rate, held, valve, metered, owner, pool) in enumerate(tanks, 1):
        lines = [f'tanks_{k}: Tank  @fixture', '    "The tanks of the survey."', f'    title "{title}"']
        if rate is not None:
            lines.append(f'    rate = {rate} episodes/h  @survey')
        if held is not None:
            lines.append(f'    held = {held} episodes  @survey')
        lines.append(f'    valve = "{valve}"')
        if metered is not None:
            lines.append(f'    metered = {cell(metered)}  @survey')
        if owner is not None:
            lines.append(f'    owner = "{owner}"')
        lines.append(f'    pool = {pool}')
        things.append('\n'.join(lines) + '\n')
    return f'scenario "Tanks"\n{HEAD}\n{TEMPLATES}\n{chr(10).join(things)}\n{REST}'


def family(tmp_path, **extra):
    """The package SC97, whose tanks are the rows of its table, and SC98, the same tanks by hand."""
    files = {'SC97/model.scn': with_table(), 'SC97/tanks.csv': table(), 'SC98/model.scn': by_hand(), **extra}
    return write_family(tmp_path, files)


def renamed(value):
    """The plain data of a model of the table with the names of the model by hand (instance k of the
    set `tanks` is `tanks.k`, and the model by hand calls it `tanks_k`), and without what differs
    between the two by design: the places, files, lines and ranks of the lines, and the set of an
    instance with its number in the set."""
    if isinstance(value, dict):
        drop = ('path', 'place', 'line', 'where', 'file', 'rank', 'copy', 'entry', 'origin')
        return {renamed(k): renamed(v) for k, v in value.items() if k not in drop}
    if isinstance(value, tuple):
        return tuple(renamed(v) for v in value)
    if isinstance(value, list):
        return [renamed(v) for v in value]
    if isinstance(value, str):
        for k in range(len(TANKS), 0, -1):
            value = value.replace(f'tanks.{k}', f'tanks_{k}')
    return value


def plain_structures(model):
    return {starts: structure.plain() for starts, structure in model.structures.items()}


def trajectory(model):
    run = simulate(model.resolve('a'), thaw(model.library), None)
    end = run.env_at(run.horizon)
    return (
        [(e['t'].hex() if isinstance(e['t'], float) else e['t'], e['event']) for e in run.trace],
        {k: v.hex() if isinstance(v, float) else v for k, v in end.items()},
    )


def problems(path):
    with pytest.raises(ModelError) as raised:
        build_model(path)
    return raised.value.diagnostics


def test_the_model_of_a_table_is_the_model_of_its_rows_written_by_hand(tmp_path):
    paths = family(tmp_path)
    rows, hand = build_model(paths['SC97/model.scn']), build_model(paths['SC98/model.scn'])
    assert renamed(plain_structures(rows)) == renamed(plain_structures(hand))
    assert renamed(thaw(rows.inputs)) == renamed(thaw(hand.inputs))
    assert renamed(trajectory(rows)) == renamed(trajectory(hand))


def test_each_tank_loses_what_its_row_says(tmp_path):
    import napkin

    model = build_model(family(tmp_path)['SC97/model.scn'])
    run = simulate(model.resolve('a'), thaw(model.library), None)
    end = run.env_at(run.horizon)
    # The trace names an event with its outcome: `tanks_2.empty.done`.
    emptied = {'.'.join(event['event'].split('.')[:2]): event['t'] for event in run.trace}
    total = 0
    for k, (_, given_rate, given_held, valve, _, _, pool) in enumerate(TANKS, 1):
        rate = (DEFAULT_RATE if given_rate is None else given_rate) * FACTORS[pool]
        held = DEFAULT_HELD if given_held is None else given_held
        lost = min(held, rate * HORIZON) if valve == 'open' else 0
        assert end[f'tanks_{k}.lost'] == pytest.approx(lost, rel=1e-9, abs=1e-9)
        assert end[f'tanks_{k}.held'] == pytest.approx(held - lost, rel=1e-9, abs=1e-9)
        if valve == 'open' and held / rate < HORIZON:
            assert emptied[f'tanks_{k}.empty'] == pytest.approx(held / rate, rel=1e-9)
        else:
            assert f'tanks_{k}.empty' not in emptied
        total += lost
    # The table makes a tank that is empty before the end, so the times above are tested.
    assert emptied
    report = napkin.sample_result(napkin.evaluate_study(model))
    final = report['runs']['a']['reporting_points']['final']['values']
    assert final['lost'] == pytest.approx(total, rel=1e-9)


def test_an_instance_of_a_table_has_the_number_and_the_title_of_its_row(tmp_path):
    import napkin

    model = build_model(family(tmp_path)['SC97/model.scn'])
    found = napkin.instances(model, 'Tank')
    assert [(item['name'], item['copy'], item['title']) for item in found] == [
        (f'tanks.{k}', k, tank[0]) for k, tank in enumerate(TANKS, 1)
    ]


def test_the_name_of_the_set_is_the_list_of_its_instances(tmp_path):
    """`sum(tanks.lost)` adds the rows, as `sum(Tank.lost)` does when the table makes every tank."""
    by_set = with_table().replace('sum(Tank.lost)', 'sum(tanks.lost)')
    paths = family(tmp_path, **{'SC96/model.scn': by_set, 'SC96/tanks.csv': table()})
    assert trajectory(build_model(paths['SC96/model.scn'])) == trajectory(
        build_model(paths['SC97/model.scn'])
    )


def test_a_line_under_the_thing_holds_for_each_row(tmp_path):
    """A line under the thing gives each instance its value; a column cannot give that member too."""
    line = (
        'tanks: Tank from "tanks.csv"  @fixture\n    "The tanks of the survey."\n    owner = "the district"\n'
    )
    header = HEADER.replace(',owner', '')
    tanks = [tank[:5] + tank[6:] for tank in TANKS]
    paths = family(tmp_path, **{'SC97/model.scn': with_table(line), 'SC97/tanks.csv': table(tanks, header)})
    model = build_model(paths['SC97/model.scn'])
    texts = repr(plain_structures(model))
    assert texts.count('The tank of the district is empty.') >= len(TANKS) and 'of nobody' not in texts


def wrong(**changes):
    """The files of SC97 with one thing wrong."""
    return {'SC97/model.scn': with_table(), 'SC97/tanks.csv': table(), **changes}


LINE = 'tanks: Tank from "{}"  @fixture\n    "The tanks of the survey."\n'
GIVEN = LINE.format('tanks.csv') + '    rate = 3 episodes/h  @fixture\n'
LISTED = TEMPLATES.replace('let pool: Pool', 'let pool: Pool\n    let others: [Pool]')
LISTED_LINE = LINE.format('tanks.csv') + '    others = [east]\n'


@pytest.mark.parametrize(
    ('files', 'words', 'file', 'line'),
    [
        # A column that names nothing of the template; the closest name comes with the error.
        (
            wrong(**{'SC97/tanks.csv': table(header=HEADER.replace('held:', 'hold:'))}),
            'hold is not a value or a link of the template Tank',
            'tanks.csv',
            1,
        ),
        (
            wrong(**{'SC97/tanks.csv': table(header=HEADER.replace('held:', 'hold:'))}),
            'did you mean held?',
            'tanks.csv',
            1,
        ),
        # A formula in a cell.
        (
            wrong(**{'SC97/tanks.csv': table().replace('\nSouth tank,5,', '\nSouth tank,2 * 3,')}),
            'is not a number, true or false',
            'tanks.csv',
            3,
        ),
        # A column of values with no record: one error for the column, at the header.
        (
            wrong(
                **{
                    'SC97/tanks.csv': table(
                        header=HEADER.replace('rate: episodes/h @survey', 'rate: episodes/h')
                    )
                }
            ),
            'the column rate gives new values, which need records of their own',
            'tanks.csv',
            1,
        ),
        # A member that a line under the thing gives too.
        (
            wrong(**{'SC97/model.scn': with_table(GIVEN)}),
            'a line under tanks and a column of its table both give rate',
            'tanks.csv',
            1,
        ),
        # A text takes no unit.
        (
            wrong(**{'SC97/tanks.csv': table(header=HEADER.replace(',owner,', ',owner: episodes,'))}),
            'owner takes no number',
            'tanks.csv',
            1,
        ),
        # A link names one entity of the model.
        (
            wrong(**{'SC97/tanks.csv': table().replace('the city,east', 'the city,north')}),
            'north is not an entity',
            'tanks.csv',
            2,
        ),
        (
            wrong(**{'SC97/tanks.csv': table().replace('the city,east', 'the city,[east]')}),
            'names no entity',
            'tanks.csv',
            2,
        ),
        # The file of the table.
        (
            wrong(**{'SC97/model.scn': with_table(LINE.format('tank.csv'))}),
            "'tank.csv' is not a file of the package",
            'model.scn',
            None,
        ),
        (
            wrong(**{'SC97/model.scn': with_table(LINE.format('../SC98/model.scn'))}),
            'is not a path inside the package',
            'model.scn',
            None,
        ),
        (
            wrong(**{'SC97/model.scn': with_table(LINE.format('model.scn'))}),
            'is not a .csv file',
            'model.scn',
            None,
        ),
        # The form of the table.
        (
            wrong(**{'SC97/tanks.csv': table().replace('South tank,5,20,', 'South tank,5,')}),
            'row 2 has 6 cells, and the header has 7',
            'tanks.csv',
            3,
        ),
        (
            wrong(**{'SC97/tanks.csv': table(header=HEADER.replace(',owner,', ',valve,'))}),
            'two columns give valve',
            'tanks.csv',
            1,
        ),
        (wrong(**{'SC97/tanks.csv': HEADER + '\n'}), 'the table has no row', 'tanks.csv', 1),
        (
            wrong(**{'SC97/tanks.csv': table(header=HEADER.replace('held: episodes', 'held episodes'))}),
            'a header is `name`, or `name: unit`',
            'tanks.csv',
            1,
        ),
        (
            wrong(**{'SC97/tanks.csv': table().replace('North tank', '"North tank')}),
            'the table is not read',
            'tanks.csv',
            None,
        ),
    ],
)
def test_a_wrong_table_is_an_error_at_its_file_and_line(tmp_path, files, words, file, line):
    paths = write_family(tmp_path, {'SC98/model.scn': by_hand(), **files})
    found = [item for item in problems(paths['SC97/model.scn']) if words in item['message']]
    assert len(found) == 1, problems(paths['SC97/model.scn'])
    assert found[0]['file'].endswith(file)
    if line is not None:
        assert found[0]['line'] == line


def test_a_list_link_is_no_column(tmp_path):
    files = wrong(
        **{
            'SC97/model.scn': with_table(LISTED_LINE).replace(TEMPLATES, LISTED),
            'SC97/tanks.csv': table(header=HEADER + ',others', tanks=[(*tank, 'east') for tank in TANKS]),
        }
    )
    paths = write_family(tmp_path, files)
    found = [item['message'] for item in problems(paths['SC97/model.scn'])]
    assert any('others is a list link' in message for message in found), found


@pytest.mark.parametrize(
    ('old', 'new'),
    [
        # A rate in a unit of an amount; a start of a var in a unit of time; a unit that is none.
        ('rate: episodes/h', 'rate: episodes'),
        ('held: episodes', 'held: h'),
        ('held: episodes', 'held: furlongs'),
    ],
)
def test_a_column_in_a_wrong_unit_is_one_error_at_its_header(tmp_path, old, new):
    """The unit of a column is wrong for every row: the error is one, at the header of the column in
    the file of the table, however many rows the table has."""
    assert old in HEADER
    files = wrong(**{'SC97/tanks.csv': table(header=HEADER.replace(old, new))})
    found = problems(write_family(tmp_path, files)['SC97/model.scn'])
    assert len(found) == 1, found
    assert found[0]['file'].endswith('tanks.csv') and found[0]['line'] == 1
    assert found[0]['path'].endswith(new.split(':')[0])


def test_a_cell_writes_its_unit_when_its_header_writes_none(tmp_path):
    """A header with no unit leaves the unit to each cell, as the line `held = 30 episodes` writes it:
    the model is the model of the table whose header writes the unit."""
    in_cells = table().replace('held: episodes @survey', 'held @survey')
    for _, _, held, *_ in TANKS:
        if held is not None:
            in_cells = in_cells.replace(f',{held},', f',{held} episodes,', 1)
    assert in_cells.count(' episodes,') == sum(tank[2] is not None for tank in TANKS)
    paths = family(tmp_path, **{'SC96/model.scn': with_table(), 'SC96/tanks.csv': in_cells})
    assert trajectory(build_model(paths['SC96/model.scn'])) == trajectory(
        build_model(paths['SC97/model.scn'])
    )


def test_a_set_takes_its_count_from_its_table_or_from_its_line_not_both():
    with pytest.raises(ModelError) as raised:
        front.read(with_table('tanks: Tank * 2 from "tanks.csv"  @fixture\n    "The tanks."\n'), 'test.scn')
    assert 'from "file.csv"' in raised.value.diagnostics[0]['message']


def test_a_model_that_is_a_text_has_no_table():
    """A text has no folder, so the compiler cannot read the table that it names."""
    file = front.read(with_table(), 'test.scn')
    with pytest.raises(ModelError) as raised:
        front.compile_file(file, 'test.scn', library())
    assert any('a table is a file of a package' in item['message'] for item in raised.value.diagnostics)


def hash_of(tmp_path, name, **files):
    return build_model(write_family(tmp_path / name, wrong(**files))['SC97/model.scn']).model_hash


def test_the_model_hash_covers_what_the_table_holds_and_not_its_name(tmp_path):
    base = hash_of(tmp_path, 'base')
    moved = hash_of(
        tmp_path,
        'moved',
        **{'SC97/model.scn': with_table(LINE.format('data/survey.csv')), 'SC97/data/survey.csv': table()},
    )
    assert moved == base
    spaced = hash_of(
        tmp_path, 'spaced', **{'SC97/tanks.csv': table().replace('North tank,2,', 'North tank ,  2 ,')}
    )
    assert spaced == base
    value = hash_of(
        tmp_path, 'value', **{'SC97/tanks.csv': table().replace('North tank,2,', 'North tank,3,')}
    )
    order = hash_of(tmp_path, 'order', **{'SC97/tanks.csv': table(tanks=TANKS[::-1])})
    record = hash_of(
        tmp_path,
        'record',
        **{'SC97/tanks.csv': table(header=HEADER.replace('@survey,held', '@fixture,held'))},
    )
    assert len({base, value, order, record}) == 4


def test_a_thing_with_no_table_hashes_as_before_the_language_had_tables():
    """What the model hash reads of a thing with no table has no part for a table, so no model that
    was written before changes its hash."""
    file = front.read(by_hand(), 'test.scn')
    things = identity(file)[1]['things']
    assert things and all('table' not in fields for _, fields in things)
    with_one = identity(front.read(with_table(), 'test.scn'))[1]['things']
    assert [fields['table'] for _, fields in with_one if 'table' in fields] != []


def test_the_formatter_keeps_the_line_of_a_table():
    text = with_table()
    assert 'tanks: Tank from "tanks.csv"  @fixture' in format_text(text)
    assert format_text(format_text(text)) == format_text(text)
