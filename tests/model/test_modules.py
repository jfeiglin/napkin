"""A model split across the files of a package (docs/language.md, §2.12): a main file and the modules
of its package that it uses are one model. The model of a main file and its modules is the model of the
same declarations written in one file: the same structure, apart from the places of the lines, and the
same runs, bit for bit. Each problem of the files is an error at its own file and line.
"""

import json

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.model import build_model
from tests.owned import write_family

HEAD = """    summary "Tanks. A synthetic fixture for tests only."
    horizon 12 h
    scope "Fixture"
    library "../library"
"""

TANK = """Tank:  @fixture
    "A tank that takes water from the pool."
    role environment
    input ask: people/h = 1 people/h in 0 people/h to 10 people/h  @fixture
        "Ask"
    var got: people = 0 people size 100 people  @fixture
        "Taken"
    flow take: pool.water -> got at ask  @fixture
    event full once when got >= 2 people:  @fixture
        "The tank is full."
"""

POOL = """pool:  @fixture
    "The pool that the tanks share."
    role environment
    input start_water: people = {water} in 1 people to 100 people  @fixture
        "Water at the start"
    var water: people = start_water size 100 people  @fixture
        "Water"
    share water limit 4 people/h order Tank.take  @fixture
    event stop once when t >= 1 h:  @fixture
        "The pool stops."
"""

SHARED = """assert pool.water + Tank.got is pool.start_water within 0.001 people  @fixture
    "Water is in the pool or taken."

output total: people = sum(Tank.got)  @fixture
    "Water taken"
    level

options "Response":
    "Default":
        "The defaults."

runs:
    a = "Default"

notes:
    by: "The module"
    limitations:
        module-only: "Only the module is counted."

record fixture: identity "Analytic contract fixture."
"""

TANKS = """a1: Tank  @fixture
    ask = 1 people/h  @fixture

a2: Tank  @fixture
    ask = 2 people/h  @fixture
"""

CHANGE = 'change pool:\n    start_water = {} people  @fixture\n'


def module(water='30 people', uses=()):
    lines = ''.join(f'use {name}\n' for name in uses)
    return f'{lines}{TANK}\n{POOL.format(water=water)}\n{SHARED}'


TANKS_CHANGED = TANKS + '\n' + CHANGE.format(20)


def scenario(uses=('common',), body=TANKS_CHANGED):
    lines = ''.join(f'use {name}\n' for name in uses)
    return f'scenario "Tanks"\n{HEAD}{lines}\n{body}'


def flat():
    """The same declarations in one file, with the change written in place."""
    shared = SHARED.split('\nrecord ')
    return (
        f'scenario "Tanks"\n{HEAD}\n{TANK}\n{POOL.format(water="20 people")}\n{TANKS}\n{shared[0]}\n'
        f'record {shared[1]}'
    )


def family(tmp_path, **extra):
    """The package SC97, whose main file uses its module `common`, and SC98, the same model in one
    file, below `tmp_path/scenarios`."""
    files = {'SC97/common.scn': module(), 'SC97/model.scn': scenario(), 'SC98/model.scn': flat(), **extra}
    return write_family(tmp_path, files)


def stripped(value):
    """A structure without the places, files and ranks of its lines, which differ between the two
    models; the runs below compare the order of the events."""
    if isinstance(value, dict):
        drop = ('path', 'place', 'line', 'where', 'file', 'rank')
        return {k: stripped(v) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [stripped(v) for v in value]
    return value


def plain_structures(model):
    """{start-state options: the plain data of the structure} of a model, for `stripped`."""
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


def test_a_scenario_and_its_modules_are_the_model_of_one_file(tmp_path):
    # The main file uses the module twice over (directly and through `extra`), which reads it once.
    extra = 'SC97/extra.scn'
    paths = family(
        tmp_path,
        **{
            extra: 'use common\n',
            'SC97/model.scn': scenario(uses=('common', 'extra')),
        },
    )
    split, whole = build_model(paths['SC97/model.scn']), build_model(paths['SC98/model.scn'])
    assert stripped(plain_structures(split)) == stripped(plain_structures(whole))
    assert stripped(thaw(split.inputs)) == stripped(thaw(whole.inputs))
    assert split.inputs['pool.start_water']['value'] == 20
    assert trajectory(split) == trajectory(whole)


@pytest.mark.parametrize(
    ('files', 'words', 'where'),
    [
        # A name that two files declare.
        (
            {'SC97/model.scn': scenario(body=TANKS + '\n' + POOL.format(water='5 people'))},
            'declared in',
            'model.scn',
        ),
        # A use that names no module file of the package.
        ({'SC97/model.scn': scenario(uses=('common', 'none'))}, 'no module', 'model.scn'),
        # A use of an entry file: a package's main file and a variant are no modules.
        ({'SC97/model.scn': scenario(uses=('common', 'variants.a.model'))}, 'not a module', 'model.scn'),
        # A circle of uses.
        (
            {'SC97/common.scn': module(uses=('other',)), 'SC97/other.scn': 'use common\n'},
            'circle',
            None,
        ),
        # A change of a thing that no earlier file declares.
        (
            {'SC97/model.scn': scenario(body=TANKS + '\n' + CHANGE.replace('pool', 'pool2').format(20))},
            'no earlier file',
            'model.scn',
        ),
        # A new value with no record of its own.
        (
            {'SC97/model.scn': scenario(body=TANKS + '\nchange pool:\n    start_water = 20 people\n')},
            'record of its own',
            'model.scn',
        ),
        # A change of a member that the thing does not have.
        (
            {'SC97/model.scn': scenario(body=TANKS + '\nchange pool:\n    level = 20 people  @fixture\n')},
            'is not a value',
            'model.scn',
        ),
        # A module whose first declaration is a scenario line: a main file, which no file uses.
        (
            {'SC97/common.scn': 'scenario "Tanks"\n' + HEAD + '\n' + module()},
            'not a module',
            'common.scn',
        ),
        # An error of a module's line, at that line of the module.
        ({'SC97/common.scn': module().replace('sum(Tank.got)', 'sum(Tank.gone)')}, 'gone', 'common.scn'),
    ],
)
def test_each_problem_of_the_files_is_an_error_at_its_file(tmp_path, files, words, where):
    paths = family(tmp_path, **files)
    found = [item for item in problems(paths['SC97/model.scn']) if words in item['message']]
    assert found, problems(paths['SC97/model.scn'])
    if where is not None:
        assert all(item['file'].endswith(where) for item in found)
    if words == 'gone':
        row = next(i for i, text in enumerate(files['SC97/common.scn'].split('\n'), 1) if 'Tank.gone' in text)
        assert any(item.get('line') == row for item in found)


def test_a_later_change_wins(tmp_path):
    left = 'use common\n\n' + CHANGE.format(10)
    files = {'SC97/left.scn': left, 'SC97/model.scn': scenario(uses=('left',), body=TANKS)}
    model = build_model(family(tmp_path / 'one', **files)['SC97/model.scn'])
    assert model.inputs['pool.start_water']['value'] == 10
    files['SC97/model.scn'] = scenario(uses=('left',), body=TANKS + '\n' + CHANGE.format(25))
    model = build_model(family(tmp_path / 'two', **files)['SC97/model.scn'])
    assert model.inputs['pool.start_water']['value'] == 25


def test_the_model_hash_keeps_a_comment_and_follows_a_value(tmp_path):
    base = build_model(family(tmp_path / 'base')['SC97/model.scn']).model_hash
    commented = module().replace('Tank:', '# A comment, and a blank line.\n\nTank:', 1)
    same = build_model(family(tmp_path / 'comment', **{'SC97/common.scn': commented})['SC97/model.scn'])
    assert same.model_hash == base
    other = module().replace('got >= 2 people', 'got >= 3 people')
    changed = build_model(family(tmp_path / 'value', **{'SC97/common.scn': other})['SC97/model.scn'])
    assert changed.model_hash != base


def test_options_runs_and_notes_of_several_files_merge(tmp_path):
    body = (
        TANKS
        + '\noptions "Response":\n    "Fast":\n        "A larger pool."\n'
        + '        pool.start_water = 40 people  @fixture\n'
        + '\nruns:\n    fast = "Fast"\n'
        + '\nnotes:\n    by: "The tanks"\n    limitations:\n        tanks-only: "Only the tanks are counted."\n'
    )
    model = build_model(family(tmp_path, **{'SC97/model.scn': scenario(body=body)})['SC97/model.scn'])
    assert list(model.menu['Response']) == ['Default', 'Fast']
    assert set(model.runs) == {'a', 'fast'}
    assert model.resolve('fast').parameter_values['pool.start_water'] == 40
    notes = {note.key: note for note in model.scenario.notes}
    # A later note replaces the note of its key, and the notes under a key that both hold merge.
    assert thaw(notes['by'].value) == 'The tanks'
    assert [entry.key for entry in notes['limitations'].notes] == ['module-only', 'tanks-only']


def variant(title, body=TANKS_CHANGED):
    """A variant's file: its line and its own declarations over its package's main file."""
    return f'variant "{title}"\n\n{body}'


def test_a_record_of_a_package_with_variants_is_used_by_one_of_its_variants(tmp_path):
    from napkin.model.library import unused_shared_records
    from tests.build import evidence_library, fixture_claim

    cites = 'record used: source_transfer "Applied here."\n    claims:\n        C-USED\n'
    shared = module().replace(
        'output total: people = sum(Tank.got)  @fixture', 'output total: people = sum(Tank.got)  @used'
    )
    paths = write_family(
        tmp_path,
        {
            'SC97/common.scn': shared + cites,
            'SC97/model.scn': scenario(body=''),
            'SC97/variants/a/model.scn': variant('A'),
        },
    )
    evidence = paths['SC97/common.scn'].parent / 'evidence'
    (evidence / 'sources.json').write_text(json.dumps(evidence_library()['sources']))
    (evidence / 'claims.json').write_text(json.dumps([fixture_claim('C-USED'), fixture_claim('C-UNUSED')]))
    assert build_model(paths['SC97/variants/a/model.scn'])
    package = paths['SC97/model.scn'].parent
    assert {item['path'] for item in unused_shared_records(package)} == {'SC97/evidence/claims/C-UNUSED'}
    # The check is the package's: another package of the catalogue, with records of its own, is not read.
    other = write_family(tmp_path / 'other', {'SC98/model.scn': scenario(uses=(), body='')})
    assert unused_shared_records(other['SC98/model.scn'].parent) == []


def test_a_pack_writes_the_records_of_one_folder_and_changes_no_other(tmp_path):
    from napkin.model.library import load_library
    from tests.build import evidence_library, fixture_claim
    from tools.evidence.integrate import IntegrationError, write_owned

    cite = 'record {0}: source_transfer "Applied here."\n    claims:\n        {1}\n'
    shared = module().replace(
        'output total: people = sum(Tank.got)  @fixture', 'output total: people = sum(Tank.got)  @used'
    )
    own = variant(
        'A', TANKS.replace('ask = 2 people/h  @fixture', 'ask = 2 people/h  @own') + '\n' + CHANGE.format(20)
    )
    paths = write_family(
        tmp_path,
        {
            'SC97/common.scn': shared + cite.format('used', 'C-USED'),
            'SC97/model.scn': scenario(body=''),
            'SC97/variants/a/model.scn': own + '\n' + cite.format('own', 'C-OWN'),
        },
    )
    entry = paths['SC97/variants/a/model.scn']
    common, mine = paths['SC97/common.scn'].parent, entry.parent
    (common / 'evidence' / 'sources.json').write_text(json.dumps(evidence_library()['sources']))
    (common / 'evidence' / 'claims.json').write_text(json.dumps([fixture_claim('C-USED')]))
    (mine / 'evidence' / 'claims.json').write_text(json.dumps([fixture_claim('C-OWN')]))

    def ids(folder):
        return [r['id'] for r in json.loads((folder / 'evidence' / 'claims.json').read_text())]

    library = load_library(entry)
    assert {r['id'] for r in library['claims']} >= {'C-USED', 'C-OWN'}
    write_owned(entry, library)
    assert (ids(common), ids(mine)) == (['C-USED'], ['C-OWN'])
    library['claims'].append(fixture_claim('C-NEW'))
    write_owned(entry, library, folder=common)
    assert (ids(common), ids(mine)) == (['C-USED', 'C-NEW'], ['C-OWN'])
    changed = next(r for r in library['claims'] if r['id'] == 'C-OWN')
    changed['limits'] = 'Changed.'
    with pytest.raises(IntegrationError, match='C-OWN'):
        write_owned(entry, library, folder=common)
    assert ids(mine) == ['C-OWN']
