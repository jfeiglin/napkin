"""The runs of a model file: input values by profiles and edits, and the checks of an edit document.

A synthetic file has three groups of profiles (Response, Damage and Attacker), inputs that profiles
set in entities and in an instance of a template, a fixed value, a
yes/no input, a unit that names a text value and a set of copies. Every expectation follows from the rule of
the edit document, applied by the test to values that it sets itself or reads from the file: the
narrower edit wins (one run, then one option, then every run), every edit wins over a profile's own
value, and that wins over the default.
"""

from __future__ import annotations

import itertools
import math
from functools import cache

import pytest

from napkin import SCHEMA_VERSION, distributions
from napkin.model import ModelError
from napkin.model.ir import freeze, thaw
from napkin.model.language import front
from napkin.model.language.resolve import resolve
from napkin.model.runs import Runs
from napkin.model.semantic import Entity, Group, Profile, Range, Run, Scenario, Setting, Value
from tests.build import compiled, edit, library, number_of, replace
from tests.helpers import SCENARIO_IDS, catalogue_model


def runs_library():
    """The test library with the units of the fixture's work and its costs."""
    lib = library()
    lib['units'].update(
        {
            'claims/h': {'dimensions': {'claims': 1, 'time': -1}, 'scale': 1},
            'authorizations/h': {'dimensions': {'authorizations': 1, 'time': -1}, 'scale': 1},
            'USD2025_bn': {'dimensions': {'USD2025': 1}, 'scale': 1e9},
        }
    )
    return lib


LIB = runs_library()

FIXTURE = """\
scenario "Runs fixture"
    summary "A synthetic plant that options and edits change. A fixture for tests only."
    horizon 100 h

plant:
    "A plant."
    role operator
    input rate = 0.5 per_h in 0.1 per_h to 2 per_h  @ident
        "Rate"
    input delay = 10 h in 1 h to 100 h  @ident
        "Delay"
    let size = 1000 people  @ident
        "Size"
    input backup = true  @ident
        "Backup in place"
    input cost = 1 USD2025_bn in 0 USD2025_bn to 1e+300 USD2025_bn  @ident
        "Cost"
    var status: "up" | "down" = "up"
    var held: people = size  @ident
        "Held"

attacker:
    "An attacker."
    role adversary
    input actor = "The AI"
    input pace = 1 h in 0.5 h to 50 h  @ident
        "Pace"

Channel:
    "A channel of work."
    role operator
    input item = "claims"
    input flow = 100 {item}/h in 0 {item}/h to 1000 {item}/h  @ident
        "Flow"
    let share: fraction = 0.5  @ident
        "Share"

first: Channel
    input share: fraction = 0.25 in 0 to 1  @ident

second: Channel
    item = "authorizations"

Wave:
    "One wave of work."
    role operator
    input size = 10 people in 0 people to 100 people  @ident
        "Wave size"

waves: Wave * 2

options "Response":
    "Slow":
        "The plant reacts slowly."
    "Fast":
        "The plant reacts fast."
        plant.delay = 2 h  @ident
        plant.backup = false  @ident
        second.flow = 500 {item}/h  @ident

options "Damage":
    "Intact":
        "Nothing breaks."
    "Broken":
        "The plant breaks."
        plant.status = "down"  @ident
        plant.held = 0 people  @ident

options "Attacker":
    "AI agent":
        "An AI agent."
    "Human team":
        "A human team."
        attacker.pace = 24 h  @ident
        attacker.actor = "The human team"

runs:
    slow = "Slow" + "Intact"
    fast = "Fast" + "Intact"
    slow_broken = "Slow" + "Broken"
    fast_broken_human = "Fast" + "Broken" + "Human team"
        "Fast · Human team breaks the plant"

record ident: identity "Synthetic test fixture."
"""


@cache
def model(text=FIXTURE):
    """The model of a text, built with `LIB`: the build checks every rule of the file."""
    return compiled(text, LIB)


def runs_of(text=FIXTURE):
    """The run table of a text, read from the semantic model of its model."""
    built = model(text)
    return Runs.from_scenario(built.scenario, built.library)


def unbuilt(text):
    """The run table of a text that the build rejects, read from the semantic model that the front end
    gives before the build checks it."""
    semantic, _ = resolve(front.read(text, 'RUNS.scn'), thaw(LIB))
    return Runs.from_scenario(semantic, LIB)


def edits(**levels):
    return {'schema_version': SCHEMA_VERSION, 'model_hash': 'm', **levels}


def codes(problems):
    return sorted({p['code'] for p in problems})


def declared(entity, name, text=FIXTURE):
    """A value of an entity as the file declares it (`semantic.Value`)."""
    return model(text).scenario.entity(entity).value(name)


def own(entity, name, profile):
    """The value, as the file writes it, that `profile` gives a value of an entity."""
    return next(setting.value for setting in declared(entity, name).settings if setting.profile == profile)


def chosen(text=FIXTURE):
    """{run: its profiles}, as the file writes them."""
    return {run.name: tuple(run.profiles) for run in model(text).scenario.runs}


def test_the_fixture_is_a_valid_document():
    """The fixture builds, so it keeps every rule of the file, and its run table has no problem."""
    compiled(FIXTURE, LIB)
    assert runs_of().problems == []


# ---- precedence --------------------------------------------------------------------------------

LEVEL_VALUES = {'set': 11, 'options': 22, 'runs': 44}
NARROWEST_FIRST = ('runs', 'options', 'set')


def edit_values(item):
    """Three valid edit values, distinct whenever the input's domain permits it."""
    if item.names is not None:
        values = itertools.islice(itertools.cycle(item.names), 3)
    else:
        low, high = item.range
        values = (low + (high - low) * f for f in (0, 1 / 2, 1))
    return dict(zip(('set', 'options', 'runs'), values))


@pytest.mark.parametrize('names', [None, ('a', 'b'), ('a', 'b', 'c', 'd')], ids=['numeric', 'two', 'four'])
@pytest.mark.parametrize(
    'levels', [c for k in range(4) for c in itertools.combinations(NARROWEST_FIRST, k)], ids=str
)
def test_the_narrowest_edit_that_reaches_a_run_wins(levels, names):
    """Every subset of the three levels edits plant.delay with its own value. Each level reaches the
    runs that the rule says (every run; the runs that name the option; the one run), and in each run
    the narrowest level that reaches it gives the value."""
    text = FIXTURE
    if names is not None:
        domain = ' | '.join(f'"{name}"' for name in names)
        text = edit(
            text,
            replace(
                'input delay = 10 h in 1 h to 100 h  @ident',
                f'input delay: {domain} = "{names[0]}"  @ident',
            ),
            replace('plant.delay = 2 h  @ident', f'plant.delay = "{names[-1]}"  @ident'),
        )
    table = runs_of(text)
    values = LEVEL_VALUES if names is None else edit_values(table.inputs['plant.delay'])
    runs = chosen(text)
    single = 'fast_broken_human'
    reach = {
        'set': set(runs),
        'options': {r for r, options in runs.items() if 'Fast' in options},
        'runs': {single},
    }
    key = 'plant.delay'
    body = {}
    if 'set' in levels:
        body['set'] = {key: values['set']}
    if 'options' in levels:
        body['options'] = {'Fast': {key: values['options']}}
    if 'runs' in levels:
        body['runs'] = {single: {key: values['runs']}}
    resolved = table.resolve(edits(**body) if body else None)
    delay = declared('plant', 'delay', text)
    read = number_of if names is None else lambda value: value
    own_values = {setting.profile: read(setting.value) for setting in delay.settings}
    for run, options in runs.items():
        winner = next((level for level in NARROWEST_FIRST if level in levels and run in reach[level]), None)
        if winner is not None:
            expected, origin = values[winner], winner
        else:
            setters = [p for p in options if p in own_values]
            expected = own_values[setters[0]] if setters else read(delay.value)
            origin = 'option' if setters else 'default'
        assert resolved[run].values[key] == expected, (levels, run)
        assert resolved[run].origins[key][0] == origin, (levels, run)


def test_an_edit_wins_over_the_value_of_an_option_and_reaches_no_other_input():
    plain = runs_of().resolve()
    edited = runs_of().resolve(edits(set={'plant.delay': 7}))
    for run, options in chosen().items():
        # Without edits, a run that names Fast takes its values; the others take the defaults.
        written = own('plant', 'delay', 'Fast') if 'Fast' in options else declared('plant', 'delay').value
        assert plain[run].values['plant.delay'] == number_of(written)
        assert edited[run].values['plant.delay'] == 7
        changed = {k for k, v in edited[run].values.items() if v != plain[run].values[k]}
        assert changed <= {'plant.delay'}


def test_an_option_of_an_entity_adds_to_its_class_and_reaches_only_that_entity():
    resolved = runs_of().resolve()
    entity = number_of(own('second', 'flow', 'Fast'))
    default = number_of(declared('second', 'flow').value)
    for run, options in chosen().items():
        named = 'Fast' in options
        assert resolved[run].values['second.flow'] == (entity if named else default)
        assert resolved[run].values['first.flow'] == default


def test_a_bool_input_reads_true_or_false_and_takes_booleans():
    resolved = runs_of().resolve()
    for run, options in chosen().items():
        written = own('plant', 'backup', 'Fast') if 'Fast' in options else declared('plant', 'backup').value
        assert resolved[run].values['plant.backup'] is written
    flipped = runs_of().resolve(edits(runs={'fast': {'plant.backup': True}}))
    assert flipped['fast'].values['plant.backup'] is True


def test_each_copy_is_an_input_of_its_own():
    resolved = runs_of().resolve(edits(set={'waves.2.size': 55}))
    for result in resolved.values():
        assert result.values['waves.2.size'] == 55
        assert result.values['waves.1.size'] == number_of(declared('waves.1', 'size').value)


def test_options_set_start_states_and_texts_and_edits_do_not():
    resolved = runs_of().resolve()
    for run, options in chosen().items():
        for name in ('status', 'held'):
            expected = own('plant', name, 'Broken') if 'Broken' in options else declared('plant', name).value
            assert resolved[run].starts[f'plant.{name}'] == expected
        human = 'Human team' in options
        actor = own('attacker', 'actor', 'Human team') if human else declared('attacker', 'actor').value
        assert resolved[run].texts['attacker.actor'] == actor
    for key in ('plant.status', 'plant.held', 'attacker.actor'):
        assert codes(runs_of().errors(edits(set={key: 1}))) == ['input']


# ---- edits that meet ---------------------------------------------------------------------------


def test_two_option_edits_of_one_input_that_meet_in_a_run_are_rejected_even_when_equal():
    runs = runs_of()
    for first, second in ((1.5, 0.5), (1.0, 1.0)):
        body = edits(options={'Fast': {'plant.rate': first}, 'Broken': {'plant.rate': second}})
        problems = runs.errors(body)
        assert codes(problems) == ['meeting']
        with pytest.raises(ModelError):
            runs.resolve(body)


def test_option_edits_that_meet_only_in_a_combination_are_checked_when_it_is_asked_for():
    """No run names Slow with Human team: their edits of one input meet in no declared run, so the
    document holds as one transaction over the runs. Slow with the other options of
    fast_broken_human is a combination that no run makes: asked for, it is the one run of its own
    model, where the two edits meet."""
    assert not any({'Slow', 'Human team'} <= set(options) for options in chosen().values())
    body = edits(options={'Slow': {'plant.rate': 1.5}, 'Human team': {'plant.rate': 0.5}})
    assert runs_of().errors(body) == []
    combined = model().combination('fast_broken_human', ['Slow'])
    assert combined.runs['fast_broken_human']['options'] == ('Slow', 'Broken', 'Human team')
    problems = Runs.from_table(combined.run_table).errors(body)
    assert codes(problems) == ['meeting']
    assert problems[0]['path'] == 'edits/options/Human team/plant.rate'


def renamed(name):
    """The file with the group Response under another name."""
    return edit(FIXTURE, replace('options "Response":', f'options "{name}":'))


def test_the_name_of_a_group_changes_no_check_of_the_edits():
    """A group's name has no meaning in the language: under another name, every edit document is
    decided the same, and the build checks the same choices of the options that no run names."""
    bodies = (
        edits(options={'Slow': {'plant.rate': 1.5}, 'Human team': {'plant.rate': 0.5}}),
        edits(options={'Fast': {'plant.rate': 1.5}, 'Broken': {'plant.rate': 0.5}}),
    )
    for text in (renamed('Defence'),):
        model(text)
        assert runs_of(text).unnamed_choices() == runs_of().unnamed_choices()
        for body in bodies:
            assert runs_of(text).errors(body) == runs_of().errors(body)
    assert [codes(runs_of().errors(body)) for body in bodies] == [[], ['meeting']]


@pytest.mark.parametrize(
    'body',
    [
        {'options': {'Slow': {'plant.rate': 1.5}, 'Fast': {'plant.rate': 0.5}}},
        {'options': {'Intact': {'plant.rate': 1.5}, 'Broken': {'plant.rate': 0.5}}},
        {
            'set': {'plant.rate': 1},
            'options': {'Fast': {'plant.rate': 2}},
            'runs': {'fast': {'plant.rate': 0.2}},
        },
    ],
    ids=['response options', 'options of one group', 'different levels'],
)
def test_edits_that_never_meet_at_one_level_are_accepted(body):
    assert runs_of().errors(edits(**body)) == []


# ---- checks of single edits ----------------------------------------------------------------------


def test_a_range_is_closed_and_the_value_outside_it_is_rejected():
    low, high = (number_of(edge) for edge, _ in declared('plant', 'delay').range.edges)
    for value in (low, high):
        assert runs_of().errors(edits(set={'plant.delay': value})) == []
    for value in (low - 1e-9 * max(1, abs(low)), high + 1e-9 * max(1, abs(high))):
        assert codes(runs_of().errors(edits(set={'plant.delay': value}))) == ['bounds']


@pytest.mark.parametrize(
    ('key', 'value', 'code'),
    [
        ('plant.size', 1000, 'locked'),
        ('second.share', 0.5, 'locked'),
        ('plant.backup', 1, 'bool'),
        ('plant.backup', 0, 'bool'),
        ('plant.delay', True, 'value'),
        ('plant.delay', math.inf, 'value'),
        ('plant.nothing', 1, 'input'),
        ('nobody.delay', 1, 'input'),
        ('plant.cost', 1e300, 'unit'),
    ],
)
def test_an_edit_needs_an_input_and_a_value_of_its_kind(key, value, code):
    """A fixed value is locked, even at its own value; a yes/no input takes booleans only; a number
    must be finite and must stay finite in execution units (1e300 billion dollars does not)."""
    for level in ('set', 'options', 'runs'):
        body = {
            'set': {'set': {key: value}},
            'options': {'options': {'Fast': {key: value}}},
            'runs': {'runs': {'slow': {key: value}}},
        }[level]
        assert codes(runs_of().errors(edits(**body))) == [code], level


def test_an_entity_can_make_a_fixed_field_of_its_class_an_input():
    assert runs_of().errors(edits(set={'first.share': 1})) == []
    assert codes(runs_of().errors(edits(set={'second.share': 1}))) == ['locked']


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'options': {'Quick': {'plant.rate': 1}}}, 'reference'),
        ({'runs': {'fastest': {'plant.rate': 1}}}, 'reference'),
        # A key of an earlier edit format is no key: version 0.0.1 has `options` and no list of runs.
        ({'scenario_set': {'rate': 1}}, 'schema'),
        ({'presets': {'Fast': {'plant.rate': 1}}}, 'schema'),
        ({'lists': [{'runs': ['slow'], 'set': {'plant.rate': 1}}]}, 'schema'),
        ({'set': {'plant': 1}}, 'schema'),
        # A text is a name or a distribution: a number input takes neither '1' nor a name.
        ({'set': {'plant.rate': '1'}}, 'value'),
        ({'set': {'plant.rate': ''}}, 'schema'),
    ],
)
def test_an_edit_document_names_options_runs_and_inputs_that_exist(body, code):
    assert codes(runs_of().errors(edits(**body))) == [code]


def test_an_edit_of_an_option_that_no_run_names_is_accepted_and_changes_no_run():
    """No run names AI agent: an edit of it is no problem of the document, it changes the value of no
    run, and a combination that names the option takes it."""
    assert not any('AI agent' in options for options in chosen().values())
    runs = runs_of()
    body = edits(options={'AI agent': {'plant.rate': 1}})
    assert runs.errors(body) == []
    assert runs.resolve(body) == runs.resolve()
    options, problems = runs.combination('slow', ['AI agent'])
    assert (options, problems) == (('Slow', 'Intact', 'AI agent'), [])
    taken = runs.values_of(options, body, 'slow')
    assert (taken.values['plant.rate'], taken.origins['plant.rate']) == (1, ('options', 'AI agent'))


def test_the_edit_document_has_its_version_and_the_model_revision():
    runs = runs_of()
    body = edits(set={'plant.rate': 1})
    assert runs.errors(body, 'm') == []
    assert codes(runs.errors(body, 'other')) == ['model_hash']
    # The version of an earlier edit format is refused: there is no reader of it.
    for key, value in (('schema_version', '5'), ('model_hash', '')):
        assert codes(runs.errors({**body, key: value})) == ['schema']
    for key in ('schema_version', 'model_hash'):
        bare = {k: v for k, v in body.items() if k != key}
        assert codes(runs.errors(bare)) == ['schema']


def test_an_edit_document_is_one_transaction():
    """A problem in one run rejects the edits for every run, also when one other run is asked for."""
    body = edits(set={'plant.rate': 1}, runs={'fast': {'plant.delay': 1000}})
    with pytest.raises(ModelError) as rejected:
        runs_of().resolve(body, ['slow'])
    assert codes(rejected.value.diagnostics) == ['bounds']
    assert rejected.value.diagnostics[0]['path'] == 'edits/runs/fast/plant.delay'


def test_a_frozen_document_and_frozen_edits_resolve_as_plain_ones():
    """A compiled model hands out frozen data: its run table, and frozen edits, resolve as the plain
    table of its semantic model and plain edits do."""
    body = edits(set={'plant.rate': 1}, options={'Fast': {'plant.backup': True}})
    plain = runs_of().resolve(body)
    frozen = Runs.from_table(model().run_table).resolve(freeze(body))
    assert frozen == plain


# ---- the file's own values ------------------------------------------------------------------------

RATE = 'input rate = 0.5 per_h in 0.1 per_h to 2 per_h  @ident'


@pytest.mark.parametrize(
    ('change', 'code'),
    [
        (lambda t: edit(t, replace('plant.delay = 2 h  @ident', 'plant.delay = 1000 h  @ident')), 'bounds'),
        (
            lambda t: edit(
                t, replace('second.flow = 500 {item}/h  @ident', 'second.flow = -1 {item}/h  @ident')
            ),
            'bounds',
        ),
        (lambda t: edit(t, replace(RATE, 'input rate = 5 per_h in 0.1 per_h to 2 per_h  @ident')), 'bounds'),
        (lambda t: edit(t, replace('in 0.1 per_h to 2 per_h', 'in 2 per_h to 0.1 per_h')), 'bounds'),
        # A bare number is a number of its value's unit only when that unit is dimensionless.
        (lambda t: edit(t, replace(RATE, 'input rate: per_h = 0.5 in 0.1 per_h to 2 per_h  @ident')), 'unit'),
        (
            lambda t: edit(
                t, replace(RATE, 'input rate: per_h = 0.5 people in 0.1 per_h to 2 per_h  @ident')
            ),
            'unit',
        ),
        # An input of a number with no range.
        (lambda t: edit(t, replace(RATE, 'input rate = 0.5 per_h  @ident')), 'bounds'),
        (
            lambda t: edit(
                t, replace(RATE, 'input rate: furlongs = 0.5 per_h in 0.1 per_h to 2 per_h  @ident')
            ),
            'unit',
        ),
        (lambda t: edit(t, replace('item = "authorizations"', 'item = "parcels"')), 'unit'),
    ],
)
def test_the_defaults_and_option_values_of_inputs_are_checked(change, code):
    runs = unbuilt(change(FIXTURE))
    assert codes(runs.problems) == [code]
    with pytest.raises(ModelError):
        runs.resolve()


def test_a_unit_can_name_the_text_field_of_its_own_entity():
    runs = runs_of()
    for entity in ('first', 'second'):
        item = declared(entity, 'item').value
        assert runs.inputs[f'{entity}.flow'].unit == f'{item}/h'


def test_the_run_table_reads_a_semantic_model_that_no_file_wrote():
    # Code, not a file, gives the run table its semantic model. Its braces name a text value as
    # `{item}`; a profile gives a value in another unit of the dimension, written bare.
    units = {
        'units': {
            'h': {'dimensions': {'time': 1}, 'scale': 1},
            'days': {'dimensions': {'time': 1}, 'scale': 24},
            'claims/h': {'dimensions': {'claims': 1, 'time': -1}, 'scale': 1},
        }
    }

    def value(name, kind, written_type, written, edges=None, settings=()):
        where = ('crew', name)
        listed = (
            None
            if edges is None
            else Range(tuple((e, (*where, 'range', i)) for i, e in enumerate(edges)), None, (*where, 'range'))
        )
        return Value(
            name=name,
            kind=kind,
            type=written_type,
            text=name,
            value=written,
            range=listed,
            records=None,
            settings=tuple(Setting(p, freeze(w), ('profiles', p, name)) for p, w in settings),
            where=where,
            value_where=where,
            range_where=(*where, 'range'),
            type_where=where,
        )

    values = (
        value('item', 'text', 'text', 'claims'),
        value(
            'flow',
            'input',
            '{item}/h',
            '3 {item}/h',
            ('1 {item}/h', '200 {item}/h'),
            [('Fast', {'value': '120 {item}/h'})],
        ),
        value('delay', 'input', 'h', '12 h', ('1 h', '10 days'), [('Slow', '3 days')]),
        value(
            'spread',
            'input',
            '{item}/h',
            'pert(1 {item}/h, 3 {item}/h, 9 {item}/h)',
            ('0 {item}/h', '10 {item}/h'),
        ),
    )
    menu = Group('Pace', tuple(Profile(p, f'{p}.', ('profiles', p)) for p in ('Slow', 'Fast')), ('profiles',))
    scenario = Scenario(
        (menu,),
        (Run('slow', ('Slow',), ('runs', 'slow')), Run('fast', ('Fast',), ('runs', 'fast'))),
        (Entity('crew', 'crew', None, None, values, ('crew',)),),
    )
    runs = Runs.from_scenario(scenario, units)
    assert runs.problems == []
    assert runs.inputs['crew.flow'].unit == 'claims/h'
    # 10 days are 240 h, and 3 days are 72 h.
    assert runs.inputs['crew.delay'].range == (1, 240)
    spread = runs.inputs['crew.spread'].value
    assert distributions.support(spread['family'], spread['args']) == (1, 9)
    by_run = runs.resolve()
    assert {k: v for k, v in by_run['slow'].values.items() if k != 'crew.spread'} == {
        'crew.flow': 3,
        'crew.delay': 72,
    }
    assert {k: v for k, v in by_run['fast'].values.items() if k != 'crew.spread'} == {
        'crew.flow': 120,
        'crew.delay': 12,
    }
    assert runs.texts == {'crew.item': 'claims'}


# ---- the catalogue ------------------------------------------------------------------------------


def catalogue():
    """(ID, the run table of its model) of each scenario of the catalogue."""
    for sid in SCENARIO_IDS:
        built = catalogue_model(sid)
        yield sid, Runs.from_scenario(built.scenario, built.library)


@pytest.mark.scenario_contract
def test_every_run_of_the_catalogue_resolves_within_its_ranges():
    for sid, runs in catalogue():
        assert runs.problems == [], sid
        for run, result in runs.resolve().items():
            for key, value in result.values.items():
                item = runs.inputs[key]
                if item.is_bool:
                    assert isinstance(value, bool), (sid, run, key)
                elif item.range is not None and isinstance(value, dict):
                    # A distribution: its whole support lies in the range.
                    low, high = distributions.support(value['family'], value['args'])
                    assert item.range[0] <= low <= high <= item.range[1], (sid, run, key)
                elif item.range is not None:
                    assert item.range[0] <= value <= item.range[1], (sid, run, key)
                origin = result.origins[key]
                # Without edits a value is the default or the value of a profile that the run names.
                assert origin == ('default',) or (origin[0] == 'option' and origin[1] in result.options)
                if origin == ('default',):
                    assert value == item.value, (sid, run, key)


@pytest.mark.scenario_contract
def test_every_option_that_no_run_names_combines_with_the_other_options_of_every_run():
    """The build checks each option that no run names with the other options of each run."""
    for sid, runs in catalogue():
        choices = {frozenset(options) for options in (*runs.runs.values(), *runs.unnamed_choices())}
        for option in runs.unnamed():
            group = runs.group_of[option]
            for options in runs.runs.values():
                others = [p for p in options if runs.group_of[p] != group]
                assert frozenset([option, *others]) in choices, (sid, option)


@pytest.mark.scenario_contract
def test_the_narrowest_level_wins_on_every_catalogue_scenario():
    """For each scenario, an input that an option of a run sets is edited at every level, with three
    valid values from its domain; each run takes the value and origin of the narrowest level that
    reaches it, even when a small categorical domain requires repeated values."""
    for sid, runs in catalogue():
        named = {p for options in runs.runs.values() for p in options}
        key, option = next(
            (k, p) for k, item in runs.inputs.items() for p in item.options if p in named and not item.is_bool
        )
        values = edit_values(runs.inputs[key])
        single = sorted(runs.runs)[-1]
        body = edits(
            set={key: values['set']},
            options={option: {key: values['options']}},
            runs={single: {key: values['runs']}},
        )
        for run, result in runs.resolve(body).items():
            level = 'runs' if run == single else 'options' if option in runs.runs[run] else 'set'
            assert result.values[key] == values[level], (sid, run)
            assert result.origins[key][0] == level, (sid, run)
