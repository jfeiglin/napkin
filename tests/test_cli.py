"""The `napkin` command (napkin/cli.py) and what its commands share (napkin/commands/common.py).

The fake packages are written in tmp_path on the prelude's units, with their records in place and no
library: `shop`, a package without variants, and `chain`, a package with a module and two variants.
Each command has a section of its own below the shared ones.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from napkin import cli, commands, paths
from napkin.commands import common
from napkin.engine import evaluate_study, sample_result
from napkin.model.ir import thaw

ROOT = Path(__file__).resolve().parents[1]
PRELUDE = ROOT / 'napkin' / 'std' / 'units.json'
EDITS_SCHEMA = ROOT / 'napkin' / 'schema' / 'edits.schema.json'

FIXTURE = '@identity "A synthetic fixture for tests only."'

SHOP = f"""\
scenario "A shop"
    summary "A shop that serves the people who wait. A synthetic fixture for tests only."
    horizon 720 h
    scope "Fixture"

shop:
    "A shop."
    {FIXTURE}
    role operator
    input rate: people/h = 1 people/h in 0.1 people/h to 10 people/h
        "Service rate"
        {FIXTURE}
    var state: "open" | "closed" = "open"
        "Open or closed"
        {FIXTURE}
    var waiting: people = 10 people size 100 people
        "People waiting"
        {FIXTURE}
    var served: people = 0 people size 100 people
        "People served"
        {FIXTURE}
    flow serve: waiting -> served at rate while state is "open"
        {FIXTURE}
    event close once when t >= 5 h:
        "The shop closes."
        {FIXTURE}
        state = "closed"
    status failed when state is "closed"
        "Closed"
    status ok
        "Open"
    output still_waiting: people = waiting
        "People still waiting"
        level
        {FIXTURE}

guard:
    "The guard of the shop."
    {FIXTURE}
    role operator
    sees shop.state
    event decide once when t >= 6 h:
        "The guard decides."
        {FIXTURE}
        choice
        reopen 0.5:
            "The guard opens the shop again."
            shop.state = "open"
        keep else:
            "The guard keeps the shop closed."

output served_total: people = shop.served
    "People served"
    {FIXTURE}

output harm: people
    "Harm"
    unestimated "No source gives it."
    {FIXTURE}

options "Rate":
    "Fast":
        "Fast service."
        shop.rate = 2 people/h
            {FIXTURE}
    "Slow":
        "Slow service."

options "Hours":
    "Long":
        "Long hours."
    "Short":
        "Short hours."

runs:
    fast = "Fast" + "Long"
    slow = "Slow" + "Long" versus fast
"""

# A local unit of time of the shop, beside the prelude's.
SHIFT_HOURS = 8
SHOP_UNITS = {
    'shift': {'kind': 'time', 'dimensions': {'time': 1}, 'scale': SHIFT_HOURS, 'description': 'A work shift.'}
}

CHAIN = """\
scenario "A chain of shops"
    summary "The shops of a chain. A synthetic fixture for tests only."
    horizon 48 h
    scope "Fixture"
use parts
"""

PARTS = f"""\
shop:
    "A shop."
    {FIXTURE}
    role operator
    input rate: people/h = 1 people/h in 0.1 people/h to 10 people/h
        "Service rate"
        {FIXTURE}
    var waiting: people = 10 people size 100 people
        "People waiting"
        {FIXTURE}
    var served: people = 0 people size 100 people
        "People served"
        {FIXTURE}
    flow serve: waiting -> served at rate
        {FIXTURE}

output served_total: people = shop.served
    "People served"
    {FIXTURE}
"""

# The variants of the chain, by name: (the text of the title as the file writes it, the file).
VARIANTS = {
    'east': (
        'The east shop',
        f"""\
variant "The east shop"
    summary "The shop in the east. A synthetic fixture for tests only."

change shop:
    rate = 2 people/h
        {FIXTURE}
""",
    ),
    'west': (
        'The west shop, which\n    serves the west',
        """\
variant "The west shop, which
    serves the west"
""",
    ),
}


def write(folder, files):
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return folder


def write_shop(folder):
    return write(folder, {'model.scn': SHOP, 'units.json': json.dumps(SHOP_UNITS)})


def write_chain(folder):
    files = {'model.scn': CHAIN, 'parts.scn': PARTS}
    files.update({f'variants/{name}/model.scn': text for name, (_, text) in VARIANTS.items()})
    return write(folder, files)


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    """The two packages, written once for the tests that only read them, and the shop's model."""
    base = tmp_path_factory.mktemp('packages')
    shop, chain = write_shop(base / 'shop'), write_chain(base / 'chain')
    return SimpleNamespace(shop=shop, chain=chain, model=common.load(common.one_target(str(shop))))


@pytest.fixture
def shop(tmp_path):
    """A shop of its own, which a test can change."""
    return write_shop(tmp_path / 'shop')


def refused(call, *args, **kwargs):
    """The message of the UsageError of a call."""
    with pytest.raises(common.UsageError) as raised:
        call(*args, **kwargs)
    return str(raised.value)


def diagnostics_of(call, *args, **kwargs):
    """The diagnostics of the Failed of a call."""
    with pytest.raises(common.Failed) as raised:
        call(*args, **kwargs)
    return raised.value.diagnostics


# --- Targets --------------------------------------------------------------------------------------


def test_a_package_its_file_and_the_current_folder_name_one_model(built, monkeypatch):
    folder = built.shop
    expected = [common.Target(folder, folder / 'model.scn', 'shop', None, ())]
    assert common.targets(str(folder)) == expected
    assert common.targets(str(folder / 'model.scn')) == expected
    monkeypatch.chdir(folder)
    # The current folder is named by its own name, not by an empty one.
    assert common.targets() == expected
    assert common.targets('model.scn') == expected
    monkeypatch.chdir(folder.parent)
    assert common.one_target('shop') == expected[0]


def test_a_package_with_variants_runs_as_each_variant(built, monkeypatch):
    folder = built.chain
    found = common.targets(str(folder))
    assert [item.name for item in found] == ['chain:east', 'chain:west']
    assert [item.entry for item in found] == [paths.entry(folder / 'variants' / name) for name in VARIANTS]
    assert all(item.package == folder and item.variants == ('east', 'west') for item in found)
    assert common.targets(str(folder / 'model.scn')) == found
    assert common.targets(str(folder), 'west') == [found[1]]
    # A variant's folder, its file and the current folder in it name that variant.
    assert common.one_target(str(folder / 'variants' / 'east')) == found[0]
    assert common.one_target(str(folder / 'variants' / 'east' / 'model.scn'), 'east') == found[0]
    monkeypatch.chdir(folder / 'variants' / 'west')
    assert common.one_target() == found[1]


def test_several_variants_without_one_list_each_name_and_title(built):
    message = refused(common.one_target, str(built.chain))
    for name, (title, _) in VARIANTS.items():
        # A title that runs over several lines reads as one line.
        assert f'{name}  {" ".join(title.split())}' in message


def test_an_unknown_variant_gives_the_closest_names(built):
    message = refused(common.targets, str(built.chain), 'est')
    assert 'est' in message and 'east' in message
    # A package without variants, and a variant's folder with another variant, are refused too.
    assert 'east' in refused(common.targets, str(built.shop), 'east')
    assert 'west' in refused(common.targets, str(built.chain / 'variants' / 'east'), 'west')


def test_what_is_no_target_is_refused(built, tmp_path):
    (tmp_path / 'empty').mkdir()
    for text in (
        built.chain / 'parts.scn',  # a module of a package
        tmp_path / 'empty',  # a folder without model.scn
        built.shop / 'units.json',  # another file
        tmp_path / 'missing',
    ):
        assert common.WHAT in refused(common.targets, str(text))


def test_each_target_loads_its_own_model(built):
    for item in common.targets(str(built.chain)):
        model = common.load(item)
        assert paths.names_of(model.origin) == tuple(item.name.split(':'))
        assert Path(model.origin) == item.entry


# --- Loading ------------------------------------------------------------------------------------


def test_a_model_that_does_not_compile_fails_with_its_file_and_line(shop):
    entry = shop / 'model.scn'
    entry.write_text(SHOP + 'not a declaration\n', encoding='utf-8')
    (item,) = diagnostics_of(common.load, common.one_target(str(shop)))
    line = len(SHOP.splitlines()) + 1
    assert (Path(item['file']), item['line']) == (entry, line)
    assert common.located(item, shop.parent).startswith(f'{Path("shop", "model.scn")}:{line}:')


@pytest.mark.parametrize(
    'text, code',
    [
        # A key twice and NaN: the engine's own reader refuses them (napkin.model.load_json).
        ('{"shift": {}, "shift": {}}', 'source'),
        ('{"shift": {"dimensions": {"time": 1}, "scale": NaN}}', 'source'),
        # JSON that is not valid: the engine gives no file, so the diagnostic finds it.
        ('{"shift": ', 'source'),
    ],
)
def test_a_file_of_the_model_that_cannot_be_read_fails_with_that_file(shop, text, code):
    (shop / 'units.json').write_text(text, encoding='utf-8')
    (item,) = diagnostics_of(common.load, common.one_target(str(shop)))
    assert (Path(item['file']), item['code']) == (shop / 'units.json', code)


def test_a_file_that_is_not_text_or_not_there_fails_with_that_file(shop, tmp_path):
    entry = shop / 'model.scn'
    entry.write_bytes(SHOP.encode('utf-8') + b'# \xff\n')
    (item,) = diagnostics_of(common.load, common.one_target(str(shop)))
    assert Path(item['file']) == entry
    missing = common.Target(tmp_path, tmp_path / 'gone' / 'model.scn', 'gone', None, ())
    (item,) = diagnostics_of(common.load, missing)
    assert Path(item['file']) == missing.entry


def test_a_model_checked_for_some_runs_says_so(built):
    assert common.scope_note(built.model) is None
    scoped = common.load(common.one_target(str(built.shop)), runs=['fast'])
    assert scoped.admission_runs == ('fast',)
    note = common.scope_note(scoped)
    assert 'fast' in note and 'slow' not in note


# --- The runs -------------------------------------------------------------------------------------

# The shop with four runs: `fast`, which `slow` and `short` are compared with, and `late`, which is
# compared with none and has a text of its own.
RUNS_SHOP = SHOP.replace(
    '    slow = "Slow" + "Long" versus fast\n',
    '    slow = "Slow" + "Long" versus fast\n'
    '    late = "Slow" + "Short"\n'
    '        "Slow service in short hours"\n'
    '    short = "Fast" + "Short" versus fast\n',
)
# The shop with its options and no runs, which the engine refuses.
NO_RUNS_SHOP = SHOP[: SHOP.index('runs:')]

# The relay: the chain's parts, a group of options and one run in its main file. Its variant `double`
# adds a run that is compared with the main file's; its variant `plain` adds none.
RELAY = f"""\
scenario "A relay"
    summary "A relay of shops. A synthetic fixture for tests only."
    horizon 48 h
    scope "Fixture"
use parts

options "Rate":
    "Base rate":
        "The rate as the file gives it."
    "Double rate":
        "Twice the rate."
        shop.rate = 2 people/h
            {FIXTURE}

runs:
    single = "Base rate"
"""
RELAY_VARIANTS = {
    'double': """\
variant "The relay with a double rate"
    summary "The relay at twice the rate. A synthetic fixture for tests only."

runs:
    double = "Double rate" versus single
        "Twice the rate"
""",
    'plain': """\
variant "The relay as it is"
    summary "The relay. A synthetic fixture for tests only."
""",
}


@pytest.fixture(scope='module')
def runs_packages(tmp_path_factory):
    """The shop with four runs, the shop with no runs, and the relay with its variants."""
    base = tmp_path_factory.mktemp('runs')
    relay = {'model.scn': RELAY, 'parts.scn': PARTS}
    relay.update({f'variants/{name}/model.scn': text for name, text in RELAY_VARIANTS.items()})
    return SimpleNamespace(
        four=common.one_target(str(write(base / 'four', {'model.scn': RUNS_SHOP, 'units.json': '{}'}))),
        none=common.one_target(str(write(base / 'none', {'model.scn': NO_RUNS_SHOP, 'units.json': '{}'}))),
        relay={item.variant: item for item in common.targets(str(write(base / 'relay', relay)))},
    )


def comparisons(model, run):
    """The runs that a spread of `run` samples, by the compiled model (`spread.sampled_runs`)."""
    from napkin import spread

    return spread.sampled_runs(model, run)


def test_the_files_give_each_run_and_the_runs_that_it_is_compared_with(runs_packages):
    """`slow` and `short` name `fast` with `versus`, so each is compared with `fast`, and `fast` with
    both; `late` is compared with none. The compiled model has the same runs in the same order, and a
    run with its comparisons are the runs that its spread samples."""
    target = runs_packages.four
    declared = common.declared_runs(target)
    assert declared == {'fast': ('slow', 'short'), 'slow': ('fast',), 'late': (), 'short': ('fast',)}
    model = common.load(target)
    assert list(declared) == list(model.runs)
    for run, compared in declared.items():
        assert [name for name in declared if name == run or name in compared] == comparisons(model, run)


def test_a_variant_has_the_runs_of_its_main_file_then_its_own(runs_packages):
    """The variant `double` adds a run compared with the main file's run; `plain` adds none. Each is
    the variant's compiled model's own list of runs, with the runs of each spread."""
    relay = runs_packages.relay
    assert common.declared_runs(relay['double']) == {'single': ('double',), 'double': ('single',)}
    assert common.declared_runs(relay['plain']) == {'single': ()}
    for target in relay.values():
        model = common.load(target)
        declared = common.declared_runs(target)
        assert list(declared) == list(model.runs)
        for run, compared in declared.items():
            assert [name for name in declared if name == run or name in compared] == comparisons(model, run)


def test_a_model_with_no_runs_and_no_options_has_one_run_that_is_compared_with_none(built):
    for target in common.targets(str(built.chain)):
        model = common.load(target)
        assert len(model.runs) == 1
        assert common.declared_runs(target) == {name: () for name in model.runs}
        assert common.the_run(target) == next(iter(model.runs))


def test_the_runs_come_from_the_files_and_nothing_compiles(runs_packages, monkeypatch):
    from napkin.model.language import front

    def no_compile(*arguments, **keywords):
        raise AssertionError('the runs of the files need no compiled model')

    monkeypatch.setattr(front, 'compile_file', no_compile)
    monkeypatch.setattr(common, 'load', no_compile)
    target = runs_packages.four
    assert list(common.declared_runs(target)) == ['fast', 'slow', 'late', 'short']
    assert common.the_run(target, 'late') == 'late'
    assert common.check_runs(target, ['short', 'fast']) == ('short', 'fast')
    assert common.the_run(runs_packages.relay['plain']) == 'single'


def test_files_that_do_not_read_fail_as_the_model_does(shop):
    """A line that starts no declaration, and a file that is not UTF-8 text: the runs fail with the
    diagnostics of the model's own load, with its file and line."""
    target = common.one_target(str(shop))
    entry = shop / 'model.scn'
    for text in (SHOP.encode('utf-8') + b'not a declaration\n', SHOP.encode('utf-8') + b'# \xff\n'):
        entry.write_bytes(text)
        found = diagnostics_of(common.declared_runs, target)
        assert found == diagnostics_of(common.load, target)
        assert [Path(item['file']) for item in found] == [entry]
        assert diagnostics_of(common.the_run, target) == found
        assert diagnostics_of(common.check_runs, target, ['fast']) == found


def test_a_model_with_options_and_no_runs_fails_with_the_engines_diagnostics(runs_packages):
    target = runs_packages.none
    assert common.declared_runs(target) == {}
    expected = diagnostics_of(common.load, target)
    assert expected
    assert diagnostics_of(common.the_run, target) == expected
    assert diagnostics_of(common.the_run, target, 'fast') == expected
    assert diagnostics_of(common.check_runs, target, ['fast']) == expected


def test_several_runs_and_no_run_list_each_run_with_its_label(runs_packages):
    """The listing gives each run in the order of the model, with the label that the model gives it:
    its text, or its options."""
    target = runs_packages.four
    model = common.load(target)
    head, *rows = refused(common.the_run, target).splitlines()
    assert target.name in head and '--run' in head
    assert [row.split(None, 1) for row in rows] == [[name, run['name']] for name, run in model.runs.items()]
    assert all(row.startswith('  ') for row in rows)


def test_an_unknown_run_gives_the_closest_names(runs_packages):
    target = runs_packages.four
    message = refused(common.the_run, target, 'fats')
    assert 'fats' in message and 'fast' in message.split('fats', 1)[1]
    message = refused(common.check_runs, target, ['fast', 'shrot'])
    assert 'shrot' in message and 'short' in message.split('shrot', 1)[1]
    # A variant's run is no run of another variant.
    message = refused(common.the_run, runs_packages.relay['plain'], 'double')
    assert 'double' in message and 'relay:plain' in message


def test_check_runs_gives_each_run_once_in_the_order_given_and_reads_no_file_for_none(
    runs_packages, monkeypatch
):
    from napkin.model.language import front

    target = runs_packages.four
    assert common.check_runs(target, ['late', 'fast', 'late']) == ('late', 'fast')

    def no_read(*arguments, **keywords):
        raise AssertionError('no --run reads no file')

    monkeypatch.setattr(front, 'load', no_read)
    assert common.check_runs(target, []) == common.check_runs(target, None) == ()


# --- --set ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'text, value',
    [
        ('4', 4),
        ('-1.5e3', -1500.0),
        ('true', True),
        ('"two words"', 'two words'),
        ('"pert(48 h, 96 h, 200 h)"', 'pert(48 h, 96 h, 200 h)'),
        # A bare word is text.
        ('fast', 'fast'),
        ('slow-mode_2', 'slow-mode_2'),
    ],
)
def test_a_setting_is_strict_json_or_a_word(text, value):
    found = common.parse_set([f'shop.rate={text}'])
    assert found == {'shop.rate': value} and type(found['shop.rate']) is type(value)


@pytest.mark.parametrize(
    'items',
    [
        ['shop.rate=NaN'],
        ['shop.rate=Infinity'],
        ['shop.rate=-Infinity'],
        ['shop.rate=1e999'],
        ['shop.rate=[1, 1e999]'],
        ['shop.rate=1' + '0' * 400],
        ['shop.rate={"a": 1, "a": 2}'],
        # Neither JSON nor a word.
        ['shop.rate=4h'],
        ['shop.rate=two words'],
        ['shop.rate=_hidden'],
        ['shop.rate='],
        ['=4'],
        ['shop.rate'],
        ['shop.rate=1', 'shop.rate=2'],
    ],
)
def test_a_setting_that_is_neither_is_refused(items):
    refused(common.parse_set, items)


# --- --option -----------------------------------------------------------------------------------


def test_an_option_is_named_alone_or_with_its_group(built):
    model = built.model
    assert common.parse_options(model, ['Rate=Fast']) == ('Fast',)
    assert common.parse_options(model, ['Short', 'Rate=Slow']) == ('Short', 'Slow')
    assert common.parse_options(model, ['Fast', 'Rate=Fast']) == ('Fast',)
    assert common.parse_options(model, []) == ()
    # The options are what `model.combination` puts into a run.
    combined = model.combination('fast', common.parse_options(model, ['Short']))
    assert combined.runs['fast']['options'] == ('Fast', 'Short')


def test_an_option_that_names_nothing_gives_the_closest_names(built):
    model = built.model
    assert 'Fast' in refused(common.parse_options, model, ['Fats'])
    assert 'Fast' in refused(common.parse_options, model, ['Rate=Fats'])
    assert 'Rate' in refused(common.parse_options, model, ['Rat=Fast'])
    # An option of another group.
    refused(common.parse_options, model, ['Hours=Fast'])


def test_two_options_of_one_group_are_refused(built):
    message = refused(common.parse_options, built.model, ['Fast', 'Slow'])
    assert 'Fast' in message and 'Slow' in message


def test_an_option_of_two_groups_needs_its_group():
    # The compiler refuses an option name in two groups, so a menu alone stands for such a model.
    model = SimpleNamespace(menu={'A': {'Same': ''}, 'B': {'Same': '', 'Other': ''}})
    message = refused(common.parse_options, model, ['Same'])
    assert 'A' in message and 'B' in message
    assert common.parse_options(model, ['B=Same']) == ('Same',)
    refused(common.parse_options, model, ['A=Same', 'B=Other', 'B=Same'])


# --- --edits ------------------------------------------------------------------------------------


def edits_file(tmp_path, doc):
    path = tmp_path / 'edits.json'
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding='utf-8')
    return path


def test_no_file_and_no_setting_is_no_edit_document(built):
    assert common.read_edits(built.model, None, {}) is None
    assert common.read_edits(built.model, None, None) is None


def test_a_setting_takes_the_place_of_the_files_entry(built, tmp_path):
    runs = {'slow': {'shop.rate': 0.5}}
    path = edits_file(tmp_path, {'set': {'shop.rate': 3, 'shop.other': 1}, 'runs': runs})
    doc = common.read_edits(built.model, path, {'shop.rate': 4})
    assert doc['set'] == {'shop.rate': 4, 'shop.other': 1} and doc['runs'] == runs


def test_a_document_without_its_model_takes_this_model(built, tmp_path):
    model = built.model
    path = edits_file(tmp_path, {'set': {'shop.rate': 3}})
    doc = common.read_edits(model, path, {})
    version = json.loads(EDITS_SCHEMA.read_text(encoding='utf-8'))['properties']['schema_version']['const']
    assert (doc['schema_version'], doc['model_hash']) == (version, model.model_hash)
    assert evaluate_study(model, doc, runs=['fast']).admissible
    only_set = common.read_edits(model, None, {'shop.rate': 3})
    assert only_set == doc


def test_a_document_of_another_model_keeps_its_hash_and_is_refused(built, tmp_path):
    model = built.model
    other = '0' * 64
    assert other != model.model_hash
    doc = common.read_edits(model, edits_file(tmp_path, {'model_hash': other}), {'shop.rate': 3})
    assert doc['model_hash'] == other
    study = evaluate_study(model, doc, runs=['fast'])
    assert not study.admissible and 'model_hash' in {item['code'] for item in study.diagnostics}


@pytest.mark.parametrize(
    'text',
    [
        '[1, 2]',
        '{"set": {"shop.rate": 1, "shop.rate": 2}}',
        '{"set": {"shop.rate": NaN}}',
        '{"set": ',
        '{"set": 3}',
    ],
)
def test_an_edit_file_that_cannot_be_read_fails_with_the_file(built, tmp_path, text):
    path = edits_file(tmp_path, text)
    (item,) = diagnostics_of(common.read_edits, built.model, path, {'shop.rate': 4})
    assert Path(item['file']) == path
    (item,) = diagnostics_of(common.read_edits, built.model, tmp_path / 'missing.json', {})
    assert Path(item['file']) == tmp_path / 'missing.json'


# --- --at -------------------------------------------------------------------------------------------


def scale_of(name):
    """The scale of a unit in execution units, from the unit tables themselves."""
    table = {**json.loads(PRELUDE.read_text(encoding='utf-8')), **SHOP_UNITS}
    return table[name]['scale']


def test_each_time_is_converted_by_the_units_of_the_model(built):
    found = common.parse_times(built.model, '7days, 1.5weeks,24h,2shift')
    expected = sorted(
        {24 * scale_of('h'), 7 * scale_of('days'), 1.5 * scale_of('weeks'), 2 * scale_of('shift')}
    )
    assert [t for _, t in found] == expected
    assert [name for name, _ in found] == [repr(float(t)) for t in expected]
    # One time once: 24 h and a day are one point.
    assert common.parse_times(built.model, '24h,1day') == [(repr(24.0 * scale_of('h')), 24.0 * scale_of('h'))]
    assert len(common.parse_times(built.model, '1day', many=False)) == 1


def test_the_points_are_the_names_that_the_report_gives(built):
    found = common.parse_times(built.model, '1h,2.5days,1week')
    report = sample_result(evaluate_study(built.model, runs=['fast']), [t for _, t in found])
    assert set(report['runs']['fast']['reporting_points']) == {name for name, _ in found} | {'final'}
    for name, t in found:
        assert report['runs']['fast']['reporting_points'][name]['t'] == t


def test_a_time_lies_within_the_run(built):
    horizon = built.model.time['horizon']
    assert common.parse_times(built.model, f'{horizon}h, 0h') == [
        ('0.0', 0.0),
        (repr(float(horizon)), horizon),
    ]
    refused(common.parse_times, built.model, f'{horizon + 1}h')
    refused(common.parse_times, built.model, '-1h')


@pytest.mark.parametrize('text', ['24', '24h,', 'h', '3people', '2 tunings', '3 days 2'])
def test_a_time_without_a_unit_of_time_is_refused(built, text):
    refused(common.parse_times, built.model, text)


def test_one_time_is_one_time(built):
    refused(common.parse_times, built.model, '1h,2h', many=False)


def test_an_unknown_unit_of_time_gives_the_closest_units(built):
    assert 'days' in refused(common.parse_times, built.model, '3dayz')
    assert 'shift' in refused(common.parse_times, built.model, '3shifs')


# --- --exceed -----------------------------------------------------------------------------------


def test_an_exceedance_names_an_output_and_a_number(built):
    outputs = built.model.outputs
    name = next(iter(outputs))
    found = common.parse_exceed(built.model, [f'{name}=9.9e6', f'{name} = -2', f'{outputs[name]}=1'])
    assert found == [(outputs[name], 9.9e6), (outputs[name], -2.0), (outputs[name], 1.0)]
    assert common.parse_exceed(built.model, []) == []


@pytest.mark.parametrize(
    'item', ['served_totl=1', 'served_total=inf', 'served_total=nan', 'served_total=a', 'served_total']
)
def test_an_exceedance_of_no_output_or_no_number_is_refused(built, item):
    message = refused(common.parse_exceed, built.model, [item])
    if item.startswith('served_totl'):
        assert 'served_total' in message


# --- The run store ------------------------------------------------------------------------------


@pytest.fixture
def store_state(monkeypatch):
    """The run store's setting, restored after the test."""
    from napkin import store

    monkeypatch.setattr(store, '_active', dict(store._active))
    return store


def test_the_store_follows_the_setting(store_state, monkeypatch, tmp_path):
    monkeypatch.setenv('NAPKIN_STORE', str(tmp_path / 'runs'))
    assert common.use_store() == tmp_path / 'runs' == store_state.current()
    assert common.use_store(False) is None and store_state.current() is None
    monkeypatch.setenv('NAPKIN_STORE', 'off')
    assert common.use_store() is None and store_state.current() is None


# --- Diagnostics and numbers --------------------------------------------------------------------


def test_a_diagnostic_is_one_line_with_its_place(tmp_path):
    inside = str(tmp_path / 'pkg' / 'model.scn')
    item = {
        'file': inside,
        'line': 3,
        'column': 5,
        'severity': 'error',
        'message': 'bad\nunit',
        'path': 'a/b',
    }
    shown = Path('pkg', 'model.scn')
    assert common.located(item, tmp_path) == f'{shown}:3:5: error: bad unit (a/b)'
    assert common.located({**item, 'column': None}, tmp_path) == f'{shown}:3: error: bad unit (a/b)'
    assert common.located({**item, 'line': 0}, tmp_path) == f'{shown}: error: bad unit (a/b)'
    # A file outside the folder keeps its whole path.
    assert common.located(item, tmp_path / 'other').startswith(f'{inside}:3:5: ')
    # No file: the severity, the message and the place; and the run of a study's diagnostic.
    plain = {'severity': 'warning', 'message': 'late', 'path': 'runs/a', 'run': 'a'}
    assert common.located(plain) == 'warning: late (runs/a; run a)'
    assert common.located({'message': 'late'}) == 'error: late'
    stream = io.StringIO()
    common.show_diagnostics([item, plain], stream, cwd=tmp_path)
    assert stream.getvalue().splitlines() == [common.located(item, tmp_path), common.located(plain)]


def test_a_number_has_four_significant_figures():
    for value in (1.23456, -98765.4321, 0.000123456, 3.0, 2e11 / 3, 7e-5, 1.5e13, -4.4e-9):
        shown = common.number(value)
        assert math.isclose(float(shown), value, rel_tol=5e-4)
        assert ('e' in shown) == (not 1e-4 <= abs(value) < 1e12)
        assert len(shown.lstrip('-').replace('.', '').split('e')[0].strip('0')) <= 4
    assert [common.number(value) for value in (0, 0.0, None, True, 'text')] == [
        '0',
        '0',
        'None',
        'True',
        'text',
    ]


# --- JSON -------------------------------------------------------------------------------------------


@pytest.fixture(scope='module')
def played(built):
    """A report of a played run: the guard's decision takes a pick, the shop's event the model's
    choice; and the report of the other run."""
    model = built.model
    play = {
        'run': 'fast',
        'control': {'guard': 'reader'},
        'picks': [{'event': 'guard.decide', 'outcome': 'keep'}],
    }
    study = evaluate_study(model, runs=['fast'], play=play)
    assert study.admissible, study.diagnostics
    times = [t for _, t in common.parse_times(model, '1h,7h')]
    return SimpleNamespace(
        model=model,
        report=sample_result(study, times),
        other=sample_result(evaluate_study(model, runs=['slow'])),
        both=sample_result(evaluate_study(model, runs=['fast', 'slow'])),
    )


def test_the_compact_document_is_a_projection_of_the_report(played):
    report = played.report
    doc = common.compact(report)
    assert {key: doc[key] for key in report if key != 'runs'} == {
        key: value for key, value in report.items() if key != 'runs'
    }
    assert doc['admitted_runs'] is None
    assert doc['runs'].keys() == report['runs'].keys()
    for name, run in report['runs'].items():
        shown = doc['runs'][name]
        for key in ('label', 'options', 'horizon', 'outcomes'):
            assert shown[key] == run[key]
        assert shown['reporting_points'].keys() == run['reporting_points'].keys()
        for point, row in run['reporting_points'].items():
            assert shown['reporting_points'][point] == {key: row[key] for key in ('t', 'values', 'statuses')}
        fired = [entry for entry in run['trace'] if entry['outcome'] is not None]
        assert len(shown['events']) == len(fired)
        for event, entry in zip(shown['events'], fired):
            assert (event['t'], event['thing'], event['event'], event['outcome'], event['text']) == (
                entry['t'],
                entry['entity'],
                entry['event'],
                entry['outcome'],
                entry['label'],
            )
            assert event.get('picked') == entry['picked']
            assert ('picked' in event) == (entry['picked'] is not None)
    # The fixture has what the projection must keep: a picked event and one that the model chose,
    # and an outcome that is not estimated.
    events = doc['runs']['fast']['events']
    assert {event.get('picked') for event in events} == {'reader', None}
    assert 'unestimated' in doc['runs']['fast']['reporting_points']['final']['statuses'].values()
    stream = io.StringIO()
    common.write_json(doc, stream)
    assert json.loads(stream.getvalue()) == doc


def test_full_adds_exactly_the_trace_the_evidence_and_the_index(played):
    report, model = played.report, played.model
    doc = common.compact(report)
    full = common.compact(report, full=True, index=model.index, admitted=('fast',))
    assert full.keys() - doc.keys() == {'index'} and full['index'] == thaw(model.index)
    assert full['admitted_runs'] == ['fast']
    for name, run in report['runs'].items():
        assert full['runs'][name].keys() - doc['runs'][name].keys() == {'trace', 'evidence'}
        assert (full['runs'][name]['trace'], full['runs'][name]['evidence']) == (
            run['trace'],
            run['evidence'],
        )
        assert {key: full['runs'][name][key] for key in doc['runs'][name]} == doc['runs'][name]


def test_reports_of_one_run_each_merge_into_the_report_of_both(played):
    other, both = played.other, played.both
    fast = sample_result(evaluate_study(played.model, runs=['fast']))
    doc = common.merged([fast, other])
    assert doc['runs'] == both['runs']
    assert {key: doc[key] for key in both if key not in ('runs', 'diagnostics')} == {
        key: value for key, value in both.items() if key not in ('runs', 'diagnostics')
    }
    assert all(item in doc['diagnostics'] for item in both['diagnostics'])
    assert len(doc['diagnostics']) == len({json.dumps(item, sort_keys=True) for item in doc['diagnostics']})


def test_a_rejected_report_rejects_the_merge(played, tmp_path):
    model = played.model
    stale = common.read_edits(model, edits_file(tmp_path, {'model_hash': '0' * 64}), {})
    rejected = sample_result(evaluate_study(model, stale, runs=['slow']))
    assert not rejected['admissible']
    doc = common.merged([played.report, rejected], edits=stale)
    assert (doc['admissible'], doc['status'], doc['runs']) == (False, rejected['status'], {})
    assert doc['effective_edits'] == stale
    # Without the document, reports of other edits do not merge.
    with pytest.raises(ValueError):
        common.merged([played.report, rejected])


def test_reports_of_other_models_or_of_one_run_twice_do_not_merge(played, built):
    chain = common.load(common.one_target(str(built.chain), 'east'))
    with pytest.raises(ValueError):
        common.merged([played.other, sample_result(evaluate_study(chain))])
    with pytest.raises(ValueError):
        common.merged([played.other, played.other])
    with pytest.raises(ValueError):
        common.merged([])


def test_json_is_one_finite_line():
    doc = {'a': [1, 2.5, None, 'é'], 'b': {'c': True}}
    stream = io.StringIO()
    common.write_json(doc, stream)
    assert stream.getvalue() == json.dumps(doc, separators=(',', ':')) + '\n'
    with pytest.raises(ValueError):
        common.write_json({'a': math.nan}, io.StringIO())


# --- The command line -----------------------------------------------------------------------------


def test_help_lists_every_command_and_version_prints_the_version(capsys):
    import napkin

    with pytest.raises(SystemExit) as done:
        cli.main(['--help'])
    out = capsys.readouterr().out
    assert done.value.code == 0
    for name, module in commands.modules().items():
        assert f'  {name} ' in out and module.SUMMARY in out
    with pytest.raises(SystemExit) as done:
        cli.main(['--version'])
    assert done.value.code == 0 and capsys.readouterr().out.strip() == napkin.__version__
    with pytest.raises(SystemExit) as done:
        cli.main([])
    assert done.value.code == 2


@pytest.mark.parametrize('name', commands.NAMES)
def test_each_command_has_help(name, capsys):
    with pytest.raises(SystemExit) as done:
        cli.main([name, '--help'])
    assert done.value.code == 0 and f'usage: napkin {name}' in capsys.readouterr().out


# The spec's flags of each command (§2), as a shell writes them, and what each one gives.
FLAGS = {
    'compile': (
        '--variant v --inputs --outputs --json pkg',
        {'variant': 'v', 'inputs': True, 'outputs': True, 'json': True, 'target': 'pkg'},
    ),
    'run': (
        '--variant v --run a --run b --option "Delayed response" --option "Response=Early response" '
        '--set x.y=4 --set plan=fast --at 24h,7days --edits e.json --events --json full --no-store pkg',
        {
            'variant': 'v',
            'run': ['a', 'b'],
            'option': ['Delayed response', 'Response=Early response'],
            'set': ['x.y=4', 'plan=fast'],
            'at': '24h,7days',
            'edits': Path('e.json'),
            'events': True,
            'json': 'full',
            'no_store': True,
            'target': 'pkg',
        },
    ),
    'play': (
        '--variant v --run a --control operator --control guard.first --option O --set x.y=1 '
        '--edits e.json --picks p.json --save s.json --json pkg',
        {
            'variant': 'v',
            'run': 'a',
            'control': ['operator', 'guard.first'],
            'option': ['O'],
            'set': ['x.y=1'],
            'edits': Path('e.json'),
            'picks': Path('p.json'),
            'save': Path('s.json'),
            'json': True,
            'target': 'pkg',
        },
    ),
    'sample': (
        '--variant v --run a --option O --set x.y=1 --samples 2000 --seed 7 --jobs 3 --at 24h '
        '--exceed loss=9.9e6 --exceed loss=1 --edits e.json --json pkg',
        {
            'variant': 'v',
            'run': 'a',
            'option': ['O'],
            'set': ['x.y=1'],
            'samples': 2000,
            'seed': 7,
            'jobs': 3,
            'at': '24h',
            'exceed': ['loss=9.9e6', 'loss=1'],
            'edits': Path('e.json'),
            'json': True,
            'target': 'pkg',
        },
    ),
    'derivatives': (
        '--variant v --run a --input x.y --input z --json pkg',
        {'variant': 'v', 'run': 'a', 'input': ['x.y', 'z'], 'json': True, 'target': 'pkg'},
    ),
    'draw': (
        '--variant v --run a --style s.toml -o j.svg --latex j.tex pkg',
        {
            'variant': 'v',
            'run': 'a',
            'style': Path('s.toml'),
            'output': Path('j.svg'),
            'latex': Path('j.tex'),
            'target': 'pkg',
        },
    ),
    'new': (
        '--title "A title" --variants east,west demo',
        {'title': 'A title', 'variants': 'east,west', 'dir': Path('demo')},
    ),
    'fmt': ('--check a.scn pkg', {'check': True, 'paths': [Path('a.scn'), Path('pkg')]}),
}

# What each command gives when only its required flags are given.
DEFAULTS = {
    'compile': ('', {'variant': None, 'inputs': False, 'outputs': False, 'json': False, 'target': '.'}),
    'run': (
        '',
        {'run': [], 'option': [], 'set': [], 'at': None, 'edits': None, 'events': False, 'json': None}
        | {'no_store': False, 'target': '.'},
    ),
    'play': (
        '--control c',
        {'run': None, 'option': [], 'set': [], 'picks': None, 'save': None, 'json': False},
    ),
    'sample': ('--run a', {'samples': 200, 'seed': 0, 'jobs': None, 'at': None, 'exceed': [], 'json': False}),
    'derivatives': ('', {'variant': None, 'run': None, 'input': [], 'json': False, 'target': '.'}),
    'draw': ('', {'run': None, 'style': None, 'output': None, 'latex': None, 'target': '.'}),
    'new': ('demo', {'title': None, 'variants': None}),
    'fmt': ('', {'check': False, 'paths': []}),
}


@pytest.mark.parametrize('name', commands.NAMES)
def test_each_command_takes_the_flags_of_the_spec(name):
    for line, expected in (FLAGS[name], DEFAULTS[name]):
        args = cli.parse([name, *shlex.split(line)])
        assert args.command == name and args.handler is commands.modules()[name].main
        assert {key: getattr(args, key) for key in expected} == expected


@pytest.mark.parametrize(
    'argv',
    [
        ['play'],  # --control is required
        ['new'],  # DIR is required
        ['sample', '--samples', '0'],
        ['sample', '--jobs', 'two'],
        ['sample', '--seed', '-1'],
        ['run', '--json=all'],
        ['run', '--jso', 'full'],  # no abbreviations
        ['compile', 'a', 'b'],
    ],
)
def test_a_command_line_that_the_spec_does_not_give_is_refused(argv, capsys):
    with pytest.raises(SystemExit) as done:
        cli.parse(argv)
    assert done.value.code == 2 and 'usage: napkin' in capsys.readouterr().err


@pytest.mark.parametrize(
    'argv, json_form, target',
    [
        (['run', '--json', 'full', 'pkg'], 'full', 'pkg'),
        (['run', '--json', 'pkg'], 'compact', 'pkg'),
        (['run', 'pkg', '--json'], 'compact', 'pkg'),
        (['run', '--json', 'full'], 'full', '.'),
        (['run', '--json=full', 'pkg'], 'full', 'pkg'),
        (['run', '--json', '--events', 'pkg'], 'compact', 'pkg'),
        # After `--` a word is the TARGET.
        (['run', '--json', '--', '--json'], 'compact', '--json'),
    ],
)
def test_the_json_flag_of_run_never_takes_the_target(argv, json_form, target):
    args = cli.parse(argv)
    assert (args.json, args.target) == (json_form, target)


def test_the_json_flag_of_the_other_commands_is_a_plain_flag():
    for name in ('compile', 'sample', 'play'):
        args = cli.parse([name, *shlex.split(DEFAULTS[name][0]), '--json', 'full'])
        assert (args.json, args.target) == (True, 'full')


def test_main_gives_the_exit_code_of_each_ending(monkeypatch, capsys, tmp_path):
    module = commands.modules()['run']
    item = {'file': str(tmp_path / 'model.scn'), 'line': 2, 'severity': 'error', 'message': 'wrong'}

    def ending(error):
        def main(args):
            raise error

        return main

    monkeypatch.setattr(module, 'main', ending(common.UsageError('no such run')))
    assert cli.main(['run']) == 2
    err = capsys.readouterr().err
    assert 'usage: napkin run' in err and 'napkin run: error: no such run' in err
    monkeypatch.setattr(module, 'main', ending(common.Failed([item], 'It does not compile.')))
    assert cli.main(['run']) == 1
    assert capsys.readouterr().err.splitlines() == ['It does not compile.', common.located(item)]
    monkeypatch.setattr(module, 'main', lambda args: 0)
    assert cli.main(['run']) == 0
    # Nothing else is caught.
    monkeypatch.setattr(module, 'main', ending(RuntimeError('a bug')))
    with pytest.raises(RuntimeError):
        cli.main(['run'])


def child(*argv):
    """The output of `python -B ARGV` in a new process at the root of the checkout, which must exit 0."""
    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    done = subprocess.run(
        [sys.executable, '-B', *argv],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_python_m_napkin_is_the_command():
    out = child('-m', 'napkin', '--help')
    assert out.startswith('usage: napkin') and all(f'  {name} ' in out for name in commands.NAMES)


def test_help_loads_no_engine_numpy_or_scipy():
    # Each help, in one process: after each, no module of the engine, the model, the run store, numpy
    # or scipy is loaded.
    code = f"""
import json, sys
from napkin import cli
heavy = ('numpy', 'scipy', 'napkin.engine', 'napkin.model', 'napkin.store', 'napkin.spread', 'napkin.draw')
found = {{}}
for argv in [['--help'], ['--version'], *[[name, '--help'] for name in {list(commands.NAMES)!r}]]:
    try:
        cli.main(argv)
    except SystemExit:
        pass
    found[' '.join(argv)] = sorted(m for m in sys.modules if any(m == h or m.startswith(h + '.') for h in heavy))
print(json.dumps(found))
"""
    found = json.loads(child('-c', code).splitlines()[-1])
    assert found and all(loaded == [] for loaded in found.values()), found


# --- napkin compile -------------------------------------------------------------------------------

# The sections of compile, run and fmt share `napkin_call`, which runs a command line in this
# process, and `assumption_record`, an assumption of a folder's evidence as the library reads it.


@pytest.fixture
def napkin_call(monkeypatch, capsys):
    """`napkin ARGV` in this process: its exit code, its output and its errors. The run store keeps
    the test's setting afterwards and starts no helper process."""
    from napkin import store

    monkeypatch.setattr(store, '_active', dict(store._active))
    monkeypatch.setattr(store, 'cores', lambda: 1)

    def call(*argv):
        code = cli.main([str(word) for word in argv])
        found = capsys.readouterr()
        return SimpleNamespace(code=code, out=found.out, err=found.err)

    return call


def assumption_record(identifier):
    return {
        'title': 'A fixture',
        'id': identifier,
        'statement': 'A statement of a fixture.',
        'rationale': 'A fixture.',
        'status': 'selected',
        'origin': 'author',
        'review': {'status': 'unreviewed'},
        'supports': [],
        'evidence_needed': 'None: a fixture.',
        'decided': {'by': 'fixture', 'date': '2026-11-09'},
    }


def test_compile_compiles_every_variant_and_names_each_variant_run_and_option(built, napkin_call):
    done = napkin_call('compile', built.chain, '--json')
    assert done.code == 0, done.err
    doc = json.loads(done.out)
    assert doc['package'] == 'chain' and list(doc['models']) == ['chain:east', 'chain:west']
    for target in common.targets(str(built.chain)):
        model = common.load(target)
        item = doc['models'][target.name]
        assert item['admissible'] and item['diagnostics'] == []
        assert list(item['runs']) == list(model.runs) and item['options'] == thaw(model.menu)
    text = napkin_call('compile', built.chain)
    assert text.code == 0 and text.err == ''
    assert all(
        name in text.out for name in [*VARIANTS, *common.load(common.targets(str(built.chain))[0]).runs]
    )
    assert f'{len(VARIANTS)} variants compiled' in text.out
    # The shop: each run, each group and each option by its real name, and each actor's choices.
    model = built.model
    shop = napkin_call('compile', built.shop)
    assert shop.code == 0
    assert all(run in shop.out for run in model.runs)
    for group, options in model.menu.items():
        assert f'{group}: ' + ', '.join(f'"{option}"' for option in options) in shop.out
    from napkin.model.views import actors

    for actor in actors(model):
        assert actor['name'] in shop.out
        for choice in actor['choices']:
            assert choice['event'] in shop.out and all(o['name'] in shop.out for o in choice['outcomes'])


def test_compile_lists_every_input_and_output(built, napkin_call):
    model = built.model
    done = napkin_call('compile', built.shop, '--inputs', '--outputs')
    assert done.code == 0
    listed = done.out.split('inputs (')[1]
    assert all(f'    {name} ' in listed for name in [*model.inputs, *model.outputs])
    doc = json.loads(napkin_call('compile', built.shop, '--inputs', '--outputs', '--json').out)
    (item,) = doc['models'].values()
    assert list(item['inputs']) == list(model.inputs) and list(item['outputs']) == list(model.outputs)
    for name, found in item['inputs'].items():
        given = model.inputs[name]
        assert (found['unit'], found['value'], found['range']) == (
            given['unit'],
            thaw(given['value']),
            thaw(given['range']),
        )
    # The outcomes of a report are the outputs that the listing names, with their units and statuses.
    outcomes = sample_result(evaluate_study(model, runs=['fast']))['runs']['fast']['outcomes']
    for found in item['outputs'].values():
        outcome = outcomes[found['outcome']]
        assert (found['unit'], found['status'], found['label']) == (
            outcome['unit'],
            outcome['status'],
            outcome['label'],
        )
    # Without the flags, the document has neither.
    (plain,) = json.loads(napkin_call('compile', built.shop, '--json').out)['models'].values()
    assert 'inputs' not in plain and 'outputs' not in plain


def test_compile_prints_the_package_and_its_title_and_json_holds_every_model(built, napkin_call):
    doc = json.loads(napkin_call('compile', built.shop, '--json').out)
    assert doc['schema_version'] == '0.0.1' and doc['package'] == 'shop'
    assert doc['title'] == built.model.scenario.title and doc['diagnostics'] == []
    assert list(doc['models']) == ['shop']
    # The title of a package with variants is its main file's; each variant's title follows it.
    chain = json.loads(napkin_call('compile', built.chain, '--json').out)
    for target in common.targets(str(built.chain)):
        title = common.load(target).scenario.title
        assert chain['models'][target.name]['title'] == title
        assert title.startswith(f'{chain["title"]}: ')
    assert napkin_call('compile', built.chain).out.startswith(f'chain  {chain["title"]}\n')


def test_compile_with_a_variant_compiles_that_variant(built, napkin_call):
    done = napkin_call('compile', built.chain, '--variant', 'west', '--json')
    assert done.code == 0 and list(json.loads(done.out)['models']) == ['chain:west']
    assert napkin_call('compile', built.chain / 'variants' / 'east', '--json').code == 0
    assert napkin_call('compile', built.chain, '--variant', 'north').code == 2


def test_compile_gives_the_place_of_each_diagnostic_and_the_models_that_compile(
    tmp_path, napkin_call, monkeypatch
):
    chain = write_chain(tmp_path / 'chain')
    west = chain / 'variants' / 'west' / 'model.scn'
    text = west.read_text(encoding='utf-8')
    west.write_text(text + 'not a declaration\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    done = napkin_call('compile', 'chain')
    assert done.code == 1
    line = len(text.splitlines()) + 1
    assert done.err.startswith(f'{Path("chain", "variants", "west", "model.scn")}:{line}:1: error: ')
    assert '1 of 2 variants compiled' in done.out
    doc = json.loads(napkin_call('compile', 'chain', '--json').out)
    assert doc['models']['chain:east']['admissible'] and not doc['models']['chain:west']['admissible']
    (item,) = doc['models']['chain:west']['diagnostics']
    assert (Path(item['file']).resolve(), item['line']) == (west.resolve(), line)
    # A model that does not compile prints only its diagnostics.
    shop = write_shop(tmp_path / 'shop')
    (shop / 'model.scn').write_text(SHOP + 'not a declaration\n', encoding='utf-8')
    alone = napkin_call('compile', 'shop')
    assert (alone.code, alone.out) == (1, '')
    assert alone.err.startswith(f'{Path("shop", "model.scn")}:{len(SHOP.splitlines()) + 1}:1: error: ')


@pytest.mark.parametrize(
    'where, text',
    [
        ('style.toml', '[layout]\nhid = []\n'),  # a key that the file does not read
        ('style.toml', '[layout\n'),  # not TOML
        ('style.toml', '[icon]\ntarget = ["nobody"]\n'),  # a name that the model does not declare
        ('variants/east/style.toml', '[icon]\nmoon = ["shop"]\n'),  # an icon that is not one
    ],
)
def test_compile_refuses_a_bad_stylesheet_with_its_file(tmp_path, napkin_call, monkeypatch, where, text):
    chain = write_chain(tmp_path / 'chain')
    (chain / where).write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    done = napkin_call('compile', 'chain')
    assert done.code == 1
    lines = done.err.splitlines()
    assert lines and all(line.startswith(str(Path('chain', where))) for line in lines)
    # Each model that reads the file names it; a variant's own file replaces its package's (D-22).
    doc = json.loads(napkin_call('compile', 'chain', '--json').out)
    readers = {'chain:east'} if where.startswith('variants/') else {'chain:east', 'chain:west'}
    assert {name for name, item in doc['models'].items() if item['diagnostics']} == readers
    assert all(item['admissible'] for item in doc['models'].values())
    # A good stylesheet passes.
    (chain / where).write_text('[layout]\nhide = ["shop"]\n', encoding='utf-8')
    assert napkin_call('compile', 'chain').code == 0


def test_compile_reports_an_unused_shared_record_at_its_file_and_line(tmp_path, napkin_call, monkeypatch):
    chain = write_chain(tmp_path / 'chain')
    east = chain / 'variants' / 'east' / 'model.scn'
    east.write_text(
        east.read_text(encoding='utf-8').replace(FIXTURE, '@assumption A-USED "The east shop assumes it."'),
        encoding='utf-8',
    )
    text = json.dumps([assumption_record('A-USED'), assumption_record('A-UNUSED')], indent=2)
    (chain / 'evidence').mkdir()
    (chain / 'evidence' / 'assumptions.json').write_text(text, encoding='utf-8')
    line = text.splitlines().index('    "id": "A-UNUSED",') + 1
    monkeypatch.chdir(tmp_path)
    done = napkin_call('compile', 'chain')
    assert done.code == 1
    (shown,) = done.err.splitlines()
    assert shown.startswith(f'{Path("chain", "evidence", "assumptions.json")}:{line}: error: ')
    assert 'A-UNUSED' in shown and 'A-USED' not in shown.replace('A-UNUSED', '')
    doc = json.loads(napkin_call('compile', 'chain', '--json').out)
    (item,) = doc['diagnostics']
    assert (Path(item['file']).name, item['line']) == ('assumptions.json', line)
    # One variant alone is no package: the check needs every variant.
    assert napkin_call('compile', 'chain', '--variant', 'east').code == 0


def test_compile_counts_each_sourced_and_assumed_value_once(tmp_path, napkin_call):
    chain = write_chain(tmp_path / 'chain')
    parts = chain / 'parts.scn'
    text = parts.read_text(encoding='utf-8')
    waiting = '"People waiting"\n        ' + FIXTURE
    served = '"People served"\n        ' + FIXTURE
    assert waiting in text and served in text
    # In the module that both variants read: one sourced value, and one value with a source applied
    # here and an assumption, which is both; and the east variant's own assumed value.
    text = text.replace(waiting, '"People waiting"\n        @source "A count of the people."')
    text = text.replace(
        served,
        '"People served"\n        @source_transfer "A count elsewhere."\n        @assumption "Assumed."',
    )
    parts.write_text(text, encoding='utf-8')
    east = chain / 'variants' / 'east' / 'model.scn'
    east.write_text(
        east.read_text(encoding='utf-8').replace(FIXTURE, '@assumption "The east shop assumes it."'),
        encoding='utf-8',
    )
    doc = json.loads(napkin_call('compile', chain, '--json').out)
    assert doc['evidence'] == {'sourced': 2, 'assumed': 2}
    assert 'evidence: 2 sourced values, 2 assumed' in napkin_call('compile', chain).out
    # The west variant alone reads the module only.
    west = json.loads(napkin_call('compile', chain, '--variant', 'west', '--json').out)
    assert west['evidence'] == {'sourced': 2, 'assumed': 1}


def compile_cases():
    """The command lines of `napkin compile` that the smoke test runs: each catalogue model that this
    session checks (a package, or a variant with --variant), each package whose variants it checks
    all, and each example."""
    from tests.helpers import ALL_SCENARIO_IDS, SCENARIO_IDS
    from tools import catalogue

    entries = catalogue.entries(ROOT)
    cases, chosen = [], {}
    for owner in SCENARIO_IDS:
        package, _, variant = owner.partition(':')
        folder = paths.package_of(entries[owner])
        cases.append(pytest.param([folder, *(['--variant', variant] if variant else [])], id=owner))
        chosen.setdefault(package, (folder, set()))[1].add(owner)
    for package, (folder, owners) in chosen.items():
        every = {owner for owner in ALL_SCENARIO_IDS if owner.partition(':')[0] == package}
        if any(':' in owner for owner in every) and owners == every:
            cases.append(pytest.param([folder], id=package))
    for entry in sorted((ROOT / 'examples').glob(f'*/{paths.ENTRY}')):
        cases.append(pytest.param([entry.parent], id=f'examples/{entry.parent.name}'))
    return cases


@pytest.mark.scenario_contract
@pytest.mark.parametrize('argv', compile_cases())
def test_compile_lists_each_catalogue_package_and_example(argv, napkin_call, monkeypatch):
    # A smoke test, not a frozen output. The catalogue's models come from the compiled models that the
    # other contracts share (`catalogue_model`), which `load_scenario` builds with every run checked, as
    # `common.load` does.
    from tests.helpers import catalogue_model
    from tools import catalogue

    entries, load = catalogue.entries(ROOT), common.load

    def shared(target, runs=None):
        if runs is None and entries.get(target.name) == target.entry:
            return catalogue_model(target.name)
        return load(target, runs)

    monkeypatch.setattr(common, 'load', shared)
    doc = json.loads(napkin_call('compile', *argv, '--json').out)
    assert doc['schema_version'] == '0.0.1' and doc['diagnostics'] == []
    targets = common.targets(str(argv[0]), argv[2] if len(argv) > 2 else None)
    assert list(doc['models']) == [target.name for target in targets]
    for target in targets:
        model, item = shared(target), doc['models'][target.name]
        assert item['admissible'] and item['diagnostics'] == [], item['diagnostics']
        assert list(item['runs']) == list(model.runs) and item['options'] == thaw(model.menu)
    counts = doc['evidence']
    assert counts['sourced'] >= 0 and counts['assumed'] >= 0
    done = napkin_call('compile', *argv)
    assert done.code == 0 and done.err == '', done.err
    for model in map(shared, targets):
        assert all(f'"{option}"' in done.out for options in model.menu.values() for option in options)


# --- napkin run -------------------------------------------------------------------------------------

# The hall: people enter at a rate while its door is open, so the people inside are the rate times
# the time, a closed form. Its bell rings at RING_HOURS. Two groups of options make two runs; the
# option "Wide" sets the rate.
RING_HOURS = 3
HALL = f"""\
scenario "A hall"
    summary "People enter a hall through its door. A synthetic fixture for tests only."
    horizon 10 h
    scope "Fixture"

hall:
    "A hall."
    {FIXTURE}
    input rate: people/h = 1 people/h in 0 people/h to 50 people/h
        "Entry rate"
        {FIXTURE}
    input door: "open" | "shut" = "open"
        "Door"
        {FIXTURE}
    var queue: people = 1000 people size 1000 people
        "People who wait outside"
        {FIXTURE}
    var inside: people = 0 people size 1000 people
        "People inside"
        {FIXTURE}
    var bell: "silent" | "rung" = "silent"
        "Bell"
        {FIXTURE}
    flow enter: queue -> inside at rate while door is "open"
        {FIXTURE}
    event ring once when t >= {RING_HOURS} h:
        "The bell rings."
        {FIXTURE}
        bell = "rung"
    output entered: people = inside
        "People inside"
        {FIXTURE}

output harm: people
    "Harm"
    unestimated "No source gives it."
    {FIXTURE}

options "Door":
    "Wide":
        "A wide door."
        hall.rate = 4 people/h
            {FIXTURE}
    "Narrow":
        "A narrow door."

options "Day":
    "Monday":
        "Monday."
    "Sunday":
        "Sunday."

runs:
    narrow = "Narrow" + "Monday"
    wide = "Wide" + "Sunday" versus narrow
"""
# The hall with a check before the run that the option "Wide" fails: the run `wide` and the
# combination of "Wide" with any run are refused.
CHECKED_HALL = HALL.replace(
    '    output entered:',
    f'    assert rate <= 2 people/h\n        "The door lets in 2 people in an hour at most."\n        {FIXTURE}\n'
    '    output entered:',
)
# The hall whose run `narrow` names the option "Wide" itself.
WIDE_HALL = HALL.replace('narrow = "Narrow" + "Monday"', 'narrow = "Wide" + "Monday"')


@pytest.fixture
def hall(tmp_path):
    return write(tmp_path / 'hall', {'model.scn': HALL})


def hall_model(folder, runs=None):
    return common.load(common.one_target(str(folder)), runs=runs)


def rate_of(model, run):
    """The rate of a run: the value of the option of the run that sets it, else the input's own."""
    item = model.inputs['hall.rate']
    found = [
        item['options'][option]['value'] for option in model.runs[run]['options'] if option in item['options']
    ]
    return found[0] if found else item['value']


def entered(model):
    """The name of the output of the people inside, in the report."""
    return model.outputs['hall.entered']


def blocks(out):
    """{run: the lines of its block} of the text of `napkin run`: a block starts with the run's name."""
    found, name = {}, None
    for line in out.splitlines():
        if line and not line.startswith(' ') and not line.startswith('note: '):
            name = line.split(':')[0].split(' ')[0]
            found[name] = []
        elif line and name is not None:
            found[name].append(line)
    return found


def row_of(lines, label):
    (row,) = [line for line in lines if line.startswith(f'  {label}  ')]
    return row


def test_run_gives_the_outcomes_of_sample_result_which_follow_the_closed_form(hall, napkin_call):
    model = hall_model(hall)
    times = [2 * scale_of('h'), 0.25 * scale_of('days')]
    done = napkin_call('run', hall, '--at', '2h,0.25days', '--json')
    assert done.code == 0, done.err
    doc = json.loads(done.out)
    report = sample_result(evaluate_study(model), times)
    assert list(doc['runs']) == list(report['runs']) == list(model.runs)
    for name, run in doc['runs'].items():
        rows = report['runs'][name]['reporting_points']
        assert run['reporting_points'] == {
            point: {key: row[key] for key in ('t', 'values', 'statuses')} for point, row in rows.items()
        }
        assert sorted(row['t'] for row in run['reporting_points'].values()) == [*times, model.time['horizon']]
        for row in run['reporting_points'].values():
            assert math.isclose(row['values'][entered(model)], rate_of(model, name) * row['t'], rel_tol=1e-9)


def test_run_prints_each_outcome_with_its_value_and_unit_at_the_end(hall, napkin_call):
    model = hall_model(hall)
    done = napkin_call('run', hall)
    assert done.code == 0 and done.err == ''
    report = sample_result(evaluate_study(model))
    found = blocks(done.out)
    assert list(found) == list(report['runs'])
    horizon = model.time['horizon']
    for name, run in report['runs'].items():
        assert f'at the end ({common.number(horizon)} h)' in found[name][0]
        final = run['reporting_points']['final']
        for outcome, item in run['outcomes'].items():
            row = row_of(found[name], item['label'])
            if final['statuses'][outcome] == 'estimated':
                assert row.endswith(f'{common.number(final["values"][outcome])} {item["unit"]}')
        value = rate_of(model, name) * horizon
        assert row_of(found[name], run['outcomes'][entered(model)]['label']).endswith(
            f'{common.number(value)} {run["outcomes"][entered(model)]["unit"]}'
        )


def test_run_prints_an_unestimated_outcome_as_not_estimated_never_zero(hall, napkin_call):
    model = hall_model(hall)
    done = napkin_call('run', hall, '--at', '2h')
    outcomes = sample_result(evaluate_study(model, runs=['narrow']))['runs']['narrow']['outcomes']
    (harm,) = [item for item in outcomes.values() if item['status'] == 'unestimated']
    for lines in blocks(done.out).values():
        row = row_of(lines, harm['label'])
        assert row.split()[len(harm['label'].split()) :] == ['not', 'estimated'] * 2
        assert not any(character.isdigit() for character in row)


def test_run_at_a_time_gives_the_value_at_that_time(hall, napkin_call):
    model = hall_model(hall)
    two = 2 * scale_of('h')
    done = napkin_call('run', hall, '--at', '2h', '--run', 'wide')
    assert done.code == 0
    lines = blocks(done.out)['wide']
    assert lines[0].split()[:3] == ['at', common.number(two), 'h']
    label = sample_result(evaluate_study(model, runs=['wide']))['runs']['wide']['outcomes'][entered(model)][
        'label'
    ]
    row = row_of(lines, label)
    assert row.split()[len(label.split())] == common.number(rate_of(model, 'wide') * two)


def test_run_with_runs_checks_those_runs_only_and_says_so(tmp_path, napkin_call):
    folder = write(tmp_path / 'hall', {'model.scn': CHECKED_HALL})
    # With every run checked, the model does not compile: the option "Wide" fails the check.
    whole = napkin_call('run', folder)
    assert whole.code == 1 and 'run wide' in whole.err
    done = napkin_call('run', folder, '--run', 'narrow')
    assert done.code == 0, done.err
    scoped = hall_model(folder, runs=['narrow'])
    assert done.out.splitlines()[0] == f'note: {common.scope_note(scoped)}'
    assert list(blocks(done.out)) == ['narrow']
    doc = json.loads(napkin_call('run', folder, '--run', 'narrow', '--json').out)
    assert doc['admitted_runs'] == ['narrow'] and list(doc['runs']) == ['narrow']
    # Without --run, every run is checked, and nothing says otherwise.
    plain = write(tmp_path / 'plain', {'model.scn': HALL})
    every = napkin_call('run', plain)
    assert every.code == 0 and not every.out.startswith('note: ')
    assert json.loads(napkin_call('run', plain, '--json').out)['admitted_runs'] is None


def test_run_refuses_an_unknown_run_with_the_closest_names_before_it_compiles(hall, napkin_call, monkeypatch):
    def no_load(*arguments, **keywords):
        raise AssertionError('an unknown run compiles nothing')

    monkeypatch.setattr(common, 'load', no_load)
    # The first run that the files do not declare, after one that they do.
    done = napkin_call('run', hall, '--run', 'wide', '--run', 'narow')
    assert done.code == 2 and done.out == ''
    message = done.err.splitlines()[-1]
    assert 'narow' in message and 'narrow' in message.split('narow', 1)[1]


def test_run_with_an_option_gives_the_values_of_a_run_that_names_it(hall, tmp_path, napkin_call):
    model = hall_model(hall)
    other = write(tmp_path / 'other', {'model.scn': WIDE_HALL})
    combined = json.loads(napkin_call('run', hall, '--run', 'narrow', '--option', 'Wide', '--json').out)
    named = json.loads(napkin_call('run', other, '--run', 'narrow', '--json').out)
    assert combined['runs']['narrow']['options'] == named['runs']['narrow']['options'] == ['Wide', 'Monday']
    assert combined['runs']['narrow']['reporting_points'] == named['runs']['narrow']['reporting_points']
    wide = model.inputs['hall.rate']['options']['Wide']['value']
    final = combined['runs']['narrow']['reporting_points']['final']
    assert math.isclose(final['values'][entered(model)], wide * final['t'], rel_tol=1e-9)
    # Without --run, the option goes into every run: one study for each, in one report.
    every = json.loads(napkin_call('run', hall, '--option', 'Day=Sunday', '--json').out)
    assert {name: run['options'] for name, run in every['runs'].items()} == {
        'narrow': ['Narrow', 'Sunday'],
        'wide': ['Wide', 'Sunday'],
    }
    assert every['admissible'] and every['schema_version'] == '0.0.1'
    text = napkin_call('run', hall, '--run', 'narrow', '--option', 'Wide')
    assert text.code == 0 and 'narrow: Wide · Monday' in text.out.splitlines()


def test_run_checks_a_combination_when_it_is_asked_for(tmp_path, napkin_call):
    folder = write(tmp_path / 'hall', {'model.scn': CHECKED_HALL})
    assert napkin_call('run', folder, '--run', 'narrow', '--option', 'Sunday').code == 0
    done = napkin_call('run', folder, '--run', 'narrow', '--option', 'Wide')
    assert done.code == 1 and 'run narrow' in done.err
    doc = json.loads(napkin_call('run', folder, '--run', 'narrow', '--option', 'Wide', '--json').out)
    assert not doc['admissible'] and doc['runs'] == {}
    assert any(item['code'].startswith('check:') and item['run'] == 'narrow' for item in doc['diagnostics'])


def test_run_sets_an_input_with_a_word_or_with_json(hall, napkin_call):
    model = hall_model(hall)
    shut = json.loads(napkin_call('run', hall, '--set', 'hall.door=shut', '--json').out)
    assert shut['effective_edits']['set'] == {'hall.door': 'shut'}
    for run in shut['runs'].values():
        assert all(row['values'][entered(model)] == 0 for row in run['reporting_points'].values())
    # A JSON number in the input's unit; an edit of every run wins over the value of an option.
    three = json.loads(
        napkin_call('run', hall, '--set', 'hall.rate=3', '--set', 'hall.door="open"', '--json').out
    )
    assert three['effective_edits']['set'] == {'hall.rate': 3, 'hall.door': 'open'}
    for run in three['runs'].values():
        final = run['reporting_points']['final']
        assert math.isclose(final['values'][entered(model)], 3 * final['t'], rel_tol=1e-9)
    assert napkin_call('run', hall, '--set', 'hall.rate=fast').code == 1  # a word is text, not a rate
    assert napkin_call('run', hall, '--set', 'hall.rate=3 people/h').code == 2


def test_run_merges_an_edit_file_and_the_settings(hall, tmp_path, napkin_call):
    model = hall_model(hall)
    path = edits_file(
        tmp_path, {'reason': 'A test', 'set': {'hall.rate': 3}, 'runs': {'wide': {'hall.rate': 7}}}
    )
    doc = json.loads(napkin_call('run', hall, '--edits', path, '--set', 'hall.rate=5', '--json').out)
    assert doc['effective_edits']['set'] == {'hall.rate': 5} and doc['effective_edits']['reason'] == 'A test'
    # The edit of one run wins over the edit of every run, which the setting gave.
    for name, rate in (('narrow', 5), ('wide', 7)):
        final = doc['runs'][name]['reporting_points']['final']
        assert math.isclose(final['values'][entered(model)], rate * final['t'], rel_tol=1e-9)
    # The file alone.
    alone = json.loads(napkin_call('run', hall, '--edits', path, '--json').out)
    assert alone['effective_edits']['set'] == {'hall.rate': 3}


def test_run_refuses_an_edit_document_of_another_model(hall, tmp_path, napkin_call):
    path = edits_file(tmp_path, {'model_hash': '0' * 64, 'set': {'hall.rate': 3}})
    for options in ([], ['--option', 'Sunday']):
        done = napkin_call('run', hall, '--edits', path, *options)
        assert done.code == 1 and done.out == '' and 'error: ' in done.err
        doc = json.loads(napkin_call('run', hall, '--edits', path, *options, '--json').out)
        assert not doc['admissible'] and doc['runs'] == {}
        assert 'model_hash' in {item['code'] for item in doc['diagnostics']}
        assert napkin_call('run', hall, '--edits', path, *options, '--json').code == 1


def test_run_prints_each_event_and_its_time(hall, napkin_call):
    model = hall_model(hall)
    done = napkin_call('run', hall, '--events', '--run', 'narrow')
    lines = blocks(done.out)['narrow']
    events = lines[lines.index('  events:') + 1 :]
    trace = sample_result(evaluate_study(model, runs=['narrow']))['runs']['narrow']['trace']
    fired = [entry for entry in trace if entry['outcome'] is not None]
    assert len(events) == len(fired) >= 1
    for line, entry in zip(events, fired):
        assert line.split()[:2] == [common.number(entry['t']), 'h'] and entry['event'] in line
    # The bell rings at the time that its `when` names.
    (ring,) = [entry for entry in fired if entry['rule'] == 'hall.ring']
    assert ring['t'] == RING_HOURS * scale_of('h')
    assert 'events:' not in napkin_call('run', hall, '--run', 'narrow').out


def test_run_prints_each_warning_of_the_study(tmp_path, napkin_call, monkeypatch):
    text = HALL.replace(
        '"Entry rate"\n        ' + FIXTURE,
        '"Entry rate"\n        @assumption A-RATE "The hall assumes the rate."',
    )
    folder = write(tmp_path / 'hall', {'model.scn': text})
    (folder / 'evidence').mkdir()
    (folder / 'evidence' / 'assumptions.json').write_text(json.dumps([assumption_record('A-RATE')]))
    monkeypatch.chdir(tmp_path)
    done = napkin_call('run', 'hall')
    assert done.code == 0
    report = sample_result(evaluate_study(hall_model(folder)))
    warnings = [item for item in report['diagnostics'] if item['severity'] == 'warning']
    assert warnings and done.err.splitlines() == [common.located(item) for item in warnings]


def test_run_json_is_one_report_document_and_full_adds_the_trace_evidence_and_index(hall, napkin_call):
    model = hall_model(hall)
    compact = json.loads(napkin_call('run', hall, '--json').out)
    assert compact['schema_version'] == '0.0.1' and compact['admissible'] and compact['admitted_runs'] is None
    assert compact['model_hash'] == model.model_hash
    full = json.loads(napkin_call('run', hall, '--json', 'full').out)
    assert full.keys() - compact.keys() == {'index'} and full['index'] == json.loads(
        json.dumps(thaw(model.index))
    )
    for name, run in compact['runs'].items():
        assert full['runs'][name].keys() - run.keys() == {'trace', 'evidence'}
        assert {key: full['runs'][name][key] for key in run} == run
    # --json before TARGET, and after it.
    assert json.loads(napkin_call('run', '--json', hall).out) == compact
    assert json.loads(napkin_call('run', '--json', 'full', hall).out) == full
    assert json.loads(napkin_call('run', hall, '--json=full').out) == full


def test_run_of_a_model_with_one_run_runs_it_with_every_run_checked(built, napkin_call):
    doc = json.loads(napkin_call('run', built.chain, '--variant', 'east', '--json').out)
    model = common.load(common.one_target(str(built.chain), 'east'))
    assert list(doc['runs']) == list(model.runs) and len(model.runs) == 1
    assert doc['admitted_runs'] is None


def test_run_uses_the_run_store_unless_told_not_to(hall, napkin_call, monkeypatch, tmp_path):
    from napkin import store

    monkeypatch.setenv('NAPKIN_STORE', str(tmp_path / 'runs'))
    assert napkin_call('run', hall, '--run', 'narrow').code == 0
    assert store.current() == tmp_path / 'runs'
    assert napkin_call('run', hall, '--run', 'narrow', '--no-store').code == 0
    assert store.current() is None


@pytest.mark.parametrize(
    'argv',
    [
        ['--option', 'Wid'],
        ['--option', 'Wide', '--option', 'Narrow'],
        ['--set', 'hall.rate=4h'],
        ['--at', '11h'],
        ['--at', '2'],
        ['--at', '2people'],
        ['--variant', 'east'],
        ['--run', 'narow'],
    ],
)
def test_run_refuses_a_command_line_that_names_nothing_of_the_model(hall, napkin_call, argv):
    done = napkin_call('run', hall, *argv)
    assert done.code == 2 and 'usage: napkin run' in done.err and done.out == ''


def test_run_lists_the_variants_of_a_package_and_stops(built, napkin_call):
    done = napkin_call('run', built.chain)
    assert done.code == 2 and all(name in done.err for name in VARIANTS)


@pytest.mark.parametrize('kind', ['module', 'empty folder', 'other file', 'missing'])
def test_run_refuses_what_is_no_target(built, tmp_path, napkin_call, kind):
    (tmp_path / 'empty').mkdir()
    text = {
        'module': built.chain / 'parts.scn',
        'empty folder': tmp_path / 'empty',
        'other file': built.shop / 'units.json',
        'missing': tmp_path / 'missing',
    }[kind]
    done = napkin_call('run', text)
    assert done.code == 2 and common.WHAT in done.err
    if kind == 'missing':
        # The hint: what a TARGET is.
        assert f'{text} does not exist' in done.err


def test_run_gives_the_file_line_and_column_of_a_model_that_does_not_compile(hall, napkin_call, monkeypatch):
    # A line at the top level that starts no declaration, after the file's last line: its first word,
    # at the first column, is the problem.
    (hall / 'model.scn').write_text(HALL + 'not a declaration\n', encoding='utf-8')
    monkeypatch.chdir(hall.parent)
    done = napkin_call('run', 'hall')
    assert done.code == 1 and done.out == ''
    assert done.err.startswith(f'{Path("hall", "model.scn")}:{len(HALL.splitlines()) + 1}:1: error: ')


@pytest.mark.parametrize(
    'value, shown',
    [
        (70000, '70000'),
        (0.00075, '0.00075'),
        (7.276e-12, '7.276e-12'),
        (2303.349, '2303'),
        (0, '0'),
        (None, 'None'),
    ],
)
def test_a_value_shows_four_significant_figures(value, shown):
    assert common.number(value) == shown


# --- napkin play ------------------------------------------------------------------------------------


@pytest.fixture
def play_cli(monkeypatch, capsys, store_state):
    """`napkin play ARGV` in this process, with `stdin` as its input and no run store: (the exit code,
    the standard output, the standard error)."""
    monkeypatch.setenv('NAPKIN_STORE', 'off')

    def call(*argv, stdin=''):
        monkeypatch.setattr(sys, 'stdin', io.StringIO(stdin))
        code = cli.main(['play', *map(str, argv)])
        out, err = capsys.readouterr()
        return code, out, err

    return call


@pytest.fixture(scope='module')
def play_fast(built):
    """The shop's model checked for its run `fast` only, as `napkin play --run fast` checks it."""
    return common.load(common.one_target(str(built.shop)), runs=['fast'])


PLAY_CONTROL = {'guard': 'reader'}


def play_session(model, **kwargs):
    from napkin.session import Session

    return Session(model, 'fast', control=PLAY_CONTROL, **kwargs)


def play_first(decision):
    return next(item['name'] for item in decision['outcomes'] if item['available'])


def play_lines(out):
    return [json.loads(line) for line in out.splitlines()]


def test_play_lists_the_runs_when_the_model_has_several(play_cli, built):
    code, _, err = play_cli(built.shop, '--control', 'guard')
    assert code == 2
    # Each run with its label, as the model gives it; the usage's own lines go on with more spaces.
    rows = [line.split(None, 1) for line in err.splitlines() if line.startswith('  ') and line[2] != ' ']
    assert rows == [[name, run['name']] for name, run in built.model.runs.items()]


def test_play_refuses_an_unknown_run_with_the_closest_names_before_it_compiles(play_cli, built, monkeypatch):
    def no_load(*arguments, **keywords):
        raise AssertionError('an unknown run compiles nothing')

    monkeypatch.setattr(common, 'load', no_load)
    code, out, err = play_cli(built.shop, '--run', 'fats', '--control', 'guard')
    assert (code, out) == (2, '') and 'usage: napkin play' in err
    message = err.splitlines()[-1]
    assert 'fats' in message and 'fast' in message.split('fats', 1)[1]


def test_play_json_writes_the_decision_again_after_each_line_that_is_no_answer(play_cli, built, play_fast):
    decision = play_session(play_fast).advance()
    pick = play_first(decision)
    cannot = next(item['name'] for item in decision['outcomes'] if item['name'] != pick)
    bad = [
        'not json',
        '[1]',
        '{"pick": "nothing"}',
        '{"pick": 1}',
        json.dumps({'pick': pick, 'why': 'no'}),
        json.dumps({'pick': pick, 'reason': 3}),
        f'{{"pick": "{pick}", "pick": "{cannot}"}}',
        '{"pick": NaN}',
    ]
    stdin = '\n'.join(['', *bad, '  ', json.dumps({'pick': pick, 'reason': 'why'})]) + '\n'
    code, out, _ = play_cli(built.shop, '--run', 'fast', '--control', 'guard', '--json', stdin=stdin)
    assert code == 0
    lines = play_lines(out)
    assert all(line['schema_version'] == '0.0.1' for line in lines)
    assert [line['type'] for line in lines] == ['decision', *['error', 'decision'] * len(bad), 'result']
    shown = {key: value for key, value in lines[0].items() if key not in ('type', 'schema_version')}
    assert shown == decision
    assert all(line == lines[0] for line in lines if line['type'] == 'decision')
    result = lines[-1]
    assert result['finished'] is True and 'decision' not in result
    assert result['picks'] == [
        {'event': decision['event'], 'outcome': pick, 't': decision['t'], 'by': 'reader', 'reason': 'why'}
    ]
    finished = play_session(play_fast, resolver=lambda decision: (pick, 'why'))
    assert finished.advance() is None
    assert result['report'] == common.compact(finished.result(), admitted=('fast',))


def test_play_json_ends_with_the_decision_that_waits_when_the_input_ends(play_cli, built, play_fast):
    code, out, _ = play_cli(built.shop, '--run', 'fast', '--control', 'guard', '--json')
    lines = play_lines(out)
    assert code == 3 and [line['type'] for line in lines] == ['decision', 'result']
    assert lines[-1]['finished'] is False and lines[-1]['report'] is None and lines[-1]['picks'] == []
    assert lines[-1]['decision'] == play_session(play_fast).advance()


@pytest.mark.parametrize('json_lines_too', [False, True], ids=['terminal', 'json'])
def test_play_refuses_an_unknown_control_with_the_engines_diagnostic_and_names_the_actors(
    play_cli, built, play_fast, json_lines_too
):
    from napkin.model.views import actors

    code, out, err = play_cli(
        built.shop, '--run', 'fast', '--control', 'nobody', *(['--json'] if json_lines_too else [])
    )
    assert code == 1
    study = evaluate_study(
        play_fast, runs=['fast'], play={'run': 'fast', 'control': {'nobody': 'reader'}, 'picks': []}
    )
    assert not study.admissible and {item['code'] for item in study.diagnostics} == {'play'}
    lines = err.splitlines()
    assert all(common.located(item) in lines for item in study.diagnostics)
    (hint,) = [
        line
        for line in lines
        if line.startswith('note: ') and line != f'note: {common.scope_note(play_fast)}'
    ]
    named = actors(play_fast)
    assert named and all(
        actor['name'] in hint and all(choice['event'] in hint for choice in actor['choices'])
        for actor in named
    )
    if json_lines_too:
        error, result = play_lines(out)
        assert (
            error['type'] == 'error' and error['diagnostics'][: len(study.diagnostics)] == study.diagnostics
        )
        assert (result['type'], result['finished'], result['report'], result['picks']) == (
            'result',
            False,
            None,
            [],
        )


def test_play_at_the_terminal_takes_a_number_or_a_name_and_asks_again_for_anything_else(
    play_cli, built, play_fast, tmp_path
):
    from napkin.session import Session

    decision = play_session(play_fast).advance()
    names = [item['name'] for item in decision['outcomes'] if item['available']]
    log = tmp_path / 'log.json'
    answers = {'a number': (f'nothing\n{len(names) + 1}\n0\n{len(names)}\n\n', names[-1], None)}
    answers['a name'] = (f'{names[0]}\nbecause\n', names[0], 'because')
    for stdin, outcome, reason in answers.values():
        code, out, _ = play_cli(built.shop, '--run', 'fast', '--control', 'guard', '--save', log, stdin=stdin)
        assert code == 0
        # The model is checked for the run only, and the output says so first.
        assert out.splitlines()[0] == f'note: {common.scope_note(play_fast)}'
        picks = Session.load(log, play_fast, 'fast', control=PLAY_CONTROL).picks
        assert [(item['event'], item['outcome'], item['reason']) for item in picks] == [
            (decision['event'], outcome, reason)
        ]
        # The output shows each outcome of the run by its label.
        report = play_session(play_fast, picks=picks).result()
        assert all(item['label'] in out for item in report['runs']['fast']['outcomes'].values())


# What the command line of a log's continuation changes, by the field of the log that then differs.
PLAY_CONTEXT = {
    'run': ['--run', 'slow', '--control', 'guard'],
    'options': ['--run', 'fast', '--control', 'guard', '--option', 'Slow'],
    'control': ['--run', 'fast', '--control', 'guard.decide'],
    'edits': ['--run', 'fast', '--control', 'guard', '--set', 'shop.rate=2'],
}


def test_play_continues_a_log_of_the_same_context(play_cli, built, tmp_path):
    log = tmp_path / 'log.json'
    argv = (built.shop, '--run', 'fast', '--control', 'guard')
    code, out, _ = play_cli(*argv, '--save', log)
    assert code == 3 and log.is_file()
    code, out, _ = play_cli(*argv, '--picks', log, '--json', stdin=json.dumps({'pick': 'keep'}) + '\n')
    assert code == 0 and play_lines(out)[-1]['finished'] is True


@pytest.mark.parametrize('field', PLAY_CONTEXT)
def test_play_refuses_a_log_of_another_context_and_names_what_differs(play_cli, built, field, tmp_path):
    log = tmp_path / 'log.json'
    code, _, _ = play_cli(built.shop, '--run', 'fast', '--control', 'guard', '--save', log)
    assert code == 3
    kept = log.read_bytes()
    code, _, err = play_cli(built.shop, *PLAY_CONTEXT[field], '--picks', log, '--save', log)
    assert code == 1 and field in err.replace(str(log), '')
    # The refused log stays as it was.
    assert log.read_bytes() == kept


def test_play_with_options_and_settings_plays_that_combination(play_cli, built, play_fast):
    from napkin.engine import edits_for

    code, out, _ = play_cli(
        built.shop,
        '--run',
        'fast',
        '--control',
        'guard',
        '--option',
        'Slow',
        '--set',
        'shop.rate=2',
        '--json',
        stdin=json.dumps({'pick': 'reopen'}) + '\n',
    )
    assert code == 0
    result = play_lines(out)[-1]
    session = play_session(
        play_fast,
        options=('Slow',),
        edits=edits_for(play_fast, {'set': {'shop.rate': 2}}),
        resolver=lambda decision: ('reopen', None),
    )
    assert session.advance() is None
    assert result['report'] == common.compact(session.result(), admitted=('fast',))
    assert 'Slow' in result['report']['runs']['fast']['options']


# --- napkin sample ----------------------------------------------------------------------------------

# A desk serves people at its rate until it closes, so a sample serves rate * min(t, end) people by
# time t, plus the people that its start option serves before the start. Run `fixed` takes a fixed
# rate and is compared with run `drawn`; run `ahead` names the start option "Ahead", which sets the
# start value of a stock: it changes the structure of the run, not only its values. The check
# refuses a closing time before SAMPLE_OPEN hours, which no draw of the model's own distribution gives.
SAMPLE_OPEN = 1.5
SAMPLE_QUEUE = f"""\
scenario "A queue"
    summary "A desk serves people until it closes. A synthetic fixture for tests only."
    horizon 24 h
    scope "Fixture"

desk:
    "A desk."
    {FIXTURE}
    role environment
    input rate: people/h = uniform(1 people/h, 3 people/h) in 0.5 people/h to 4 people/h
        "Service rate"
        {FIXTURE}
    input end: h = pert(2 h, 6 h, 20 h) in 1 h to 22 h
        "Closing time"
        {FIXTURE}
    var state: "open" | "closed" = "open"
        "Open or closed"
        {FIXTURE}
    var served: people = 0 people size 100 people
        "People served"
        {FIXTURE}
    event close when state is "open" and t >= end:
        "The desk closes."
        {FIXTURE}
        state = "closed"
    flow serve: -> served at rate if state is "open" else 0 people/h
        {FIXTURE}

assert desk.end >= {SAMPLE_OPEN} h
    "The desk opens for long enough."
    {FIXTURE}

output served_total: people = desk.served
    "People served"
    {FIXTURE}

output harm: people
    "Harm"
    unestimated "No source gives it."
    {FIXTURE}

options "Rate":
    "Drawn rate":
        "The rate as the model draws it."
    "Fixed rate":
        "A fixed rate."
        desk.rate = 2 people/h
            {FIXTURE}

options "Start":
    "Empty":
        "No one is served at the start."
    "Ahead":
        "Some people are served before the start."
        desk.served = 5 people
            {FIXTURE}

runs:
    drawn = "Drawn rate" + "Empty"
    fixed = "Fixed rate" + "Empty" versus drawn
    ahead = "Drawn rate" + "Ahead"
"""

# One drawn number and nothing that moves: each sample's outcome is its draw, and a sample is fast.
SAMPLE_DRAW = f"""\
scenario "A draw"
    summary "One drawn number. A synthetic fixture for tests only."
    horizon 1 h
    scope "Fixture"

box:
    "A box."
    {FIXTURE}
    role environment
    input size: people = uniform(1 people, 3 people) in 0 people to 4 people
        "Size"
        {FIXTURE}

output size_out: people = box.size
    "Size of the box"
    level
    {FIXTURE}
"""


@pytest.fixture(scope='module')
def sample_packages(tmp_path_factory):
    """The queue and the draw, written once for the tests that only read them, and the queue's model."""
    base = tmp_path_factory.mktemp('sampled')
    queue = write(base / 'queue', {'model.scn': SAMPLE_QUEUE})
    single = write(base / 'single', {'model.scn': SAMPLE_DRAW})
    return SimpleNamespace(queue=queue, single=single, model=common.load(common.one_target(str(queue))))


@pytest.fixture
def no_store(monkeypatch):
    """No run store, and the store's setting restored after the test: the samples read and write none,
    and no helper process starts."""
    from napkin import store

    monkeypatch.setattr(store, '_active', dict(store._active))
    monkeypatch.setenv('NAPKIN_STORE', 'off')


def sampling(capsys, *argv):
    """(exit code, standard output, standard error) of `napkin sample ARGV`."""
    code = cli.main(['sample', *map(str, argv)])
    out, err = capsys.readouterr()
    return code, out, err


def sampled_doc(capsys, *argv):
    """The `--json` document of `napkin sample ARGV`, which must exit 0 with one line."""
    code, out, err = sampling(capsys, *argv, '--json')
    assert code == 0, err
    assert out.count('\n') == 1
    return json.loads(out)


def serves(draws, t, rate=None):
    """The closed form of the queue: the people that a sample serves by time t, rate * min(t, end),
    with the sample's drawn rate unless `rate` is given."""
    return (draws['desk.rate'] if rate is None else rate) * min(t, draws['desk.end'])


def outcome_block(out, outcome):
    """The lines of the text of `napkin sample` under the heading of `outcome`."""
    lines = out.splitlines()
    start = next(k for k, line in enumerate(lines) if line.startswith(f'{outcome}: '))
    end = next((k for k in range(start + 1, len(lines)) if not lines[k]), len(lines))
    return lines[start + 1 : end]


def test_sample_gives_the_mean_and_quantiles_of_the_closed_forms(sample_packages, no_store, capsys):
    """Each sample of run drawn serves rate * min(t, end) people, at the end of the run and at --at.
    The mean, the standard deviation and the type-7 percentiles of these closed forms (numpy's own) are
    the summary's, and the text shows the summary's numbers. An outcome that no source gives is not
    estimated in any sample, and the text says so."""
    import numpy as np

    queue = sample_packages.queue
    for at, t in ((None, sample_packages.model.time['horizon']), ('3h', 3.0)):
        extra = () if at is None else ('--at', at)
        argv = ('--run', 'drawn', '--samples', 40, '--seed', 3, '--jobs', 1, *extra, queue)
        record = sampled_doc(capsys, *argv)['runs']['drawn']
        assert record['settings']['t'] == t
        closed = [serves(sample['draws'], t) for sample in record['samples']]
        values = [sample['values']['served_total'] for sample in record['samples']]
        assert values == pytest.approx(closed, rel=1e-9, abs=1e-9)
        summary = record['summary']['served_total']
        assert summary['mean'] == pytest.approx(np.mean(closed), rel=1e-9)
        assert summary['sd'] == pytest.approx(np.std(closed, ddof=1), rel=1e-9)
        for p in (5, 25, 50, 75, 95):
            assert summary[f'p{p}'] == pytest.approx(np.percentile(closed, p), rel=1e-9)
        harm = record['summary']['harm']
        assert harm['estimated'] is False
        assert {sample['statuses']['harm'] for sample in record['samples']} == {'unestimated'}
        assert {sample['values']['harm'] for sample in record['samples']} == {None}
        code, out, err = sampling(capsys, *argv)
        assert code == 0, err
        (line,) = [line for line in outcome_block(out, 'served_total') if line.split()[0] == 'drawn']
        for key in ('mean', 'p5', 'p25', 'p75', 'p95'):
            assert common.number(summary[key]) in line.replace(';', ' ').split(), key
        assert [line.split()[1:] for line in outcome_block(out, 'harm')] == [['not', 'estimated']] * 2


def tail_values(capsys, single, samples, keys):
    """(the summary of the draw's outcome, the type-7 percentiles of its draws at `keys`, the text) of
    `samples` samples of the draw, whose outcome in each sample is its draw."""
    import numpy as np

    record = sampled_doc(capsys, '--samples', samples, '--jobs', 1, single)['runs']['base']
    draws = [entry['draws']['box.size'] for entry in record['samples']]
    expected = {key: float(np.percentile(draws, float(key[1:]))) for key in keys}
    code, out, err = sampling(capsys, '--samples', samples, '--jobs', 1, single)
    assert code == 0, err
    return record['summary']['size_out'], expected, out


def test_the_1_in_100_value_shows_from_1000_samples(sample_packages, no_store, capsys):
    """The 1-in-100 value (p99) shows from 1000 samples, and not with 999: it is the type-7 percentile
    of the draws, as each sample gives its draw. The 1-in-200 value does not show with 1000. The text
    shows the values of the document, so a value that the text leaves out is not in the document."""
    from napkin.commands import sample

    (_, hundred), (_, two_hundred) = sample.TAILS
    _, out, _ = sampling(capsys, '--samples', 999, '--jobs', 1, sample_packages.single)
    assert hundred not in out and two_hundred not in out
    summary, expected, out = tail_values(capsys, sample_packages.single, 1000, ['p99'])
    assert summary['p99'] == pytest.approx(expected['p99'], rel=1e-12) and 'p99.5' not in summary
    assert hundred in out and two_hundred not in out


def test_the_1_in_200_value_shows_from_2000_samples(sample_packages, no_store, capsys):
    """The 1-in-200 value (p99.5) shows from 2000 samples, and not with 1999; the 1-in-100 value shows
    with both."""
    from napkin.commands import sample

    (_, hundred), (_, two_hundred) = sample.TAILS
    _, out, _ = sampling(capsys, '--samples', 1999, '--jobs', 1, sample_packages.single)
    assert hundred in out and two_hundred not in out
    summary, expected, out = tail_values(capsys, sample_packages.single, 2000, ['p99', 'p99.5'])
    for key, value in expected.items():
        assert summary[key] == pytest.approx(value, rel=1e-12), key
    assert hundred in out and two_hundred in out


def test_an_exceedance_is_the_share_of_the_samples_above_the_value(sample_packages, no_store, capsys):
    """--exceed gives, for each run, the number of the samples whose outcome is above the value, of
    all the samples, counted here from the values of the samples: a sample at the value is not above
    it, and none is above the largest."""
    queue = sample_packages.queue
    argv = ('--run', 'drawn', '--samples', 30, '--jobs', 1, queue)
    first = sampled_doc(capsys, *argv)['runs']
    values = {run: [s['values']['served_total'] for s in record['samples']] for run, record in first.items()}
    limits = [values['drawn'][0], 20.0, max(values['drawn'])]
    exceed = [item for value in limits for item in ('--exceed', f'served_total={value!r}')]
    doc = sampled_doc(capsys, *argv, *exceed)
    code, out, err = sampling(capsys, *argv, *exceed)
    assert code == 0, err
    lines = outcome_block(out, 'served_total')
    for run, record in doc['runs'].items():
        assert [s['values']['served_total'] for s in record['samples']] == values[run]
        found = record['summary']['served_total']['exceed']
        assert [item['value'] for item in found] == limits
        for item in found:
            count = sum(1 for value in values[run] if value > item['value'])
            assert (item['count'], item['samples'], item['chance']) == (count, 30, count / 30)
            shown = f'P(served_total > {common.number(item["value"])}) = {common.number(count / 30)}'
            assert any(shown in line and f'({count} of 30 samples)' in line for line in lines)
    assert doc['runs']['drawn']['summary']['served_total']['exceed'][-1]['count'] == 0
    assert doc['runs']['drawn']['summary']['served_total']['exceed'][0]['count'] < 30


def test_the_compared_run_is_sampled_on_the_same_draws(sample_packages, no_store, capsys):
    """A spread of run drawn or of run fixed, which is compared with it, samples both, in the order of
    the file, on the same draws: each sample of fixed draws the closing time of the same sample of
    drawn, and its own fixed rate (`Model.run_values`), which is not drawn."""
    queue, model = sample_packages.queue, sample_packages.model
    docs = {run: sampled_doc(capsys, '--run', run, '--samples', 12, '--jobs', 1, queue) for run in model.runs}
    assert list(docs['drawn']['runs']) == list(docs['fixed']['runs']) == ['drawn', 'fixed']
    assert docs['drawn']['runs'] == docs['fixed']['runs']
    assert list(docs['ahead']['runs']) == ['ahead']
    drawn, fixed = (docs['drawn']['runs'][run]['samples'] for run in ('drawn', 'fixed'))
    assert [s['draws']['desk.end'] for s in drawn] == [s['draws']['desk.end'] for s in fixed]
    assert {tuple(s['draws']) for s in drawn} == {('desk.rate', 'desk.end')}
    assert {tuple(s['draws']) for s in fixed} == {('desk.end',)}
    rate, t = model.run_values('fixed')['desk.rate'], model.time['horizon']
    closed = [serves(s['draws'], t, rate) for s in fixed]
    assert [s['values']['served_total'] for s in fixed] == pytest.approx(closed, rel=1e-9, abs=1e-9)


def test_an_option_samples_its_combination_in_every_process(sample_packages, no_store, capsys, monkeypatch):
    """With --option "Ahead" and two processes, run drawn gives the samples of run ahead, which names
    the option, sampled in this process: each process makes the combination. Run fixed, which is
    compared with drawn, takes the option too, on the same draws. Each sample serves the same number of
    people more than the same sample without the option, a number above zero: a process that ignored
    the combination would serve none more."""
    from napkin import spread

    queue, many = sample_packages.queue, ('--samples', 12)
    monkeypatch.setattr(spread, '_POOLS', {})
    try:
        pooled = sampled_doc(capsys, '--run', 'drawn', '--option', 'Ahead', *many, '--jobs', 2, queue)
    finally:
        for pool in spread._POOLS.values():
            pool.shutdown()
    named = sampled_doc(capsys, '--run', 'ahead', *many, '--jobs', 1, queue)
    plain = sampled_doc(capsys, '--run', 'drawn', *many, '--jobs', 1, queue)
    assert pooled['options'] == ['Ahead'] and list(pooled['runs']) == ['drawn', 'fixed']
    assert pooled['runs']['drawn']['samples'] == named['runs']['ahead']['samples']
    for run in ('drawn', 'fixed'):
        assert 'Ahead' in pooled['runs'][run]['options']
    drawn, fixed = (pooled['runs'][run]['samples'] for run in ('drawn', 'fixed'))
    assert [s['draws']['desk.end'] for s in drawn] == [s['draws']['desk.end'] for s in fixed]
    more = set()
    for run in ('drawn', 'fixed'):
        pairs = zip(pooled['runs'][run]['samples'], plain['runs'][run]['samples'], strict=True)
        for with_option, without in pairs:
            assert with_option['draws'] == without['draws']
            more.add(round(with_option['values']['served_total'] - without['values']['served_total'], 9))
    (ahead,) = more
    assert ahead > 0


def test_the_document_has_one_record_for_each_sample_with_its_draws(sample_packages, no_store, capsys):
    """--json gives, for each sampled run, its settings, the distribution of each drawn input as the
    model gives it, the label and unit of each outcome, and one record for each sample: its draws of
    the drawn inputs, and the value and status of each outcome."""
    from napkin import SCHEMA_VERSION
    from napkin.engine.sampling import uncertain

    model, queue = sample_packages.model, sample_packages.queue
    doc = sampled_doc(capsys, '--run', 'drawn', '--samples', 17, '--seed', 5, '--jobs', 1, queue)
    assert doc['schema_version'] == SCHEMA_VERSION and doc['model_hash'] == model.model_hash
    settings = {'samples': 17, 'seed': 5, 'method': 'random', 'point': 'final', 't': model.time['horizon']}
    for run, record in doc['runs'].items():
        assert record['settings'] == settings
        written = model.written_values(run)
        assert record['inputs'] == {
            name: {'label': model.inputs[name]['doc'], 'distribution': written[name]['text']}
            for name in uncertain(written)
        }
        outputs = {name: model.structure_of(run).outcomes[name] for name in model.outputs.values()}
        assert record['outcomes'] == {
            name: {'label': item.label, 'unit': item.unit} for name, item in outputs.items()
        }
        assert len(record['samples']) == 17
        for sample in record['samples']:
            assert set(sample['draws']) == set(record['inputs'])
            assert set(sample['values']) == set(sample['statuses']) == set(outputs)
    assert doc['runs']['drawn']['samples'] != doc['runs']['fixed']['samples']


def test_a_model_with_no_distribution_says_so_and_shows_no_spread(built, no_store, capsys, monkeypatch):
    """The shop has no input with a distribution: with or without a run, the command says so, samples
    nothing and exits 0; its document has no run. An edit document that gives an input a distribution
    gives the shop a spread, which draws that input."""
    from napkin import spread

    real = spread.spread

    def no_spread(*arguments, **keywords):
        raise AssertionError('a model with no distribution has no spread')

    monkeypatch.setattr(spread, 'spread', no_spread)
    for argv in ((built.shop,), ('--run', 'fast', built.shop)):
        code, out, err = sampling(capsys, *argv)
        assert code == 0 and err == '' and len(out.splitlines()) == 1
        assert 'distribution' in out and 'served_total' not in out
        doc = sampled_doc(capsys, *argv)
        assert doc['runs'] == {} and doc['note'] in out
    monkeypatch.setattr(spread, 'spread', real)
    text = 'uniform(0.5 people/h, 2 people/h)'
    setting = f'shop.rate={json.dumps(text)}'
    doc = sampled_doc(capsys, '--run', 'fast', '--set', setting, '--samples', 4, '--jobs', 1, built.shop)
    assert list(doc['runs']) == ['fast', 'slow']
    assert doc['runs']['slow']['inputs']['shop.rate']['distribution'] == text
    assert len({s['draws']['shop.rate'] for s in doc['runs']['slow']['samples']}) == 4


def test_a_run_admits_itself_and_the_runs_it_is_compared_with_and_says_so(
    sample_packages, no_store, capsys, monkeypatch
):
    """D-42: --run drawn checks the model for drawn and fixed, which is compared with it, and not for
    ahead. The files give those runs, so the model loads once, for them, and never for every run. The
    document names those runs and the text says so. A run compared with no other admits itself alone."""
    queue = sample_packages.queue
    real, loads = common.load, []

    def load(target, runs=None):
        loads.append(None if runs is None else list(runs))
        return real(target, runs)

    monkeypatch.setattr(common, 'load', load)
    for run, admitted in (('drawn', ['drawn', 'fixed']), ('fixed', ['drawn', 'fixed']), ('ahead', ['ahead'])):
        loads.clear()
        doc = sampled_doc(capsys, '--run', run, '--samples', 4, '--jobs', 1, queue)
        assert doc['admitted_runs'] == admitted and list(doc['runs']) == admitted
        assert loads == [admitted]
        assert admitted == comparisons(sample_packages.model, run)
        code, out, err = sampling(capsys, '--run', run, '--samples', 4, '--jobs', 1, queue)
        assert code == 0, err
        assert common.scope_note(SimpleNamespace(admission_runs=tuple(admitted))) in out.splitlines()


def test_the_only_run_is_the_run_and_several_runs_need_one(sample_packages, no_store, capsys):
    """A model with one run samples it, checked for every run. A model with several runs and no --run
    lists each run and stops (exit 2)."""
    doc = sampled_doc(capsys, '--samples', 4, '--jobs', 1, sample_packages.single)
    assert doc['admitted_runs'] is None and len(doc['runs']) == 1
    code, out, err = sampling(capsys, '--samples', 4, sample_packages.queue)
    assert code == 2 and out == '' and 'usage: napkin sample' in err
    # The usage's own lines go on with more spaces.
    listed = [line.split()[0] for line in err.splitlines() if line.startswith('  ') and line[2] != ' ']
    assert listed == list(sample_packages.model.runs)


def test_sample_refuses_an_unknown_run_with_the_closest_names_before_it_compiles(
    sample_packages, no_store, capsys, monkeypatch
):
    def no_load(*arguments, **keywords):
        raise AssertionError('an unknown run compiles nothing')

    monkeypatch.setattr(common, 'load', no_load)
    code, out, err = sampling(capsys, '--run', 'drwn', '--samples', 4, sample_packages.queue)
    assert (code, out) == (2, '') and 'usage: napkin sample' in err
    message = err.splitlines()[-1]
    assert 'drwn' in message and 'drawn' in message.split('drwn', 1)[1]


@pytest.mark.parametrize('jobs, samples', [(8, 3), (2, 3)])
def test_no_more_processes_start_than_there_are_samples(
    sample_packages, no_store, capsys, monkeypatch, jobs, samples
):
    """The pool of the samples has min(jobs, samples) processes. Here the pool runs each task in this
    process, so no process starts, and it counts the processes that it was asked for."""
    from concurrent.futures import Future

    from napkin import spread

    asked = []

    class Pool:
        def __init__(self, workers, **options):
            asked.append(workers)

        def submit(self, function, task):
            future = Future()
            future.set_result(function(task))
            return future

    monkeypatch.setattr(spread, 'ProcessPoolExecutor', Pool)
    monkeypatch.setattr(spread, '_POOLS', {})
    doc = sampled_doc(capsys, '--samples', samples, '--jobs', jobs, sample_packages.single)
    assert asked == [min(jobs, samples)]
    assert [len(record['samples']) for record in doc['runs'].values()] == [samples]


def test_inputs_that_the_engine_refuses_stop_the_command_before_the_first_sample(
    sample_packages, no_store, capsys, monkeypatch, tmp_path
):
    """An input outside its range, and a distribution outside the range of its input, from --set or an
    edit document, are refused with the engine's diagnostics, which call the input by its label. So is
    a distribution whose draws break the model's check, with the diagnostic of each sample that breaks
    it, its draw named. Each is refused before any sample runs (exit 1)."""
    from napkin import spread

    def no_sample(*arguments):
        raise AssertionError('a refused spread runs no sample')

    monkeypatch.setattr(spread, 'run_sample', no_sample)
    queue, model = sample_packages.queue, sample_packages.model
    low, high = model.inputs['desk.end']['range']
    below = f'uniform({low - 0.5} h, {high} h)'
    document = tmp_path / 'edits.json'
    document.write_text(json.dumps({'set': {'desk.end': below}}), encoding='utf-8')
    above = model.inputs['desk.rate']['range'][1] + 1
    for given, name in (
        (('--set', f'desk.rate={above}'), 'desk.rate'),
        (('--set', f'desk.end={json.dumps(below)}'), 'desk.end'),
        (('--edits', document), 'desk.end'),
    ):
        code, out, err = sampling(capsys, '--run', 'drawn', '--samples', 20, '--jobs', 1, *given, queue)
        assert (code, out) == (1, ''), given
        assert model.inputs[name]['doc'] in err, given
    # Its median keeps the desk open for long enough, so the run itself holds the check; a third of
    # its draws do not.
    short = 'desk.end=' + json.dumps(f'uniform({low} h, {SAMPLE_OPEN + 1} h)')
    code, out, err = sampling(capsys, '--run', 'drawn', '--samples', 20, '--jobs', 1, '--set', short, queue)
    assert (code, out) == (1, '')
    rows = [line for line in err.splitlines() if 'error' in line]
    assert rows and all('sample' in line and 'desk.end=' in line for line in rows)


# --- napkin draw ------------------------------------------------------------------------------------


def svg_things(path):
    """The cards of an SVG that `napkin draw` wrote, by their `data-thing`; the file must parse."""
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()
    assert root.tag == '{http://www.w3.org/2000/svg}svg' and root.get('role') == 'img'
    return {g.get('data-thing') for g in root.iter('{http://www.w3.org/2000/svg}g') if g.get('data-thing')}


def test_draw_writes_the_svg_of_the_target_to_the_file_that_its_name_gives(
    built, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['draw', str(built.shop)]) == 0
    assert svg_things(tmp_path / 'shop.svg') == {entity.entry for entity in built.model.scenario.entities}
    assert capsys.readouterr().out.startswith('shop.svg')
    # --run draws that run, checked for that run only, and names it in the file.
    assert cli.main(['draw', str(built.shop), '--run', 'fast']) == 0
    assert svg_things(tmp_path / 'shop.fast.svg')
    out = capsys.readouterr().out
    assert out.startswith('note: ') and 'fast' in out.splitlines()[0]
    assert out.splitlines()[-1].startswith('shop.fast.svg')
    # A variant names its file too.
    assert cli.main(['draw', str(built.chain), '--variant', 'east']) == 0
    assert svg_things(tmp_path / 'chain.east.svg') == {'shop'}


def test_draw_says_when_the_picture_is_taller_than_a_pdf_page(built, tmp_path, monkeypatch, capsys):
    from napkin.draw import layout as layouts

    output = tmp_path / 'map.svg'
    assert cli.main(['draw', str(built.shop), '-o', str(output)]) == 0
    height = float(re.search(r'height="([0-9.]+)"', output.read_text(encoding='utf-8')).group(1))
    assert 'PDF page' not in capsys.readouterr().out
    # Taller than the page: a note that names the file and its height, before the line of the file.
    monkeypatch.setattr(layouts, 'PAGE_HEIGHT', height - 0.5)
    assert cli.main(['draw', str(built.shop), '-o', str(output)]) == 0
    lines = capsys.readouterr().out.splitlines()
    (note,) = [line for line in lines if 'PDF page' in line]
    assert note.startswith('note: ') and str(output) in note and f'{height:,.0f} px tall' in note
    assert lines[-1].startswith(str(output))
    # Exactly as tall as the page: no note.
    monkeypatch.setattr(layouts, 'PAGE_HEIGHT', height)
    assert cli.main(['draw', str(built.shop), '-o', str(output)]) == 0
    assert 'PDF page' not in capsys.readouterr().out


def test_draw_writes_the_file_that_o_names(built, tmp_path, capsys):
    output = tmp_path / 'pictures' / 'map.svg'
    output.parent.mkdir()
    assert cli.main(['draw', str(built.shop), '-o', str(output)]) == 0
    assert svg_things(output) and str(output) in capsys.readouterr().out
    # A file that cannot be written fails with its path.
    missing = tmp_path / 'no-such-folder' / 'map.svg'
    assert cli.main(['draw', str(built.shop), '-o', str(missing)]) == 1
    assert str(missing) in capsys.readouterr().err and not missing.exists()


# The shop's stylesheet with a panel of its equations and their references.
SHOP_PANELS = '[equations]\nthings = ["shop"]\n\n[references]\nshow = true\n'


def test_draw_writes_the_latex_of_the_panels_to_the_file_that_latex_names(tmp_path, monkeypatch, capsys):
    """--latex FILE writes the fragment of the picture's panels beside the SVG: an `align*` for each
    block, a table of the symbols and an item for each reference, and names it in its line. A
    stylesheet without [equations] gives a fragment of comments only, with a note; a file that cannot
    be written fails with its path."""
    from napkin.draw import model_map

    monkeypatch.chdir(tmp_path)
    folder = write_shop(tmp_path / 'shop')
    (folder / 'style.toml').write_text(SHOP_PANELS, encoding='utf-8')
    assert cli.main(['draw', str(folder), '--run', 'fast', '--latex', 'shop.tex']) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-2].startswith('shop.fast.svg') and out[-1].startswith('shop.tex: ')
    text = (tmp_path / 'shop.tex').read_text(encoding='utf-8')
    model = common.load(common.one_target(str(folder)))
    found = model_map.picture(model, run='fast')['panels']
    blocks = [block for block in found['equations'] if block['lines']]
    assert blocks and text.count(r'\begin{align*}') == text.count(r'\end{align*}') == len(blocks)
    assert text.count(r'\item ') == len(found['references']) > 0
    assert text.count(r'\begin{longtable}') == 1 and text.startswith('%')
    # Without [equations], the fragment holds comments only, and a note says so.
    (folder / 'style.toml').write_text('', encoding='utf-8')
    assert cli.main(['draw', str(folder), '--latex', 'none.tex']) == 0
    assert 'note: none.tex' in capsys.readouterr().out
    assert all(
        row.startswith('%') for row in (tmp_path / 'none.tex').read_text(encoding='utf-8').splitlines()
    )
    missing = Path('no-such-folder', 'shop.tex')
    assert cli.main(['draw', str(folder), '--latex', str(missing)]) == 1
    assert str(missing) in capsys.readouterr().err and not (tmp_path / missing).exists()


def test_draw_of_a_package_with_variants_lists_them_and_stops(built, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['draw', str(built.chain)]) == 2
    err = capsys.readouterr().err
    assert all(name in err for name in VARIANTS) and not list(tmp_path.iterdir())


def test_draw_gives_the_problems_of_a_stylesheet(shop, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / 'missing.toml'
    assert cli.main(['draw', str(shop), '--style', str(missing)]) == 1
    assert 'missing.toml' in capsys.readouterr().err
    # The package's own stylesheet, with a table that no stylesheet has.
    (shop / 'style.toml').write_text('[nonsense]\nkey = 1\n', encoding='utf-8')
    assert cli.main(['draw', str(shop)]) == 1
    assert 'style.toml' in capsys.readouterr().err
    assert not list(tmp_path.glob('*.svg'))


def test_draw_of_a_run_that_the_model_does_not_have_is_refused(built, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['draw', str(built.shop), '--run', 'no_such_run']) == 2
    err = capsys.readouterr().err
    assert 'usage: napkin draw' in err and 'no_such_run' in err and not list(tmp_path.glob('*.svg'))


# A desk whose run "robot" names the option that sets the text in the label of its stock: the label is
# the run's text in that run, and the file's own in the others. DESK_FRONT and DESK_BACK are two more
# things, for a stylesheet that groups them.
DESK = f"""\
scenario "A desk"
    summary "A desk where people wait. A synthetic fixture for tests only."
    horizon 10 h
    scope "Fixture"

desk:
    "A desk."
    {FIXTURE}
    role operator
    input who = "the clerk"
    var waiting: people = 10 people size 100 people
        "Wait for {{who}}"
        {FIXTURE}
    flow leave: waiting -> at 1 people/h
        {FIXTURE}

output still_waiting: people = desk.waiting
    "People still waiting"
    level
    {FIXTURE}

options "Staff":
    "Clerk":
        "A clerk."
    "Robot":
        "A robot."
        desk.who = "the robot"

runs:
    robot = "Robot"
"""
DESK_THINGS = f"""\
front:
    "The front desk."
    {FIXTURE}
    role operator

back:
    "The back desk."
    {FIXTURE}
    role operator

"""


def stock_label(path, key):
    """The tooltip of the stock `key` in an SVG that `napkin draw` wrote."""
    import xml.etree.ElementTree as ET

    for g in ET.parse(path).getroot().iter('{http://www.w3.org/2000/svg}g'):
        if g.get('data-stock') == key:
            return g.find('{http://www.w3.org/2000/svg}title').text
    raise AssertionError(key)


def test_draw_of_a_model_with_one_run_draws_that_run(tmp_path, monkeypatch, capsys):
    """Without --run, the only run of a model is the run drawn, so its label takes the run's text; with
    two runs the picture joins them, and the label is the file's own text. The file keeps its name."""
    monkeypatch.chdir(tmp_path)
    one = write(tmp_path / 'desk', {'model.scn': DESK})
    assert cli.main(['draw', str(one)]) == 0
    assert 'the robot' in stock_label(tmp_path / 'desk.svg', 'desk.waiting')
    assert capsys.readouterr().out.startswith('desk.svg')
    two = write(tmp_path / 'two' / 'desk', {'model.scn': DESK + '    clerk = "Clerk"\n'})
    assert cli.main(['draw', str(two), '-o', str(tmp_path / 'two.svg')]) == 0
    label = stock_label(tmp_path / 'two.svg', 'desk.waiting')
    assert 'the clerk' in label and 'the robot' not in label


@pytest.mark.parametrize(
    ('sheet', 'key', 'fixed'),
    [
        # The desk's row is between the rows of the two things of a group: the frame would hold it.
        (
            '[place]\nfront = { column = 1, row = 1 }\ndesk = { column = 1, row = 2 }\n'
            'back = { column = 1, row = 3 }\n\n[group]\n"Ends" = ["front", "back"]\n',
            'place.desk',
            ('desk = { column = 1, row = 2 }', 'desk = { column = 1, row = 4 }'),
        ),
        # The front's group comes second, and its row is above the back's: the frames go down in the
        # order of [group].
        (
            '[place]\nfront = { column = 1, row = 1 }\nback = { column = 1, row = 2 }\n'
            '\n[group]\n"Back" = ["back"]\n"Front" = ["front"]\n',
            'place.front',
            ('front = { column = 1, row = 1 }', 'front = { column = 1, row = 3 }'),
        ),
    ],
)
def test_compile_and_draw_refuse_rows_that_the_frames_cannot_keep(
    tmp_path, napkin_call, monkeypatch, sheet, key, fixed
):
    """Both commands give the problem at the place of the thing, and draw no file; with the thing's row
    changed, the stylesheet holds."""
    monkeypatch.chdir(tmp_path)
    text = DESK.replace('output still_waiting', DESK_THINGS + 'output still_waiting')
    write(tmp_path / 'desk', {'model.scn': text, 'style.toml': sheet})
    for command in ('compile', 'draw'):
        done = napkin_call(command, 'desk')
        assert done.code == 1, command
        assert str(Path('desk', 'style.toml')) in done.err and key in done.err, done.err
    assert not list(tmp_path.glob('*.svg'))
    (tmp_path / 'desk' / 'style.toml').write_text(sheet.replace(*fixed), encoding='utf-8')
    assert napkin_call('compile', 'desk').code == 0


# --- napkin new -------------------------------------------------------------------------------------


def written(folder):
    """{path in the folder: text} of every file in `folder`."""
    return {
        path.relative_to(folder).as_posix(): path.read_text(encoding='utf-8')
        for path in sorted(folder.rglob('*'))
        if path.is_file()
    }


def test_new_writes_a_starter_that_compiles_and_runs_as_written(tmp_path, capsys):
    from napkin.model.language.format import format_text
    from napkin.package import load_package

    folder = tmp_path / 'demo'
    assert cli.main(['new', str(folder)]) == 0
    out = capsys.readouterr().out
    # One file, its own formatted text, and no units or library of its own.
    files = written(folder)
    assert list(files) == [paths.ENTRY]
    assert format_text(files[paths.ENTRY]) == files[paths.ENTRY]
    (model,) = load_package(folder).values()
    # The prelude's units only: no `library` line and no units.json add any.
    assert set(model.library['units']) == set(json.loads(PRELUDE.read_text(encoding='utf-8')))
    # A stock, the tally that one flow fills from it, one input, one output, and one record, an
    # assumption, which every value cites: the model reaches no other record.
    (thing,) = model.scenario.entities
    assert sorted(value.kind for value in thing.values) == ['input', 'stock', 'tally']
    assert len(thing.flows) == 1 and len(model.outputs) == 1
    (record,) = model.scenario.records
    assert record.content['kind'] == 'assumption'
    assert [item['kind'] for item in model.evidence['records'].values()] == ['assumption']
    assert evaluate_study(model).admissible
    # What to replace next: the title, each input and each record of the model.
    assert model.scenario.title in out
    assert model.inputs and all(name in out for name in model.inputs)
    assert record.name in out


def test_the_starters_flow_moves_its_rate_until_the_stock_runs_out(tmp_path):
    from napkin.engine import edits_for
    from napkin.expressions import UnitSystem
    from napkin.package import load_package

    folder = tmp_path / 'demo'
    assert cli.main(['new', str(folder)]) == 0
    (model,) = load_package(folder).values()
    (thing,) = model.scenario.entities
    kinds = {value.kind: value for value in thing.values}
    units = UnitSystem(thaw(model.library['units']))

    def amount(text):
        number, unit = text.split(maxsplit=1)
        return float(number) * units.parse_unit(unit).scale

    stock, tally = amount(kinds['stock'].value), amount(kinds['tally'].value)
    rate = f'{thing.name}.{kinds["input"].name}'
    low, high = model.inputs[rate]['range']
    per_hour = units.parse_unit(model.inputs[rate]['unit']).scale
    horizon = model.time['horizon']
    (outcome,) = model.outputs.values()
    # The rate at which the stock runs out at the end of the run, and rates on each side of it.
    empties = stock / (per_hour * horizon)
    rates = sorted({low, high, *(r for r in (empties / 2, empties * 3 / 2) if low <= r <= high)})
    assert len(rates) >= 3
    for r in rates:
        study = evaluate_study(model, edits_for(model, {'set': {rate: r}}))
        assert study.admissible, study.diagnostics
        (run,) = sample_result(study)['runs'].values()
        final = run['reporting_points']['final']['values'][outcome]
        # The tally is its start plus the rate times the time, until the stock is empty.
        assert final == pytest.approx(tally + min(stock, r * per_hour * horizon), rel=1e-9, abs=1e-9 * stock)


def test_new_with_variants_writes_variants_that_change_one_input(tmp_path, capsys):
    from napkin.model import load_scenario
    from napkin.model.language.format import format_text
    from napkin.package import load_package

    folder = tmp_path / 'demo'
    assert cli.main(['new', '--variants', 'east,west', str(folder)]) == 0
    out = capsys.readouterr().out
    files = written(folder)
    assert set(files) == {
        paths.ENTRY,
        *(f'{paths.VARIANTS}/{name}/{paths.ENTRY}' for name in ('east', 'west')),
    }
    assert all(format_text(text) == text for text in files.values())
    models = load_package(folder)
    assert list(models) == ['demo:east', 'demo:west']
    base = load_scenario(folder / paths.ENTRY)
    changed = set()
    for model in models.values():
        assert evaluate_study(model).admissible
        # The same inputs, one of which has another value; nothing else of the model differs.
        mine, theirs = thaw(model.inputs), thaw(base.inputs)
        assert mine.keys() == theirs.keys()
        (name,) = [name for name in mine if mine[name] != theirs[name]]
        assert {key for key in mine[name] if mine[name][key] != theirs[name][key]} == {'value'}
        changed.add(name)
        ours, others = (
            {starts: structure.plain() for starts, structure in each.structures.items()}
            for each in (model, base)
        )
        for structure in (ours, others):
            for item in structure.values():
                item['parameters'][name].pop('value')
        assert ours == others
        assert model.outputs == base.outputs and thaw(model.time) == thaw(base.time)
    assert len(changed) == 1 and all(name in out for name in changed)


def test_new_refuses_a_model_that_is_there_and_writes_nothing(tmp_path, capsys):
    folder = tmp_path / 'demo'
    assert cli.main(['new', str(folder)]) == 0
    before = written(folder)
    for flags in ([], ['--variants', 'east'], ['--title', 'Another']):
        assert cli.main(['new', *flags, str(folder)]) == 2
        assert written(folder) == before
    # A variant's file that is there is refused too, and the main file is not written.
    other = tmp_path / 'other'
    (other / paths.VARIANTS / 'east').mkdir(parents=True)
    (other / paths.VARIANTS / 'east' / paths.ENTRY).write_text('# mine\n', encoding='utf-8')
    assert cli.main(['new', '--variants', 'west,east', str(other)]) == 2
    assert written(other) == {f'{paths.VARIANTS}/east/{paths.ENTRY}': '# mine\n'}
    # A DIR that is a file.
    (tmp_path / 'file').write_text('', encoding='utf-8')
    assert cli.main(['new', str(tmp_path / 'file')]) == 2
    assert 'usage: napkin new' in capsys.readouterr().err


@pytest.mark.parametrize(
    'flags',
    [
        ['--variants', 'East'],
        ['--variants', '9east'],
        ['--variants', '_east'],
        ['--variants', 'east-side'],
        ['--variants', 'éast'],
        ['--variants', 'ｅast'],
        ['--variants', ''],
        ['--variants', 'east,'],
        ['--variants', 'east,,west'],
        ['--variants', 'east,east'],
        ['--variants', 'east/west'],
        ['--title', 'A "quoted" title'],
        ['--title', ' \t '],
    ],
)
def test_new_refuses_a_bad_variant_name_or_title_and_writes_nothing(tmp_path, flags, capsys):
    folder = tmp_path / 'demo'
    assert cli.main(['new', *flags, str(folder)]) == 2
    assert 'usage: napkin new' in capsys.readouterr().err
    assert not folder.exists()


def test_the_title_of_the_starter_is_the_title_given(tmp_path):
    from napkin.model import load_scenario

    for k, title in enumerate(
        ['A shop', 'Water in “the” valley, {east} # 2', ' Two\tlines\nof  text ', 'é' * 150]
    ):
        folder = tmp_path / f'demo{k}'
        assert cli.main(['new', '--title', title, str(folder)]) == 0
        assert load_scenario(folder / paths.ENTRY).scenario.title == ' '.join(title.split())


def test_napkin_run_prints_the_outcomes_of_the_starter(tmp_path, capsys):
    from napkin.package import load_package

    for flags in ([], ['--variants', 'east,west']):
        folder = tmp_path / f'demo{len(flags)}'
        assert cli.main(['new', *flags, str(folder)]) == 0
        # The command that `napkin new` prints runs the model.
        (line,) = [line for line in capsys.readouterr().out.splitlines() if 'napkin run ' in line]
        argv = shlex.split(line.partition('napkin ')[2])
        assert cli.main([*argv, '--no-store']) == 0
        out = capsys.readouterr().out
        model = load_package(folder)[folder.name + (':east' if flags else '')]
        (run,) = sample_result(evaluate_study(model))['runs'].values()
        for name, outcome in run['outcomes'].items():
            assert outcome['label'] in out
            assert common.number(run['reporting_points']['final']['values'][name]) in out


def test_a_starter_with_a_wrong_line_fails_with_its_file_line_and_column(tmp_path, capsys):
    # A line at the top level that starts no declaration, after the starter's last line: its first
    # word, at the first column, is the problem.
    folder = tmp_path / 'demo'
    assert cli.main(['new', str(folder)]) == 0
    path = folder / paths.ENTRY
    text = path.read_text(encoding='utf-8')
    path.write_text(text + 'not a declaration\n', encoding='utf-8')
    capsys.readouterr()
    assert cli.main(['run', '--no-store', str(folder)]) == 1
    assert f'{paths.ENTRY}:{len(text.splitlines()) + 1}:1: error:' in capsys.readouterr().err


# --- napkin fmt -------------------------------------------------------------------------------------

# The shop with the spacing of two lines changed: the formatter writes each line again from its
# tokens, so it gives the shop's own text back.
MESSY_SHOP = SHOP.replace('    horizon 720 h', '    horizon   720   h').replace(
    'flow serve: waiting -> served at rate', 'flow serve:waiting->served   at rate'
)


def test_fmt_check_reports_an_unformatted_file_and_fmt_formats_it(shop, napkin_call, monkeypatch):
    from napkin.model.language.format import format_text

    entry = shop / 'model.scn'
    assert MESSY_SHOP != SHOP and format_text(MESSY_SHOP) == SHOP
    entry.write_text(MESSY_SHOP, encoding='utf-8')
    monkeypatch.chdir(shop.parent)
    check = napkin_call('fmt', '--check', 'shop')
    assert (check.code, check.out.splitlines()) == (1, [str(Path('shop', 'model.scn'))])
    assert entry.read_text(encoding='utf-8') == MESSY_SHOP  # --check writes nothing
    done = napkin_call('fmt', 'shop')
    assert (done.code, done.out.splitlines()) == (0, [str(Path('shop', 'model.scn'))])
    assert entry.read_text(encoding='utf-8') == SHOP
    again = napkin_call('fmt', '--check', 'shop')
    assert (again.code, again.out) == (0, '')


def formatted_chain(folder):
    """The chain with each of its files formatted, so that a test changes the files that it names."""
    from napkin.model.language.format import format_text

    chain = write_chain(folder)
    for path in chain.rglob('*.scn'):
        path.write_text(format_text(path.read_text(encoding='utf-8')), encoding='utf-8')
    return chain


def test_fmt_is_idempotent_and_writes_only_the_files_that_change(tmp_path, napkin_call):
    from napkin.model.language.format import format_text

    chain = formatted_chain(tmp_path / 'chain')
    parts = chain / 'parts.scn'
    parts.write_text(
        PARTS.replace('flow serve: waiting -> served', 'flow serve:  waiting  ->  served'), encoding='utf-8'
    )
    files = sorted(chain.rglob('*.scn'))
    past = 1_000_000_000
    for path in files:
        os.utime(path, (past, past))
    first = napkin_call('fmt', chain)
    assert first.code == 0 and [Path(line).name for line in first.out.splitlines()] == ['parts.scn']
    changed = {path for path in files if path.stat().st_mtime != past}
    assert changed == {parts}
    texts = {path: path.read_text(encoding='utf-8') for path in files}
    assert all(format_text(text) == text for text in texts.values())
    for path in files:
        os.utime(path, (past, past))
    second = napkin_call('fmt', chain)
    assert (second.code, second.out) == (0, '')
    assert all(
        path.stat().st_mtime == past and path.read_text(encoding='utf-8') == texts[path] for path in files
    )


def test_fmt_gives_the_file_line_and_column_of_a_syntax_error(shop, napkin_call, monkeypatch):
    entry = shop / 'model.scn'
    # A text without its closing quote, under an output at the end of the file: the text starts at the
    # fifth column of the line after the file's last line.
    text = SHOP + 'output more: people = 1 people\n    "no closing quote\n'
    entry.write_text(text, encoding='utf-8')
    monkeypatch.chdir(shop.parent)
    for argv in (['fmt', 'shop'], ['fmt', '--check', 'shop']):
        done = napkin_call(*argv)
        assert done.code == 1
        assert done.err.startswith(f'{Path("shop", "model.scn")}:{len(SHOP.splitlines()) + 2}:5: error: ')
    assert entry.read_text(encoding='utf-8') == text
    # A file that is not UTF-8 text is refused with its file too.
    entry.write_bytes(SHOP.encode('utf-8') + b'# \xff\n')
    done = napkin_call('fmt', 'shop')
    assert done.code == 1 and done.err.startswith(f'{Path("shop", "model.scn")}: error: ')


def test_fmt_takes_the_package_of_the_current_folder(tmp_path, napkin_call, monkeypatch):
    chain = formatted_chain(tmp_path / 'chain')
    (chain / 'parts.scn').write_text(
        PARTS.replace('    role operator', '    role   operator'), encoding='utf-8'
    )
    # A folder whose name starts with a dot is not searched.
    write(chain, {'.hidden/model.scn': 'not   formatted\n'})
    monkeypatch.chdir(chain / 'variants' / 'east')
    done = napkin_call('fmt', '--check')
    assert done.code == 1 and [Path(line).name for line in done.out.splitlines()] == ['parts.scn']
    assert all('.hidden' not in line for line in done.out.splitlines() + done.err.splitlines())
    monkeypatch.chdir(tmp_path)
    assert napkin_call('fmt', '--check').code == 2  # no package holds the folder


@pytest.mark.parametrize('kind', ['missing', 'other file'])
def test_fmt_refuses_a_path_that_is_no_scn_file_or_folder(built, tmp_path, napkin_call, kind):
    path = tmp_path / 'missing.scn' if kind == 'missing' else built.shop / 'units.json'
    done = napkin_call('fmt', path)
    assert done.code == 2 and 'usage: napkin fmt' in done.err
