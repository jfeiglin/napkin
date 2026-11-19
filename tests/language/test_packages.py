"""Packages (spec, "How templates compose into a run"; R-A5-03, R-A5-05, R-A5-07): a main file and
the modules that it uses are one model, a variant reads its package first and changes it, and each
problem of the files is placed at its own file and line. The hash of a model follows what it
computes and how its runs are configured, and no label (`napkin/model/identity.py`).

The packages are written in `tmp_path`. The join of the slice is the package `pumps`: a variant, two
options and an edit, whose program and configuration are asserted from source against a program built
by hand (`test_the_join_...`)."""

from __future__ import annotations

import json
import shutil

import pytest

from napkin.model import identity
from napkin.model.compile import library_units, load_scenario
from napkin.model.language.modules import role_of
from napkin.model.language.problems import LanguageError
from napkin.model.library import load_library
from napkin.program.build import Builder, flow, input_, named, q, this, value
from napkin.program.canonical import program_bytes
from napkin.program.config import InputValue, Quantity

MAIN = """\
scenario "Pumps"
    summary "A pool that two tanks draw on."
    horizon 4 h
    scope "The tanks."
use common

options "Pace":
    "Steady":
        "The tanks ask what they ask."
    "Fast":
        "Every tank asks for 2 L/h, and the first for 3 L/h."
        Tank.instances.ask = 2 L/h  @pace
        first.ask = 3 L/h  @pace

options "Pool":
    "Low pool":
        "The pool starts at 12 L."
        pool.start_water = 12 L  @pool_size

runs:
    steady = "Steady"
    fast_low = "Fast" + "Low pool"
"""

COMMON = """\
Tank:
    "A tank that the pool fills."
    input ask: L/h = 1 L/h in [0 L/h, 10 L/h]  @pace
    got: L = 0 L in [0 L,]
    flow take: pool.water -> this.got
        request = this.ask

pool:
    "The pool."
    input start_water: L = 30 L in [1 L, 100 L]  @pool_size
    water: L = this.start_water in [0 L,]

first: Tank

second: Tank
    ask = 1.5 L/h  @pace

record pace: assumption "The rates of the tanks."
record pool_size: assumption "The water of the pool."
"""

EAST = """\
variant "East"
    horizon 6 h

change pool:
    "The pool of the east."
    start_water = 20 L  @pool_size

change second:
    ask = 4 L/h  @pace
"""

UNITS = {'L': {'dimensions': {'volume': 1}, 'scale': 1}}


def package(root, files=None, units=UNITS):
    """The package `pumps` below `root`, with `files` ({name: text}) in place of its own, and its
    units file. A text of None leaves a file out."""
    files = {'model.scn': MAIN, 'common.scn': COMMON, 'variants/east/model.scn': EAST, **(files or {})}
    folder = root / 'pumps'
    for name, text in files.items():
        if text is not None:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
    return folder


def problems(path):
    with pytest.raises(LanguageError) as caught:
        load_scenario(path)
    return caught.value.problems


def flat(root, text):
    """A package whose main file holds `text` and nothing else."""
    folder = root / 'flat'
    folder.mkdir(parents=True)
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(UNITS), encoding='utf-8')
    return folder / 'model.scn'


def one_file(main=MAIN, common=COMMON):
    """The main file and its module written as one file: the module's lines in place of the use."""
    head, tail = main.split('use common\n')
    return f'{head}\n{common}\n{tail}'


def hand_program(entry, start_water=30, second=1.5, ask=1):
    """The program of the package by hand (napkin/program/build.py), with the pool's start water, the
    second tank's own ask and the template's ask in place."""
    b = Builder(library_units(load_library(entry)))
    b.template(
        'Tank',
        input_('ask', 'L/h', q(ask, 'L/h'), lower=q(0, 'L/h'), upper=q(10, 'L/h')),
        value('got', 'L', q(0, 'L'), lower=q(0, 'L')),
        flow('take', named('pool').water, this.got, request=this.ask),
    )
    b.entity(
        'pool',
        input_('start_water', 'L', q(start_water, 'L'), lower=q(1, 'L'), upper=q(100, 'L')),
        value('water', 'L', this.start_water, lower=q(0, 'L')),
    )
    b.member('Tank', 'first')
    b.member('Tank', 'second', ask=q(second, 'L/h'))
    return b.finish()


# ---- the join ----------------------------------------------------------------------------------------


def test_the_join_a_variant_two_options_and_an_edit_give_one_program_and_one_configuration(tmp_path):
    """The variant East changes the pool's start water to 20 L and the second tank's ask to 4 L/h, so
    its program is the package's with those values in place (the change wins over the member's own
    1.5 L/h). Its run `fast_low` takes Fast and Low pool, under an edit of every run, of the option Low
    pool and of the run: each input takes the narrowest value (R-A5-03), in its own unit."""
    folder = package(tmp_path)
    entry = folder / 'variants/east/model.scn'
    edits = {
        'schema_version': '0.0.1',
        'model_hash': load_scenario(entry).model_hash,
        'set': {'first.ask': 0.5},
        'options': {'Low pool': {'pool.start_water': '10 L'}},
        'runs': {'fast_low': {'second.ask': '2.5 L/h'}},
    }
    compiled = load_scenario(entry, run='fast_low', edits=edits)
    assert program_bytes(compiled.program) == program_bytes(hand_program(entry, 20, 4))
    assert compiled.configuration.inputs == (
        InputValue('first', 'ask', Quantity(0.5, 'L/h')),
        InputValue('pool', 'start_water', Quantity(10, 'L')),
        InputValue('second', 'ask', Quantity(2.5, 'L/h')),
    )
    assert (compiled.configuration.request.horizon, compiled.configuration.mode) == (6, 'median')
    # Without the edit, the options of the run give their values: a line of one member wins over a
    # line of every member of its template, and an option wins over the variant's change.
    assert compiled.configure('fast_low').inputs == (
        InputValue('first', 'ask', Quantity(3, 'L/h')),
        InputValue('pool', 'start_water', Quantity(12, 'L')),
        InputValue('second', 'ask', Quantity(2, 'L/h')),
    )
    assert compiled.configure('steady').inputs == compiled.configure().inputs == ()
    main = load_scenario(folder / 'model.scn')
    assert program_bytes(main.program) == program_bytes(hand_program(folder / 'model.scn'))
    assert main.model_hash != compiled.model_hash


# ---- one model of several files -------------------------------------------------------------------


def test_a_main_file_and_its_modules_are_the_model_of_one_file(tmp_path):
    """The module that two files use is read once; the model is the same declarations written in one
    file: the same program, the same options and runs, and so the same hash."""
    folder = package(
        tmp_path,
        {'extra.scn': 'use common\n', 'model.scn': MAIN.replace('use common\n', 'use common\nuse extra\n')},
    )
    split = load_scenario(folder / 'model.scn')
    whole = load_scenario(flat(tmp_path, one_file()))
    assert program_bytes(split.program) == program_bytes(whole.program)

    def menu(model):
        options = [(o.name, o.group, [(x.path, x.value) for x in o.settings]) for o in model.declared.options]
        return options, [(run.name, run.options) for run in model.declared.runs]

    assert menu(split) == menu(whole)
    assert split.model_hash == whole.model_hash


def test_a_variant_reads_its_package_first_and_overlays_its_scenario_lines(tmp_path):
    """A variant's scenario line is its package's with each line that it writes in its place, and its
    title follows its package's."""
    folder = package(tmp_path, {'variants/west/model.scn': 'variant "West"\n'})
    east = load_scenario(folder / 'variants/east/model.scn').declared.scenario
    west = load_scenario(folder / 'variants/west/model.scn').declared.scenario
    assert (east.title, east.role, east.horizon, east.summary) == (
        'Pumps: East',
        'variant',
        6,
        'A pool that two tanks draw on.',
    )
    assert (west.title, west.horizon, west.scope) == ('Pumps: West', 4, 'The tanks.')
    assert load_scenario(folder / 'model.scn').declared.scenario.title == 'Pumps'


@pytest.mark.parametrize(
    ('text', 'role'),
    [
        ('scenario "A"\n', 'main'),
        ('# A comment comes first.\n\nvariant "A"\n', 'variant'),
        ('use other\n\nthing:\n    x = 1\n', 'module'),
        ('record r: assumption "A record."\n', 'module'),
        ('', 'module'),
    ],
)
def test_a_files_role_is_its_first_declaration(text, role):
    assert role_of(text) == role


def _line_of(text, words):
    return next(k for k, row in enumerate(text.split('\n'), 1) if row.strip().startswith(words))


@pytest.mark.parametrize(
    ('files', 'code', 'where', 'words'),
    [
        # A name that two files declare: at the second, naming the first.
        (
            {'variants/east/model.scn': EAST + '\npool:\n    water: L = 1 L\n'},
            'duplicate_name',
            'variants/east/model.scn',
            'pool:',
        ),
        # A use that names no module of the package.
        (
            {'model.scn': MAIN.replace('use common', 'use common\nuse nothing')},
            'use',
            'model.scn',
            'use nothing',
        ),
        # A use of an entry file: a variant is a model of its own.
        (
            {'model.scn': MAIN.replace('use common', 'use common\nuse variants.east.model')},
            'use',
            'model.scn',
            'use variants',
        ),
        # A change of a part that no earlier file declares.
        (
            {'variants/east/model.scn': EAST.replace('change pool:', 'change pools:')},
            'change',
            'variants/east/model.scn',
            'change pools',
        ),
        # A number that a change sets cites its record (R-A5-05).
        (
            {'variants/east/model.scn': EAST.replace('ask = 4 L/h  @pace', 'ask = 4 L/h')},
            'record',
            'variants/east/model.scn',
            'ask = 4 L/h',
        ),
        # A change of a value that the part does not declare.
        (
            {'variants/east/model.scn': EAST.replace('start_water = 20 L', 'level = 20 L')},
            'change',
            'variants/east/model.scn',
            'level = 20 L',
        ),
        # A change gives a value; it declares none.
        (
            {'variants/east/model.scn': EAST.replace('start_water = 20 L', 'start_water: L = 20 L')},
            'change',
            'variants/east/model.scn',
            'start_water: L',
        ),
        # A variant reads the library of its package.
        (
            {
                'variants/east/model.scn': EAST.replace(
                    '    horizon 6 h', '    horizon 6 h\n    library "../lib"'
                )
            },
            'scenario',
            'variants/east/model.scn',
            'variant "East"',
        ),
        # An error of a module's line, at that line of the module.
        (
            {'common.scn': COMMON.replace('this.start_water in', 'this.start_waters in')},
            'unknown_name',
            'common.scn',
            'water: L = this.start_waters',
        ),
    ],
)
def test_each_problem_of_the_files_is_at_its_file_and_line(tmp_path, files, code, where, words):
    folder = package(tmp_path, files)
    found = [item for item in problems(folder / 'variants/east/model.scn') if item.code == code]
    assert len(found) == 1, found
    text = {'model.scn': MAIN, 'common.scn': COMMON, 'variants/east/model.scn': EAST, **files}[where]
    assert (found[0].file, found[0].line) == ((folder / where).as_posix(), _line_of(text, words))


def test_a_circle_of_uses_and_a_module_that_is_a_main_file_are_refused(tmp_path):
    circle = package(tmp_path / 'one', {'common.scn': 'use other\n' + COMMON, 'other.scn': 'use common\n'})
    assert 'circle' in problems(circle / 'model.scn')[0].message
    main = package(tmp_path / 'two', {'common.scn': 'scenario "Not a module"\n' + COMMON})
    found = problems(main / 'model.scn')
    assert [item.code for item in found] == ['use'] and 'not a module' in found[0].message


def test_a_module_is_no_model_and_a_variant_lives_in_its_packages_variants(tmp_path):
    folder = package(tmp_path, {'east.scn': EAST})
    assert [item.code for item in problems(folder / 'common.scn')] == ['scenario']
    assert 'variants/<name>/model.scn' in problems(folder / 'east.scn')[0].message


# ---- what a change does -------------------------------------------------------------------------


def test_two_changes_of_one_value_are_an_error_whatever_the_order_of_the_files(tmp_path):
    """R-A5-03: two `change` lines on one value are an error; the later file does not win."""
    shared = 'change pool:\n    start_water = 10 L  @pool_size\n'
    variant = EAST.replace(
        'variant "East"\n    horizon 6 h\n', 'variant "East"\n    horizon 6 h\nuse shared\n'
    )
    folder = package(tmp_path, {'shared.scn': shared, 'variants/east/model.scn': variant})
    found = problems(folder / 'variants/east/model.scn')
    assert [item.code for item in found] == ['change']
    assert 'changed twice' in found[0].message and 'shared.scn' in found[0].message


def test_a_change_of_a_template_keeps_the_own_line_of_a_member(tmp_path):
    """A change of a template changes its declaration: the first tank takes the new 5 L/h, and the
    second keeps its own 1.5 L/h; a change of the member itself wins over its own line (the join)."""
    variant = 'variant "East"\n\nchange Tank:\n    ask = 5 L/h  @pace\n'
    folder = package(tmp_path, {'variants/east/model.scn': variant})
    entry = folder / 'variants/east/model.scn'
    assert program_bytes(load_scenario(entry).program) == program_bytes(hand_program(entry, ask=5))


def test_a_change_keeps_the_kind_of_a_value(tmp_path):
    """R-A5-07: a formula is changed by a formula, and a value with no calculation by none."""
    common = COMMON.replace(
        '    water: L = this.start_water in [0 L,]',
        '    water: L = this.start_water in [0 L,]\n    low = formula(this.water < 5 L)',
    )
    formula = 'variant "East"\n\nchange pool:\n    low = formula(this.water < 2 L)\n'
    scalar = 'variant "East"\n\nchange pool:\n    low = true  @pool_size\n'
    folder = package(tmp_path / 'one', {'common.scn': common, 'variants/east/model.scn': formula})
    low = load_scenario(folder / 'variants/east/model.scn').program.template('pool').part('low')
    assert low.kind == 'formula' and "q(2, 'L')" in str(low.init.expr.node)
    folder = package(tmp_path / 'two', {'common.scn': common, 'variants/east/model.scn': scalar})
    assert [item.code for item in problems(folder / 'variants/east/model.scn')] == ['formula']


LINKS = """\
Pool:
    water: L = 10 L in [0 L,]

north: Pool

south: Pool

Tank:
    "A tank."
    source = north
    got: L = 0 L in [0 L,]
    flow take: this.source.water -> this.got
        request = 1 L/h

first: Tank
"""


def test_a_change_rebinds_a_link_and_replaces_labels(tmp_path):
    """A change can rebind a connection and edit labels: the tank now draws on the south pool, and
    its text and title are the change's."""
    variant = 'variant "South"\n\nchange Tank:\n    "A tank of the south."\n    title "South tank"\n    source = south\n'
    main = 'scenario "Links"\n    horizon 1 h\nuse parts\n'
    folder = package(
        tmp_path,
        {'model.scn': main, 'common.scn': None, 'parts.scn': LINKS, 'variants/east/model.scn': variant},
    )
    compiled = load_scenario(folder / 'variants/east/model.scn')
    tank = compiled.declared.part('Tank')
    assert (tank.text, tank.title) == ('A tank of the south.', 'South tank')
    assert (
        compiled.program.template('Tank').members[0].link('source')
        == compiled.program.member('south')[1]
        == 1
    )
    assert load_scenario(folder / 'model.scn').program.template('Tank').members[0].link('source') == 0


def test_a_member_keeps_its_title_and_a_change_replaces_it(tmp_path):
    """A member's title is its own line's, and a variant's change of the member gives it another
    (PLAN, change 19): before the audit the change compiled and its title was lost. A member with no
    title, and a row of a table, has none."""
    common = COMMON.replace('first: Tank\n', 'first: Tank\n    title "The first tank"\n')
    variant = EAST.replace('change second:\n', 'change second:\n    title "The second tank"\n')
    folder = package(tmp_path, {'common.scn': common, 'variants/east/model.scn': variant})
    main = load_scenario(folder / 'model.scn').declared
    assert (main.title('first'), main.title('second'), main.part('second').title) == ('The first tank', None, None)
    east = load_scenario(folder / 'variants/east/model.scn').declared
    assert (east.title('first'), east.title('second')) == ('The first tank', 'The second tank')
    assert east.part('second').title == 'The second tank'


def test_an_entity_keeps_its_title_and_a_change_replaces_it(tmp_path):
    common = COMMON.replace('pool:\n    "The pool."\n', 'pool:\n    "The pool."\n    title "The pool"\n')
    variant = EAST.replace('change pool:\n', 'change pool:\n    title "The east pool"\n')
    folder = package(tmp_path, {'common.scn': common, 'variants/east/model.scn': variant})
    assert load_scenario(folder / 'model.scn').declared.title('pool') == 'The pool'
    assert load_scenario(folder / 'variants/east/model.scn').declared.title('pool') == 'The east pool'


def test_a_change_that_sets_a_role_is_refused_at_its_line(tmp_path):
    variant = EAST.replace('change second:\n', 'change second:\n    role operator\n')
    folder = package(tmp_path, {'variants/east/model.scn': variant})
    (problem,) = problems(folder / 'variants/east/model.scn')
    assert (problem.code, problem.file, problem.line) == ('role', (folder / 'variants/east/model.scn').as_posix(), 9)


# ---- the hash of a model --------------------------------------------------------------------------


def test_the_hash_keeps_labels_comments_and_records_and_follows_a_value(tmp_path):
    base = load_scenario(package(tmp_path / 'base') / 'model.scn').model_hash
    for name, common in (
        ('comment', '# A comment, and a blank line.\n\n' + COMMON),
        ('label', COMMON.replace('"The pool."', '"The pool, described again."')),
        ('record', COMMON.replace('"The rates of the tanks."', '"The rates, explained again."')),
    ):
        assert (
            load_scenario(package(tmp_path / name, {'common.scn': common}) / 'model.scn').model_hash == base
        )
    menu = MAIN.replace('"The pool starts at 12 L."', '"A smaller pool."')
    assert load_scenario(package(tmp_path / 'menu', {'model.scn': menu}) / 'model.scn').model_hash == base
    for name, files in (
        ('value', {'common.scn': COMMON.replace('= 30 L in', '= 31 L in')}),
        ('option', {'model.scn': MAIN.replace('pool.start_water = 12 L', 'pool.start_water = 13 L')}),
        ('run', {'model.scn': MAIN.replace('fast_low = "Fast" + "Low pool"', 'fast_low = "Fast"')}),
        ('horizon', {'model.scn': MAIN.replace('horizon 4 h', 'horizon 5 h')}),
    ):
        assert load_scenario(package(tmp_path / name, files) / 'model.scn').model_hash != base, name


def test_a_renamed_package_and_a_new_variant_keep_the_hashes(tmp_path):
    folder = package(tmp_path / 'one')
    east = load_scenario(folder / 'variants/east/model.scn').model_hash
    package(tmp_path / 'one', {'variants/west/model.scn': 'variant "West"\n    horizon 2 h\n'})
    assert load_scenario(folder / 'variants/east/model.scn').model_hash == east
    shutil.move(folder, tmp_path / 'one' / 'renamed')
    assert load_scenario(tmp_path / 'one/renamed/variants/east/model.scn').model_hash == east


def test_the_hash_covers_the_language_version(tmp_path, monkeypatch):
    entry = package(tmp_path) / 'model.scn'
    before = load_scenario(entry).model_hash
    monkeypatch.setattr(identity, 'LANGUAGE_VERSION', identity.LANGUAGE_VERSION + '.next')
    assert load_scenario(entry).model_hash != before


def test_a_text_written_out_as_a_package_has_the_same_hash(tmp_path):
    """The hash covers no file names: a model is its declarations, wherever its files are."""
    a = load_scenario(flat(tmp_path / 'a', one_file()))
    b = load_scenario(flat(tmp_path / 'b', '# Moved.\n' + one_file()))
    assert a.model_hash == b.model_hash


def test_the_notes_of_several_files_merge_key_by_key(tmp_path):
    """A later note replaces the note of its key, and the notes under one key merge the same way."""
    common = (
        COMMON + '\nnotes:\n    by: "The module"\n    limitations:\n        module_only: "Only the module."\n'
    )
    main = MAIN + '\nnotes:\n    by: "The tanks"\n    limitations:\n        tanks_only: "Only the tanks."\n'
    folder = package(tmp_path, {'common.scn': common, 'model.scn': main})
    notes = {note.key: note for note in load_scenario(folder / 'model.scn').declared.notes}
    assert notes['by'].value.value == 'The tanks'
    assert [note.key for note in notes['limitations'].notes] == ['module_only', 'tanks_only']


def test_a_setup_line_stands_where_the_initializer_of_its_declaration_stands(tmp_path):
    """R-A5-03: the main file initializes the pool's start water in its setup scope, which is its
    declaration's initializer; the variant's change wins over it, an option of the run over the change
    and an edit over the option."""
    common = COMMON.replace('input start_water: L = 30 L in', 'input start_water: L in')
    folder = package(tmp_path, {'common.scn': common, 'model.scn': MAIN + '\npool.start_water = 30 L\n'})
    main = load_scenario(folder / 'model.scn')
    assert program_bytes(main.program) == program_bytes(hand_program(folder / 'model.scn'))
    entry = folder / 'variants/east/model.scn'
    east = load_scenario(entry)
    assert program_bytes(east.program) == program_bytes(hand_program(entry, 20, 4))
    water = InputValue('pool', 'start_water', Quantity(12, 'L'))
    assert water in east.configure('fast_low').inputs
    edits = {'schema_version': '0.0.1', 'model_hash': east.model_hash, 'set': {'pool.start_water': 9}}
    assert InputValue('pool', 'start_water', Quantity(9, 'L')) in east.configure('fast_low', edits).inputs
