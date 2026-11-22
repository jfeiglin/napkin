"""Options, named runs and the edit document (`napkin/model/runs.py`): the configuration of one run of
a model (D9), with the precedence and the conflicts of R-A5-03, an option that sets only an input
(R-A5-04), a record for each number or yes/no that it sets (R-A5-05) and values of the declared type
(D2). Each expected configuration follows from the rules, applied by the test to values that it writes
itself.

The fixture is a plant whose options set its rate, its delay, its backup, its mode, the text of its
actor and the flows of two channels, one of them through every member of its template."""

from __future__ import annotations

import itertools

import pytest

from napkin import SCHEMA_VERSION
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.canonical import configuration_bytes
from napkin.program.config import Quantity
from napkin.program.refs import Distribution, EnumValue

UNITS = {
    'L': {'volume': 1},
    'h': {'time': 1},
    'L/h': {'volume': 1, 'time': -1},
    'days': ({'time': 1}, 24),
}

FIXTURE = """\
scenario "Plant"
    horizon 10 h

plant:
    "A plant."
    input rate: L/h = 2 L/h in [1 L/h, 8 L/h]  @ident
    input delay: h = 10 h in [1 h, 100 h]  @ident
    input backup = true  @ident
    input mode: enum[CALM, BUSY] = CALM
    input actor: text = "The AI"
    input repair = uniform(1 h, 3 h)  @ident
    held: L = 0 L in [0 L,]
    flow fill: SOURCE -> this.held
        request = this.rate

Channel:
    input pace: L/h = 1 L/h in [0 L/h, 10 L/h]  @ident

first: Channel

second: Channel
    pace = 3 L/h  @ident

options "Response":
    "Slow":
        "The plant reacts slowly."
    "Fast":
        "The plant reacts fast."
        plant.delay = 2 h  @ident
        plant.backup = false  @ident
        second.pace = 5 L/h  @ident

options "Damage":
    "Intact":
        "Nothing breaks."
    "Broken":
        "The plant breaks."
        plant.mode = BUSY
        Channel.instances.pace = 0.5 L/h  @ident

options "Attacker":
    "AI agent":
        "An AI agent."
    "Human team":
        "A human team."
        plant.actor = "The human team"
        plant.rate = 4 L/h  @ident
        plant.repair = pert(2 h, 4 h, 8 h)  @ident

runs:
    slow = "Slow" + "Intact"
    fast = "Fast" + "Intact"
    slow_broken = "Slow" + "Broken"
    fast_broken_human = "Fast" + "Broken" + "Human team"
        "Fast · Human team breaks the plant"

record ident: assumption "A synthetic test fixture."
"""

RUNS = {
    'slow': ('Slow', 'Intact'),
    'fast': ('Fast', 'Intact'),
    'slow_broken': ('Slow', 'Broken'),
    'fast_broken_human': ('Fast', 'Broken', 'Human team'),
}


def compiled(text=FIXTURE):
    return compile_text(text, UNITS)


MODEL = compiled()


def document(**levels):
    return {'schema_version': SCHEMA_VERSION, 'model_hash': MODEL.model_hash, **levels}


def inputs(run=None, edits=None, options=None, model=MODEL):
    """{(member, input): value} of the configuration of a run."""
    return {(item.member, item.name): item.value for item in model.configure(run, edits, options).inputs}


def refused(*args, **kwargs):
    with pytest.raises(LanguageError) as caught:
        MODEL.configure(*args, **kwargs)
    return caught.value.codes


def problems(text):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    return [(item.code, item.line) for item in caught.value.problems]


def line_of(text, words):
    return next(k for k, row in enumerate(text.split('\n'), 1) if row.strip().startswith(words))


def litres(number):
    return Quantity(number, 'L/h')


# ---- the options of a run -------------------------------------------------------------------------


def test_a_named_run_records_its_enum_and_text_options_as_written():
    from napkin import read, run

    config = MODEL.configure('fast_broken_human')
    record = run(MODEL.program, config)
    assert record.failure is None and record.end == 10
    mode, actor, delay = read(record, MODEL.program, ['plant.mode', 'plant.actor', 'plant.delay'], [0, 10])
    assert mode.values == ('BUSY', 'BUSY')
    assert actor.values == ('The human team', 'The human team')
    assert delay.values == (2, 2)


def test_the_default_run_takes_the_model_as_written_and_a_run_its_options():
    assert inputs() == {}
    assert inputs('slow') == {}
    assert inputs('fast') == {
        ('plant', 'delay'): Quantity(2, 'h'),
        ('plant', 'backup'): False,
        ('second', 'pace'): litres(5),
    }
    # A line of every member of a template sets each member; a line of one member wins over it.
    assert inputs('fast_broken_human') == {
        ('plant', 'delay'): Quantity(2, 'h'),
        ('plant', 'backup'): False,
        ('plant', 'mode'): EnumValue('enum[CALM, BUSY]', 'BUSY'),
        ('plant', 'actor'): 'The human team',
        ('plant', 'rate'): litres(4),
        ('plant', 'repair'): Distribution('pert', (2, 4, 8), 'h'),
        ('first', 'pace'): litres(0.5),
        ('second', 'pace'): litres(5),
    }
    assert MODEL.declared.run('fast_broken_human').text == 'Fast · Human team breaks the plant'
    assert MODEL.declared.option('Broken').text == 'The plant breaks.'


def test_the_inputs_of_a_configuration_are_in_order_and_in_their_own_units():
    """Two equal values give one configuration, so one key of a stored run: 2 days and 48 h."""
    in_days = compiled(FIXTURE.replace('plant.delay = 2 h', 'plant.delay = 2 days'))
    in_hours = compiled(FIXTURE.replace('plant.delay = 2 h', 'plant.delay = 48 h'))
    assert configuration_bytes(in_days.configure('fast')) == configuration_bytes(in_hours.configure('fast'))
    found = MODEL.configure('fast_broken_human').inputs
    assert [(item.member, item.name) for item in found] == sorted((item.member, item.name) for item in found)


# ---- precedence -----------------------------------------------------------------------------------

LEVEL_VALUES = {'set': 11, 'options': 22, 'runs': 44}
NARROWEST_FIRST = ('runs', 'options', 'set')


@pytest.mark.parametrize(
    'levels', [c for k in range(4) for c in itertools.combinations(NARROWEST_FIRST, k)], ids=str
)
def test_the_narrowest_edit_that_reaches_a_run_wins(levels):
    """Every subset of the three levels edits plant.delay with its own value. Each level reaches the
    runs that the rule says (every run; the runs that take the option; the one run), and in each run the
    narrowest level that reaches it gives the value; else the run's option, else the model's own."""
    single, key = 'fast_broken_human', 'plant.delay'
    reach = {'set': set(RUNS), 'options': {r for r, o in RUNS.items() if 'Fast' in o}, 'runs': {single}}
    body = {}
    if 'set' in levels:
        body['set'] = {key: LEVEL_VALUES['set']}
    if 'options' in levels:
        body['options'] = {'Fast': {key: LEVEL_VALUES['options']}}
    if 'runs' in levels:
        body['runs'] = {single: {key: LEVEL_VALUES['runs']}}
    for run, options in RUNS.items():
        winner = next((level for level in NARROWEST_FIRST if level in levels and run in reach[level]), None)
        expected = LEVEL_VALUES[winner] if winner else (2 if 'Fast' in options else None)
        found = inputs(run, document(**body)).get(('plant', 'delay'))
        assert found == (None if expected is None else Quantity(expected, 'h')), (levels, run)


def test_an_edit_wins_over_an_option_and_reaches_no_other_input():
    for run in RUNS:
        plain, edited = inputs(run), inputs(run, document(set={'plant.delay': 7}))
        assert edited.pop(('plant', 'delay')) == Quantity(7, 'h')
        plain.pop(('plant', 'delay'), None)
        assert edited == plain


def test_an_edit_of_every_member_of_a_template_and_of_one_member():
    """At one level a line of one member wins over a line of every member of its template; a narrower
    level wins over both."""
    body = document(
        set={'Channel.instances.pace': 6, 'first.pace': 7}, runs={'slow': {'Channel.instances.pace': 8}}
    )
    assert inputs('fast', body)[('first', 'pace')] == litres(7)
    assert inputs('fast', body)[('second', 'pace')] == litres(6)
    assert inputs('slow', body)[('first', 'pace')] == inputs('slow', body)[('second', 'pace')] == litres(8)


def test_an_edit_of_an_option_that_no_run_takes_changes_no_run_and_reaches_a_combination():
    body = document(options={'AI agent': {'plant.rate': 3}})
    assert all(inputs(run, body) == inputs(run) for run in RUNS)
    assert inputs('slow', body, ['AI agent'])[('plant', 'rate')] == litres(3)


# ---- what an edit document may say ------------------------------------------------------------------


def test_two_edits_of_the_options_of_one_run_that_set_one_input_meet_even_when_equal():
    for first, second in ((1.5, 2.5), (2, 2)):
        body = document(options={'Fast': {'plant.rate': first}, 'Broken': {'plant.rate': second}})
        assert refused('slow', body) == ['meeting']


def test_edits_that_meet_only_in_a_combination_are_checked_when_it_is_asked_for():
    """No run takes Slow with Human team, so their edits of one input meet in no run: the document
    holds. The combination of fast_broken_human with Slow takes both."""
    body = document(options={'Slow': {'plant.rate': 1.5}, 'Human team': {'plant.rate': 2.5}})
    assert inputs('slow', body)[('plant', 'rate')] == litres(1.5)
    assert refused('fast_broken_human', body, ['Slow']) == ['meeting']


def test_the_name_of_a_group_changes_no_check():
    other = compiled(FIXTURE.replace('options "Response":', 'options "Defence":'))
    body = {
        **document(options={'Slow': {'plant.rate': 1.5}, 'Fast': {'plant.rate': 2.5}}),
        'model_hash': other.model_hash,
    }
    assert (
        other.configure('fast', body).inputs
        == MODEL.configure('fast', {**body, 'model_hash': MODEL.model_hash}).inputs
    )
    assert other.model_hash == MODEL.model_hash


def test_a_range_is_closed_and_a_value_outside_it_is_refused():
    for value in (1, 100):
        assert inputs('slow', document(set={'plant.delay': value}))[('plant', 'delay')] == Quantity(
            value, 'h'
        )
    for value in (1 - 1e-9, 100 + 1e-9, '4.2 days'):
        assert refused('slow', document(set={'plant.delay': value})) == ['range']


@pytest.mark.parametrize(
    ('key', 'value', 'code'),
    [
        ('plant.held', 1, 'input'),
        ('plant.backup', 1, 'bool'),
        ('plant.backup', 0, 'bool'),
        ('plant.backup', 0.5, 'bool'),
        ('plant.delay', True, 'value'),
        ('plant.delay', float('inf'), 'value'),
        ('plant.delay', '3 L', 'unit'),
        ('plant.delay', 'plant.rate', 'unknown_name'),
        ('plant.mode', 'STORMY', 'value'),
        ('plant.repair', 2, 'value'),
        ('plant.nothing', 1, 'input'),
        ('nobody.delay', 1, 'input'),
        ('Channel.pace', 1, 'input'),
    ],
)
def test_an_edit_needs_an_input_and_a_value_of_its_type(key, value, code):
    """Only an input is edited; a yes/no takes true or false and no number; a number is finite, in a
    unit of its dimension; a member of an enum is one of it; a distribution-valued input takes a
    distribution. One problem at each level of the document."""
    for body in (
        {'set': {key: value}},
        {'options': {'Fast': {key: value}}},
        {'runs': {'slow': {key: value}}},
    ):
        assert refused('slow', document(**body)) == [code], body


def test_edits_of_each_type_follow_the_declared_type():
    body = document(
        set={
            'plant.backup': False,
            'plant.mode': 'BUSY',
            'plant.actor': 'A person',
            'plant.delay': '0.1 days',
            'plant.repair': 'triangular(1 h, 2 h, 5 h)',
        }
    )
    assert inputs('slow', body) == {
        ('plant', 'backup'): False,
        ('plant', 'mode'): EnumValue('enum[CALM, BUSY]', 'BUSY'),
        ('plant', 'actor'): 'A person',
        ('plant', 'delay'): Quantity(2.4, 'h'),
        ('plant', 'repair'): Distribution('triangular', (1, 2, 5), 'h'),
    }


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'options': {'Quick': {'plant.rate': 1}}}, 'reference'),
        ({'runs': {'fastest': {'plant.rate': 1}}}, 'reference'),
        ({'presets': {'Fast': {'plant.rate': 1}}}, 'schema'),
        ({'set': {'plant': []}}, 'schema'),
        ({'set': {'plant.rate': ''}}, 'schema'),
        ({'model_hash': 'another'}, 'model_hash'),
        ({'schema_version': '5'}, 'schema'),
        ({'model_hash': ''}, 'schema'),
    ],
)
def test_an_edit_document_has_its_shape_its_revision_and_names_that_exist(body, code):
    assert refused('slow', {**document(), **body}) == [code]


def test_an_edit_document_that_is_not_an_object_or_lacks_its_envelope_is_refused():
    assert refused('slow', ['set']) == ['schema']
    for key in ('schema_version', 'model_hash'):
        bare = {k: v for k, v in document(set={'plant.rate': 3}).items() if k != key}
        assert refused('slow', bare) == ['schema']


def test_an_edit_document_is_one_transaction():
    """A problem in one run refuses the edits for every run, also when another run is asked for."""
    body = document(set={'plant.rate': 3}, runs={'fast': {'plant.delay': 1000}})
    with pytest.raises(LanguageError) as caught:
        MODEL.configure('slow', body)
    assert caught.value.codes == ['range'] and caught.value.problems[0].message.startswith(
        'runs/fast/plant.delay'
    )


def test_the_compile_api_takes_a_run_and_an_edit_document():
    found = compile_text(FIXTURE, UNITS, run='fast', edits=document(set={'plant.rate': 3}))
    assert found.configuration == MODEL.configure('fast', document(set={'plant.rate': 3}))
    assert found.model_hash == MODEL.model_hash and found.base == MODEL.configure()


# ---- combinations ---------------------------------------------------------------------------------


def test_a_combination_puts_its_options_in_place_of_those_of_their_groups():
    """slow_broken with Fast is Fast and Broken: Fast takes Slow's place; a combination that a run makes
    is that run's configuration."""
    assert inputs('slow_broken', options=['Fast']) == inputs('fast_broken_human', options=['AI agent'])
    assert inputs('slow', options=['Fast']) == inputs('fast')
    assert inputs('slow', options=['Slow']) == inputs('slow')
    assert inputs(None, options=['Broken']) == inputs('slow_broken')


@pytest.mark.parametrize(
    ('run', 'chosen'),
    [('nothing', []), ('slow', ['Quick']), ('slow', ['Slow', 'Fast']), ('slow', 'Fast')],
    ids=['unknown run', 'unknown option', 'two options of one group', 'a text'],
)
def test_a_combination_names_a_run_and_options_of_the_model(run, chosen):
    assert refused(run, None, chosen) == ['run']


# ---- the rules of options and runs in the file ----------------------------------------------------


def _with(old, new, text=FIXTURE):
    assert old in text
    return text.replace(old, new)


@pytest.mark.parametrize(
    ('text', 'code', 'words'),
    [
        # Only an input is set by an option (R-A5-04).
        (_with('plant.backup = false  @ident', 'plant.held = 3 L  @ident'), 'option', 'plant.held'),
        # A number or a yes/no that an option sets cites its record (R-A5-05).
        (_with('plant.delay = 2 h  @ident', 'plant.delay = 2 h'), 'record', 'plant.delay'),
        (_with('plant.backup = false  @ident', 'plant.backup = false'), 'record', 'plant.backup'),
        # A value of the input's type, written out, in its range.
        (_with('plant.delay = 2 h  @ident', 'plant.delay = 2 L  @ident'), 'unit', 'plant.delay'),
        (_with('plant.delay = 2 h  @ident', 'plant.delay = 2 h * 3  @ident'), 'value', 'plant.delay'),
        (_with('plant.delay = 2 h  @ident', 'plant.delay = 200 h  @ident'), 'range', 'plant.delay'),
        (_with('plant.mode = BUSY', 'plant.mode = STORMY'), 'enum_member', 'plant.mode'),
        # A path names an input of a member, of every member of a template, or of the top level.
        (_with('second.pace = 5 L/h', 'third.pace = 5 L/h'), 'unknown_name', 'third.pace'),
        (_with('second.pace = 5 L/h', 'second.paces = 5 L/h'), 'unknown_name', 'second.paces'),
        # An option sets an input once, and an option is named once across the groups.
        (
            _with(
                'plant.delay = 2 h  @ident', 'plant.delay = 2 h  @ident\n        plant.delay = 3 h  @ident'
            ),
            'option',
            'plant.delay = 3 h',
        ),
        (_with('    "AI agent":', '    "Slow":'), 'option', '"Slow":\n'),
        # A run names known options, at most one of each group, no two of which set one input.
        (_with('slow = "Slow" + "Intact"', 'slow = "Slwo" + "Intact"'), 'run', 'slow ='),
        (_with('slow = "Slow" + "Intact"', 'slow = "Slow" + "Fast"'), 'run', 'slow ='),
        (
            _with(
                'slow_broken = "Slow" + "Broken"', 'slow_broken = "Slow" + "Intact"\n    slow_broken = "Slow"'
            ),
            'run',
            'slow_broken = "Slow"\n',
        ),
        (
            _with(
                '        plant.actor = "The human team"',
                '        plant.actor = "The human team"\n        plant.delay = 3 h  @ident',
            ),
            'run',
            'fast_broken_human',
        ),
    ],
)
def test_each_rule_of_options_and_runs_is_refused_at_its_line(text, code, words):
    found = problems(text)
    expected = (
        line_of(text, words.rstrip('\n'))
        if not words.endswith('\n')
        else _last_line_of(text, words.rstrip('\n'))
    )
    assert found == [(code, expected)], found


def _last_line_of(text, words):
    return max(k for k, row in enumerate(text.split('\n'), 1) if row.strip().startswith(words))


def test_a_text_and_a_member_of_an_enum_need_no_record_and_a_member_line_wins_over_its_template():
    """Across the options of one run, and in one option, a line of one member wins over a line of every
    member of its template: they set two values, of which the member's is its own."""
    assert ('plant', 'actor') in inputs('fast_broken_human') and ('plant', 'mode') in inputs('slow_broken')
    text = _with('        second.pace = 5 L/h  @ident', '        first.pace = 5 L/h  @ident')
    text = _with(
        '        Channel.instances.pace = 0.5 L/h  @ident',
        '        Channel.instances.pace = 0.5 L/h  @ident\n        second.pace = 9 L/h  @ident',
        text,
    )
    found = inputs('fast_broken_human', model=compiled(text))
    assert (found[('first', 'pace')], found[('second', 'pace')]) == (litres(5), litres(9))


def test_a_model_without_options_has_its_default_run_only():
    text = FIXTURE.split('options "Response":')[0] + 'record ident: assumption "A synthetic test fixture."\n'
    model = compiled(text)
    assert (model.declared.options, model.declared.runs) == ((), ())
    assert model.configure().inputs == ()
    with pytest.raises(LanguageError):
        model.configure('slow')


def test_asking_for_one_run_checks_every_option_and_keeps_the_hash():
    """The checks of the model are its own, whichever run is asked for: an option that no run takes
    is checked all the same, and the hash is the model's."""
    assert compile_text(FIXTURE, UNITS, run='slow').model_hash == MODEL.model_hash
    text = _with('        "An AI agent."', '        "An AI agent."\n        plant.rate = 40 L/h  @ident')
    with pytest.raises(LanguageError) as caught:
        compile_text(text, UNITS, run='slow')
    assert caught.value.codes == ['range']


def test_a_configuration_is_made_from_the_compiled_model_without_compiling_it_again(monkeypatch):
    """The options and runs are part of the declared model, built once: each configuration reads them."""
    import napkin.model.compile as compile_module

    model = compiled()

    def again(*args, **kwargs):
        raise AssertionError('declared again')

    monkeypatch.setattr(compile_module, 'declare', again)
    assert {run: inputs(run, model=model) for run in RUNS} == {run: inputs(run) for run in RUNS}


@pytest.mark.parametrize(
    ('token', 'accepted'),
    [
        ('14.4', True),
        ('"0.6 days"', True),
        ('14.400000000000000001', False),
        ('"0.6000000000000000001 days"', False),
    ],
)
def test_authored_json_decimal_is_checked_in_the_inputs_unit(tmp_path, token, accepted):
    from napkin.commands.common import edits_of

    model = compile_text(
        'scenario "Decimal inputs"\n    horizon 1 h\ninput cutoff: h = 0 h in [0, 0.6 days]\n', UNITS
    )
    path = tmp_path / 'edits.json'
    path.write_text('{"set": {"cutoff": ' + token + '}}')
    edits = edits_of(model, path)
    if accepted:
        assert model.configure(edits=edits).inputs[0].value == Quantity(14.4, 'h')
    else:
        with pytest.raises(LanguageError) as failed:
            model.configure(edits=edits)
        assert failed.value.codes == ['range']


@pytest.mark.parametrize('token', ['1' + '0' * 309, '1e309', '-1' + '0' * 309, '-1e309'])
def test_out_of_float_range_edits_have_the_same_diagnostic(tmp_path, token):
    from napkin.commands.common import edits_of

    path = tmp_path / 'edits.json'
    path.write_text('{"set": {"plant.delay": ' + token + '}}')
    with pytest.raises(LanguageError) as failed:
        MODEL.configure(edits=edits_of(MODEL, path))
    assert failed.value.codes == ['value']
