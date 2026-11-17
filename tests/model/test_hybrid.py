"""The hybrid core (`napkin/model/hybrid.py`): the rows of a table that have one shape are one class,
and the compiler lowers one instance for each class.

The oracles are independent of the code that makes the classes and the families:

- the classes of a table are the groups of its rows by the facts that the test itself reads from its
  own data (which cells are empty, the state of the valve, the pool);
- the flat lowering of the whole file, which writes every instance out, is what the hybrid core must
  stand for: `hybrid.problems` writes the families out and compares, part by part and in the order of
  the parts;
- a family that holds a wrong value, and a list in a wrong order, are differences that the check
  finds.
"""

import dataclasses
import re
from types import MappingProxyType

import pytest

from napkin.core import expr
from napkin.model import ModelError, hybrid
from napkin.model.language import front
from napkin.model.model import build_model
from tests.model import test_tables as tables
from tests.owned import write_family


def tanks_of(count):
    """`count` tanks whose rows differ in every way that a table can make them differ: the rate is
    left out in each fifth row, the valve is shut in each fourth, and each third is of the other pool.
    Each rate is inside the range of its input (0 to 100), whatever the number of rows."""
    return [
        (
            f'Tank {k}',
            1 + (k % 600) / 7 if k % 5 else None,
            20 + k,
            'open' if k % 4 else 'shut',
            k % 2 == 0,
            f'owner {k}',
            'east' if k % 3 else 'west',
        )
        for k in range(1, count + 1)
    ]


def package(tmp_path, tanks, model=None, **more):
    files = {'SC97/model.scn': model or tables.with_table(), 'SC97/tanks.csv': tables.table(tanks), **more}
    return write_family(tmp_path, files)['SC97/model.scn']


def groups(tanks):
    """The rows of the tanks, from 1, grouped by what can change the shape of a row: whether it gives
    a rate, the state of its valve, and its pool. The other cells are values."""
    found = {}
    for k, (_, rate, _, valve, _, _, pool) in enumerate(tanks, 1):
        found.setdefault((rate is not None, valve, pool), []).append(k)
    return sorted(tuple(rows) for rows in found.values())


@pytest.mark.parametrize('count', [1, 2, 12, 57])
def test_the_classes_of_a_table_are_its_rows_grouped_by_what_can_change_their_shape(tmp_path, count):
    tanks = tanks_of(count)
    file, _ = front.load(package(tmp_path, tanks))
    found = hybrid.classes(file)
    assert sorted(of.rows for of in found['tanks']) == groups(tanks)
    assert all(of.representative == of.rows[0] and of.set == 'tanks' for of in found['tanks'])


def test_the_compiler_lowers_one_instance_for_each_class_whatever_the_number_of_rows(tmp_path):
    """Sixty rows have every class that the rows of this fixture can have, and 180 rows have the same
    classes: the model that the compiler lowers, checks and proves has the same things, so its cost
    does not grow with the rows."""
    few = hybrid.compile(package(tmp_path / 'few', tanks_of(60)))
    many = hybrid.compile(package(tmp_path / 'many', tanks_of(180)))
    assert len(few.families) == len(many.families) == len(groups(tanks_of(60)))
    assert list(few.model.entities) == list(many.model.entities)
    assert sum(len(family) for family in many.families) == 180
    whole = build_model(package(tmp_path / 'whole', tanks_of(60)))
    assert len(whole.entities) == len(few.model.entities) + 60 - len(few.families)


def test_a_sum_over_the_rows_is_one_node_with_one_member_for_each_class(tmp_path):
    core = hybrid.compile(package(tmp_path, tanks_of(40)))
    structure = next(iter(core.listed.values())).plain()
    node = expr.read(structure['outcomes']['lost']['expr'])
    assert isinstance(node, expr.Call) and node.function == 'sum'
    # The model that the checks read writes the same list as the chain of a flat structure.
    checked = next(iter(core.model.structures.values()))
    assert isinstance(checked.outcomes['lost'].expr, expr.Binary)
    assert [expr.text(arg) for arg in node.args] == [f'{family.host}.lost' for family in core.families]


@pytest.mark.parametrize('count', [1, 2, 3, 12, 23, 57])
def test_the_hybrid_core_stands_for_the_flat_lowering_of_every_row(tmp_path, count):
    """Every part of every instance, every value, every list and the order of the parts: the tables
    reach two digits, where the order of the names of the things is not the order of the rows."""
    core = hybrid.compile(package(tmp_path, tanks_of(count)))
    assert hybrid.problems(core) == []


def test_a_family_has_the_values_of_each_of_its_rows(tmp_path):
    """The values of the family against the numbers that the test wrote into the table."""
    tanks = tanks_of(12)
    core = hybrid.compile(package(tmp_path, tanks))
    for family in core.families:
        for j, row in enumerate(family.rows):
            title, rate, held, _, metered, owner, pool = tanks[row - 1]
            assert family.hosts[j] == f'tanks_{row}' and family.titles[j] == title
            if rate is not None:
                assert family.values['rate'][j] == rate
            assert family.values['metered'][j] == (1 if metered else 0)
            assert expr.read(family.starts['held'][j]) is expr.read(f"q({held}, 'episodes')")
            assert family.texts['owner'][j] == owner and family.links['pool'][j] == pool


def test_an_instance_that_a_line_names_alone_is_a_class_of_one(tmp_path):
    model = tables.with_table().replace(
        'output lost: episodes = sum(Tank.lost)',
        'output third: episodes = tanks.3.lost  @fixture\n    "Water that the third tank lost"\n    level\n\n'
        'output lost: episodes = sum(Tank.lost)',
    )
    same = [('Tank', 2, 30, 'open', True, 'a town', 'east')] * 6
    core = hybrid.compile(package(tmp_path, same, model))
    assert sorted(family.rows for family in core.families) == [(1, 2, 4, 5, 6), (3,)]
    assert hybrid.problems(core) == []


POOLS_BY_TABLE = tables.TEMPLATES.replace(
    'east: Pool  @fixture\n    "The east pool."\n\nwest: Pool  @fixture\n    "The west pool."\n    factor = 0.5  @fixture\n',
    'pools: Pool from "pools.csv"  @fixture\n    "The pools of the survey."\n',
)


def test_a_link_into_another_table_is_a_map_from_each_row_to_the_row_that_it_names(tmp_path):
    """The tanks of one class link to different pools of one class: the representative of the pools
    stands for the pool of each tank."""
    assert POOLS_BY_TABLE != tables.TEMPLATES
    model = tables.with_table().replace(tables.TEMPLATES, POOLS_BY_TABLE)
    pools = 'factor: fraction @survey\n1\n0.5\n0.25\n'
    tanks = [
        (f'Tank {k}', 1 + k / 3, 20 + k, 'open', False, 'a town', f'pools.{1 + k % 3}') for k in range(1, 10)
    ]
    core = hybrid.compile(package(tmp_path, tanks, model, **{'SC97/pools.csv': pools}))
    assert sorted(len(family) for family in core.families) == [3, 9]
    tank_family = next(family for family in core.families if family.of.set == 'tanks')
    assert tank_family.links['pool'] == tuple(f'pools_{1 + k % 3}' for k in range(1, 10))
    assert hybrid.problems(core) == []


def test_the_check_finds_a_family_with_a_wrong_value_and_a_list_in_a_wrong_order(tmp_path):
    core = hybrid.compile(package(tmp_path, tanks_of(12)))
    first = core.families[0]
    assert len(first) > 1
    wrong_rate = tuple(value + 1 if j == 1 else value for j, value in enumerate(first.values['rate']))
    wrong = dataclasses.replace(first, values=MappingProxyType({**first.values, 'rate': wrong_rate}))
    found = hybrid.problems(dataclasses.replace(core, families=(wrong, *core.families[1:])))
    assert [(kind, place.rsplit('/', 2)[-2:]) for kind, place, *_ in found] == [
        ('value', [f'{first.hosts[1]}.rate', 'value'])
    ]
    # The rows of the family in another order: the names, the values and the sum over the rows move.
    turned = dataclasses.replace(first, rows=first.rows[::-1])
    found = hybrid.problems(dataclasses.replace(core, families=(turned, *core.families[1:])))
    assert found and any(place.endswith('/outcomes/lost/expr') for _, place, *_ in found)


def test_a_model_with_no_table_has_no_family_and_is_its_own_core(tmp_path):
    path = write_family(tmp_path, {'SC98/model.scn': tables.by_hand()})['SC98/model.scn']
    core = hybrid.compile(path)
    assert core.families == () and hybrid.problems(core) == []
    assert list(core.model.entities) == list(build_model(path).entities)


def test_a_sum_over_many_rows_is_too_long_for_a_flat_structure_and_one_node_of_the_hybrid_core(tmp_path):
    """A flat structure writes a list member by member, so a sum over 700 rows is over the limit of
    the size of an expression: the flat compile refuses it with a diagnostic, not with a failure of
    the program. The hybrid core lowers one instance for each class, and the sum is one node."""
    path = package(tmp_path, tanks_of(700))
    with pytest.raises(ModelError) as raised:
        build_model(path)
    assert [item['code'] for item in raised.value.diagnostics] == ['expression']
    core = hybrid.compile(path)
    assert sum(len(family) for family in core.families) == 700
    assert len(core.model.entities) == len(
        hybrid.compile(package(tmp_path / 'few', tanks_of(60))).model.entities
    )


@pytest.mark.parametrize('count', [2, 57, 700])
def test_a_second_representative_is_lowered_as_the_first_one_says(tmp_path, count):
    """The check for a model of any size: the last instance of each class, lowered by itself, has the
    parts that the first representative gives it. 700 rows are more than a flat structure can hold a
    sum over."""
    core = hybrid.compile(package(tmp_path, tanks_of(count)))
    assert hybrid.second_problems(core) == []


def test_the_second_representative_shows_a_family_with_a_wrong_value(tmp_path):
    core = hybrid.compile(package(tmp_path, tanks_of(57)))
    first = next(family for family in core.families if len(family) > 2 and 'rate' in family.values)
    rates = first.values['rate']
    # The value of the last instance is wrong: the instance that the second lowering makes.
    wrong = dataclasses.replace(
        first, values=MappingProxyType({**first.values, 'rate': (*rates[:-1], rates[-1] + 1)})
    )
    families = tuple(wrong if family is first else family for family in core.families)
    found = hybrid.second_problems(dataclasses.replace(core, families=families))
    assert [(kind, place.rsplit('/', 2)[-2:]) for kind, place, *_ in found] == [
        ('value', [f'{first.hosts[-1]}.rate', 'value'])
    ]
    # A wrong value of an instance in the middle is not what this check reads: it reads the last one.
    middle = dataclasses.replace(
        first, values=MappingProxyType({**first.values, 'rate': (rates[0], rates[1] + 1, *rates[2:])})
    )
    families = tuple(middle if family is first else family for family in core.families)
    assert hybrid.second_problems(dataclasses.replace(core, families=families)) == []


# ---- what the hybrid core does not hold: it says so, and gives no other model ------------------------

SELF_LIST = """scenario "A list in a template"
    summary "Each cell grows with the level of all cells."
    horizon 10 days
    scope "Nothing: the model is synthetic."

Cell:  @fixture
    "One cell."
    let start: fraction = 0.05  @fixture
    var level: fraction = start size 1  @fixture
    flow grow: -> level at 0.1 ratio/day * sum(Cell.level) / 10

cells: Cell from "cells.csv"

output total: fraction = sum(Cell.level)  @fixture
    "Level of all cells"
    level

record fixture: assumption "A fixture of the tests, with no source."
"""


def test_a_list_over_a_table_in_a_line_of_its_own_template_is_refused_by_the_hybrid_core(tmp_path):
    """In a part of a representative, its own name stands for each instance, and a member of a list
    over the same rows has that name too. The hybrid core cannot hold both readings, so it refuses the
    model by name; the flat lowering of the same file writes the list of every cell."""
    files = {'SC97/model.scn': SELF_LIST, 'SC97/cells.csv': 'start: fraction @fixture\n0.05\n0.1\n0.2\n'}
    path = write_family(tmp_path, files)['SC97/model.scn']
    with pytest.raises(ModelError) as raised:
        hybrid.compile(path)
    assert [item['code'] for item in raised.value.diagnostics] == ['hybrid']
    assert 'Cell' in raised.value.diagnostics[0]['message']
    flat = next(iter(build_model(path).structures.values()))
    assert expr.names(flat.rates['cells_2.level'].expr) >= {
        'cells_1.level',
        'cells_2.level',
        'cells_3.level',
    }


def test_a_condition_whose_kind_changes_with_the_number_of_rows_is_refused_by_the_hybrid_core(tmp_path):
    """A condition on the sum of the levels of the cells is a crossing of one value when the model
    has one cell of each class, and a condition on many values that move when it has every cell. The
    compiler refuses the second. So the model of the representatives passes a check that the whole
    model fails: the hybrid core refuses the model, as the flat compile does."""
    model = SELF_LIST.replace(' * sum(Cell.level) / 10', '').replace(
        'output total:',
        'watch:  @fixture\n    "The watcher."\n    var full = false  @fixture\n'
        '    event fill once when sum(Cell.level) >= 3:  @fixture\n        "The cells are full."\n'
        '        full = true\n\noutput total:',
    )
    assert model != SELF_LIST and 'sum(Cell.level) >= 3' in model
    files = {'SC97/model.scn': model, 'SC97/cells.csv': 'start: fraction @fixture\n0.05\n0.1\n0.2\n'}
    path = write_family(tmp_path, files)['SC97/model.scn']
    with pytest.raises(ModelError):
        build_model(path)
    with pytest.raises(ModelError) as raised:
        hybrid.compile(path)
    assert [item['code'] for item in raised.value.diagnostics] == ['hybrid']
    assert 'watch.fill' in raised.value.diagnostics[0]['message']


def test_a_condition_that_the_classifier_refuses_with_every_row_is_refused_by_the_hybrid_core(tmp_path):
    """The same sum with a clock beside it. With one cell of each class it is a crossing with a
    clock, which the compiler takes. With every cell it is a condition on many values that move,
    and such a condition goes with no clock: the classifier refuses it. The hybrid core gives the
    listed structure no class for it and refuses the model by the name of the event, as the flat
    compile refuses it."""
    model = SELF_LIST.replace(' * sum(Cell.level) / 10', '').replace(
        'output total:',
        'watch:  @fixture\n    "The watcher."\n    var full = false  @fixture\n'
        '    event fill once when sum(Cell.level) >= 3 and t >= 1 h:  @fixture\n        "The cells are full."\n'
        '        full = true\n\noutput total:',
    )
    assert model != SELF_LIST and 'sum(Cell.level) >= 3 and t >= 1 h' in model
    files = {'SC97/model.scn': model, 'SC97/cells.csv': 'start: fraction @fixture\n0.05\n0.1\n0.2\n'}
    path = write_family(tmp_path, files)['SC97/model.scn']
    with pytest.raises(ModelError):
        build_model(path)
    with pytest.raises(ModelError) as raised:
        hybrid.compile(path)
    assert [item['code'] for item in raised.value.diagnostics] == ['hybrid']
    assert 'watch.fill' in raised.value.diagnostics[0]['message']


# ---- the checks of a template -------------------------------------------------------------------------

CHECKED = tables.TEMPLATES.replace(
    '    flow drain: held -> lost at rate * pool.factor while valve is "open"  @fixture\n',
    '    flow drain: held -> lost at rate * pool.factor while valve is "open"  @fixture\n'
    '    assert lost <= 2000 episodes  @fixture\n        "A tank loses no more than it can hold twice."\n'
    '    assert held + lost is 2 * held + lost - held within 1 episodes  @fixture\n'
    '        "The water of a tank is in it or lost."\n',
)


@pytest.mark.parametrize('count', [1, 2, 12])
def test_each_row_has_the_checks_of_its_template_under_the_names_of_the_flat_structure(tmp_path, count):
    """The builder names a check by its template and its number, and by its thing too when the
    template has more than one instance. A table of one row has `Tank.0`; a table of many rows has
    `Tank.0.tanks_k` for each row k, though the model of the representatives has one tank of a class
    and so the name without the thing. The oracle is the flat lowering of the whole file."""
    assert CHECKED != tables.TEMPLATES
    model = tables.with_table().replace(tables.TEMPLATES, CHECKED)
    path = package(tmp_path, tanks_of(count), model)
    core = hybrid.compile(path)
    assert hybrid.problems(core) == []
    flat = next(iter(build_model(path).structures.values()))
    assert len(flat.state_checks) == count and len(flat.partitions) == count
    assert hybrid.second_problems(core) == []


# ---- the proofs of a table hold for every row ---------------------------------------------------------
#
# The model of the representatives is proved for one row of each class. The hybrid core proves each
# declared run once more over the range of the rows of each class. The definition is the flat compile
# of the same file, which proves each row by itself.

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 10 days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'


def small(tmp_path, body, header, rows):
    """A model with `body` and the table of its cells: one row for each of `rows`, a value or a
    tuple of values."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / 'model.scn').write_text(HEAD + body + RECORD, encoding='utf-8')
    lines = [','.join(repr(float(v)) for v in (row if isinstance(row, tuple) else (row,))) for row in rows]
    (tmp_path / 'cells.csv').write_text('\n'.join([header, *lines]) + '\n', encoding='utf-8')
    return tmp_path / 'model.scn'


def refusal(make, path):
    """The diagnostics of a refusal, or None when the model is admitted."""
    try:
        make(path)
    except ModelError as problem:
        return problem.diagnostics
    return None


DIVIDED = """Cell:  @shape
    "A cell that fills at a pace over its divisor."
    let divisor: ratio = 2 ratio  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at 1 fraction/day / divisor

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_a_row_that_breaks_a_domain_is_refused_where_the_row_of_the_representative_is_fine(tmp_path):
    """Each cell divides by the divisor of its row. The first row, which stands for its class, has
    the divisor 2; the third has 0. The flat compile refuses the division of the third row, and the
    hybrid core refuses the class. With no zero in the column, both admit the model."""
    header = 'divisor: ratio @shape'
    rows = [2, 4, 0, 5]
    bad = small(tmp_path / 'bad', DIVIDED, header, rows)
    flat, found = refusal(build_model, bad), refusal(hybrid.compile, bad)
    assert [item['code'] for item in flat] == [item['code'] for item in found] == ['dynamic_domain']
    # The refusal is of the part of the template, and it names the row that stands for the class and
    # the number of the rows of the class, from the table of the test.
    assert found[0]['path'] == 'Cell/fill'
    words = set(re.findall(r'[\w.]+', found[0]['message']))
    assert {'cells_1.divisor', str(len(rows))} <= words
    good = small(tmp_path / 'good', DIVIDED, header, [2, 4, 5])
    assert refusal(build_model, good) is None and refusal(hybrid.compile, good) is None


SUMMED = """Cell:  @shape
    "A cell with a level that rises."
    var level: fraction = 1 fraction in 0 fraction to 2 fraction size 1 fraction  @shape
    flow rise: -> level at 0.01 fraction/day

cells: Cell from "cells.csv"

pool:  @shape
    "What reads the cells together."
    var out: fraction = 0 size 1  @shape
    flow drain: -> out at 1 fraction/day * 1 fraction / (10 fraction - sum(Cell.level))

output out: fraction = pool.out  @shape
    "What the pool gave"
"""


@pytest.mark.parametrize('count', [1, 4, 5, 6])
def test_a_proof_over_a_sum_of_the_rows_holds_for_the_number_of_the_rows(tmp_path, count):
    """Each level is from 0 to 2, so the sum of n levels is from 0 to 2 n. The divisor `10 - sum` has
    a proof that it is not zero while 2 n is under 10: with 1 and 4 rows, and not with 5 and 6. One
    row stands for all of them in the model of the representatives, where the sum is from 0 to 2
    whatever the number of rows. The hybrid core admits what the flat compile admits."""
    path = small(tmp_path, SUMMED, 'level: fraction @shape', [1] * count)
    flat, found = refusal(build_model, path), refusal(hybrid.compile, path)
    assert (flat is None) == (found is None) == (2 * count < 10)
    if found is not None:
        assert [item['code'] for item in found] == [item['code'] for item in flat] == ['dynamic_domain']


PAIRED = """Cell:  @shape
    "A cell whose first value is above its second in each row."
    let high: fraction = 1  @shape
    let low: fraction = 0  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at 1 fraction/day * sqrt((high - low) / 1 fraction)

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_a_proof_that_needs_two_columns_of_one_row_together_is_refused_with_the_name_of_the_class(tmp_path):
    """In each row the first value is above the second, so the root has a value for every row, and
    the flat compile admits the model. Over the class the first value is from 1 to 5 and the second
    from 0 to 4: the range of their difference goes below zero. The hybrid core proves over the
    ranges, so it refuses the model, and says which class: the limit of the proofs of a table. With
    one row the ranges are points, and it admits the model."""
    header = 'high: fraction @shape,low: fraction @shape'
    path = small(tmp_path / 'many', PAIRED, header, [(1, 0), (5, 4), (3, 2.5)])
    assert refusal(build_model, path) is None
    (found,) = refusal(hybrid.compile, path)
    assert found['code'] == 'dynamic_domain'
    assert 'over the range of the 3 rows of cells that row 1 stands for' in found['message']
    one = small(tmp_path / 'one', PAIRED, header, [(5, 4)])
    assert refusal(hybrid.compile, one) is None


LEVELS = """Cell:  @shape
    "A cell with a level between its bounds."
    let cap: fraction = 1  @shape
    var level: fraction = 0.1 fraction in 0 fraction to {top} size 1 fraction  @shape
    flow rise: -> level at 0.01 fraction/day

cells: Cell from "cells.csv"

output level: fraction = sum(Cell.level)  @shape
    "The levels"
    level
"""


def test_the_start_of_each_row_is_inside_its_bounds_and_a_bound_is_one_value_for_a_class(tmp_path):
    """A column gives the start of the level of each row, and the level is at most 1. A row that
    starts at 1.5 is refused by both compiles. A bound that reads a value of a column is another
    bound for each row: the flat compile admits it, and the hybrid core, which holds one bound for a
    class, refuses it by name; with one value in the column it admits it."""
    fixed = LEVELS.replace('{top}', '1 fraction')
    header = 'level: fraction @shape'
    outside = small(tmp_path / 'outside', fixed, header, [0.2, 0.5, 1.5])
    flat, found = refusal(build_model, outside), refusal(hybrid.compile, outside)
    assert [item['code'] for item in flat] == [item['code'] for item in found] == ['initial_bound']
    inside = small(tmp_path / 'inside', fixed, header, [0.2, 0.5, 0.9])
    assert refusal(build_model, inside) is None and refusal(hybrid.compile, inside) is None
    capped = LEVELS.replace('{top}', 'cap')
    two = small(tmp_path / 'two', capped, 'cap: fraction @shape', [1, 2])
    assert refusal(build_model, two) is None
    (found,) = refusal(hybrid.compile, two)
    assert found['code'] == 'bounds' and found['path'].endswith('/max')
    same = small(tmp_path / 'same', capped, 'cap: fraction @shape', [2, 2])
    assert refusal(hybrid.compile, same) is None


RANGED = """Cell:  @shape
    "A cell that fills at the pace of its row."
    input pace: fraction/day = 0.5 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at pace

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_the_value_of_each_row_is_inside_the_range_of_its_input(tmp_path):
    """The pace of a cell is from 0 to 1. The third row gives 1.5: the flat compile refuses the value
    of that instance, and the hybrid core, whose model has the value of the first row of the class
    only, refuses the value too, with the same code, under the input of the class. With every pace
    inside the range, both admit the model."""
    header = 'pace: fraction/day @shape'
    bad = small(tmp_path / 'bad', RANGED, header, [0.2, 0.4, 1.5])
    flat, found = refusal(build_model, bad), refusal(hybrid.compile, bad)
    assert {item['code'] for item in flat} == {item['code'] for item in found} == {'bounds'}
    assert found[0]['path'].endswith('cells_1.pace') and '1.5' in found[0]['message']
    good = small(tmp_path / 'good', RANGED, header, [0.2, 0.4, 0.9])
    assert refusal(build_model, good) is None and refusal(hybrid.compile, good) is None


SIGNED = """Cell:  @shape
    "A cell with an offset that can be below zero."
    input offset: fraction = 0 fraction in -5 fraction to 5 fraction  @shape
    var held: fraction = 2 size 10  @shape
    flow fill: -> held at 0.01 fraction/day

cells: Cell from "cells.csv"

output offsets: fraction = sum(Cell.offset)  @shape
    "The offsets of the cells together"
    level
    signed
"""


def test_a_cell_can_give_a_number_below_zero(tmp_path):
    """A cell such as `-1.5` is the negation of 1.5, as in a formula. Both compiles read each cell as
    the number of the table; a cell that is not a number is still refused."""
    offsets = [-1.5, 2.0, -0.25, -3.0]
    path = small(tmp_path / 'signed', SIGNED, 'offset: fraction @shape', offsets)
    model = build_model(path)
    assert [model.inputs[f'cells_{k}.offset']['value'] for k in range(1, 5)] == offsets
    core = hybrid.compile(path)
    found = {
        row: family.values['offset'][j] if 'offset' in family.values else None
        for family in core.families
        for j, row in enumerate(family.rows)
    }
    assert found == dict(enumerate(offsets, 1))
    for cell in ('-x', '--1', '-'):
        wrong = tmp_path / f'wrong{len(cell)}{cell.count("-")}'
        small(wrong, SIGNED, 'offset: fraction @shape', [1.0])
        (wrong / 'cells.csv').write_text(f'offset: fraction @shape\n{cell}\n', encoding='utf-8')
        assert refusal(build_model, wrong / 'model.scn') is not None


def test_the_core_keeps_what_was_proved_for_every_row_of_each_declared_run(tmp_path):
    """A core with a class of more than one row has, for each declared run, the facts that the
    checks proved over the rows; a core whose classes have one row each has none, because the model
    of the representatives is then the whole model."""
    many = hybrid.compile(small(tmp_path / 'many', DIVIDED, 'divisor: ratio @shape', [2, 4, 5]))
    assert set(many.facts) == set(many.model.runs)
    for run, facts in many.facts.items():
        assert set(facts) == {
            'proven_zero_stock_faces',
            'proven_monotone_crossings',
            'proven_cumulative_outcomes',
        }
        assert many.proved(run) is facts
    one = hybrid.compile(small(tmp_path / 'one', DIVIDED, 'divisor: ratio @shape', [2]))
    assert dict(one.facts) == {} and one.proved(next(iter(one.model.runs))) is None


NAMED = """Cell:  @shape
    "A cell that fills, with an event that a line of another event names."
    let divisor: ratio = 2 ratio  @shape
    var held: fraction = 0 size 1  @shape
    var noted: fraction = 0 size 1  @shape
    flow fill: -> held at 1 fraction/day / divisor
    event begin once when t >= 5 h:  @shape
        "The cell begins."
        note
    event note:  @shape
        "The cell is noted."
        noted = 1

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_the_proofs_over_the_rows_read_an_event_that_has_no_condition(tmp_path):
    """An event with no condition triggers when a line names it, so its trigger has no place of a
    condition. The proofs over the rows of its class read it as they read any other event: the
    hybrid core admits the model, as the flat compile does, and has the facts of each declared run."""
    path = small(tmp_path, NAMED, 'divisor: ratio @shape', [2, 4, 5])
    assert refusal(build_model, path) is None
    core = hybrid.compile(path)
    (listed,) = core.listed.values()
    # The trigger with no condition has the place of its rule; each other has the place of its
    # condition. Each one has its class, which the proofs of every run read.
    assert [name for name, rule in listed.rules.items() if rule.trigger.path == rule.path] == ['cells_1.note']
    assert all(rule.trigger.kind is not None for rule in listed.rules.values())
    assert core.facts and set(core.facts) == set(core.model.runs)


def test_a_zero_face_that_is_proved_over_the_rows_holds_for_each_row_by_itself(tmp_path):
    """The flat compile of the same file writes each tank out, and proves the zero face of each
    tank by itself. The proofs over the rows prove a face once for a class, under the name of its
    representative. Where they do, the flat compile has the face of every row of that class. The
    class of the tanks with no rate of their own (two rows, one value of the rate) has its face:
    the proofs over the rows read the class of each trigger, which the listed structure gets from
    the classifier of the checks of a structure."""
    path = package(tmp_path, tanks_of(12))
    core, flat = hybrid.compile(path), build_model(path)
    for run in core.model.runs:
        each = set(flat.resolve(run).proven_zero_stock_faces)
        assert len(each) == 12
        sizes = []
        for name in core.proved(run)['proven_zero_stock_faces']:
            host, member = name.split('.', 1)
            (family,) = [family for family in core.families if family.host == host]
            assert {f'{row}.{member}' for row in family.hosts} <= each
            sizes.append(len(family))
        assert sizes and max(sizes) > 1


MOVING = """Cell:  @shape
    "A cell whose level rises at a pace that grows with the time."
    let pace: fraction/day = 0.3 fraction/day  @shape
    var level: fraction = 5 fraction in 0 fraction to 10 fraction size 1 fraction  @shape
    var seen: fraction = 0 fraction size 1 fraction  @shape
    flow gain: -> level at pace * (1 + t / 100 h)
    event high once when level >= 5.2 fraction:  @shape
        "The level is high."
        seen = 1 fraction

cells: Cell from "cells.csv"

output seen: fraction = sum(Cell.seen)  @shape
    "The cells whose level was high"
    level
"""


def test_a_crossing_of_a_level_that_only_rises_is_proved_for_every_row(tmp_path):
    """The pace of each cell grows with the time, so the level has no constant rate: a condition on
    it needs a level that only rises or only falls. It only rises, whatever the pace of a row is.
    The flat compile proves the crossing of each row by itself. The proofs over the rows prove it
    once, for the representative of the two rows, over the range of their paces: the engine then
    has the fact for the class."""
    path = small(tmp_path, MOVING, 'pace: fraction/day @shape', [0.3, 0.4])
    core, flat = hybrid.compile(path), build_model(path)
    for run in core.model.runs:
        assert set(flat.resolve(run).proven_monotone_crossings) == {'cells_1.high', 'cells_2.high'}
        assert list(core.proved(run)['proven_monotone_crossings']) == ['cells_1.high']


# ---- an input drawn from a distribution that reads a column ---------------------------------------

DRAWN_FROM_A_COLUMN = """Cell:  @shape
    "A cell whose pace is drawn up to its own cap."
    input cap: fraction/day = 1 fraction/day in 0 fraction/day to 5 fraction/day  @shape
    input pace: fraction/day = uniform(0 fraction/day, cap) in 0 fraction/day to 5 fraction/day  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at pace

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def held_after_ten_days(model):
    from napkin.engine import evaluate_study, sample_result

    report = sample_result(evaluate_study(model))
    assert report['admissible'], report['diagnostics']
    (run,) = report['runs'].values()
    return list(run['reporting_points'].values())[-1]['values']['held']


def test_an_input_drawn_from_a_distribution_that_reads_a_column_is_refused_by_the_hybrid_core(tmp_path):
    """The pace of a cell is drawn from `uniform(0, cap)`, and `cap` is a column. The central value
    of the pace of each cell is its cap over 2, and in 10 days a cell holds 10 days times that: with
    the caps 1, 2 and 3, the cells hold 5, 10 and 15, and 30 together. The flat compile has a pace
    for each row and gives 30. The hybrid core would hold one pace for the class, from the cells of
    one row; it refuses the model, by the name of the input. A class of one row is its own
    representative, and is admitted with the value of the flat compile."""
    path = small(tmp_path / 'three', DRAWN_FROM_A_COLUMN, 'cap: fraction/day @shape', [1, 2, 3])
    assert held_after_ten_days(build_model(path)) == pytest.approx(30.0, rel=1e-9)
    found = refusal(hybrid.compile, path)
    assert found and {item['code'] for item in found} == {'hybrid'}
    assert all('pace' in item['path'] for item in found)
    one = small(tmp_path / 'one', DRAWN_FROM_A_COLUMN, 'cap: fraction/day @shape', [3])
    assert refusal(hybrid.compile, one) is None
    assert held_after_ten_days(build_model(one)) == pytest.approx(15.0, rel=1e-9)
