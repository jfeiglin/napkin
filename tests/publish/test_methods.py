"""A methods page reads as prose and tables: each topic has its own paragraph, a phrase that stands as a
sentence starts as one, prose is never shown as code and no number has an exponent."""

import json

import pytest

from napkin.model import ModelError
from napkin.model.model import build_model
from tests.build import (
    compiled,
    drop,
    entity,
    event,
    evidence_library,
    in_place,
    member,
    named,
    number_of,
    option,
    options,
    output,
    parameter,
    places,
    q,
    quote,
    sc99,
    scenario,
    stock,
)
from tests.helpers import SCENARIO_IDS, catalogue_model
from tests.publish.test_pages import OWN, Written, after, before, built_own, edited, reline, uncited
from tools.publish.brief import brief_of
from tools.publish.methods import scenario_methods
from tools.publish.pages import Pages


def paragraphs(text, heading):
    """The paragraphs of one part of a page."""
    part = text.split(f'## {heading}\n')[1].split('\n## ')[0]
    return [block.strip('\n') for block in part.split('\n\n') if block.strip()]


def row(text, label):
    """The cells of the table row that a label starts."""
    line = next(line for line in text.splitlines() if line.startswith(f'| {label} '))
    return line[2:-2].split(' | ')


def cell(text, label, column):
    """The cell of the table row that a label starts, in the column that the table's header names."""
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(f'| {label} '))
    top = index
    while top > 0 and lines[top - 1].startswith('|'):
        top -= 1
    return row(text, label)[lines[top][2:-2].split(' | ').index(column)]


def low_end(place, low):
    """An edit step: the range of the field at `place` (`in lo to hi` on its line) starts at `low`."""

    def step(text):
        start, _ = places(text)[place]
        rows = text.split('\n')
        head, _, rest = rows[start].partition(' in ')
        _, _, high = rest.partition(' to ')
        rows[start] = f'{head} in {low} to {high}'
        return '\n'.join(rows)

    return step


def also_when(place, condition):
    """An edit step: the event at `place` triggers only when `condition` also holds."""

    def step(text):
        start, _ = places(text)[place]
        rows = text.split('\n')
        head, _, records = rows[start].rpartition(':')
        event, _, written = head.partition(' when ')
        rows[start] = f'{event} when ({written}) and {condition}:{records}'
        return '\n'.join(rows)

    return step


def start_limits(review):
    """The reviewers' premise for the first move: the limits of the attack."""
    return next(premise['statement'] for premise in review['premises'] if premise['id'] == 'START')


# The name of the attack that the pages give (`attack` in brief.toml), with a small first letter.
ATTACK = 'unauthorized control commands'


def written_model(tmp_path, text, brief=''):
    """The model of a file written in a folder of its own, with the brief settings `brief`."""
    folder = tmp_path / f'model{len(list(tmp_path.iterdir()))}'
    folder.mkdir()
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    (folder / 'brief.toml').write_text(brief, encoding='utf-8')
    return build_model(folder / 'model.scn', evidence_library())


def attack_paragraphs(tmp_path, text, attack=ATTACK):
    """The paragraphs of the methods page's part on the attack and who it affects, with the attack's
    name in brief.toml."""
    model = written_model(tmp_path, text, f'attack = {json.dumps(attack)}\n')
    return paragraphs(scenario_methods(model, link=lambda target: target), 'The attack and who it affects')


def test_the_effect_of_the_attack_reads_as_a_sentence_of_its_own(tmp_path):
    assert ATTACK[0].islower()
    blocks = attack_paragraphs(tmp_path, sc99())
    assert blocks[0] == ATTACK[0].upper() + ATTACK[1:] + '.'


def test_the_attackers_doc_is_a_paragraph_of_its_own_once(tmp_path):
    """The file describes the attacker once, in the text of the entity with the role adversary."""
    text = sc99()
    (doc,) = [thing.text.value for thing in Written(text).parts.things if thing.role == 'adversary']
    blocks = attack_paragraphs(tmp_path, text)
    assert [block.splitlines() for block in blocks if doc in block] == [[doc]]


def test_an_output_that_is_not_estimated_states_its_reason_as_prose_not_as_a_calculation():
    reason = 'A separate study of each group must come first.'
    text = edited(
        scenario(),
        after(
            'output:/delivered',
            output('other', None, 'people', doc='Other harm', under=(f'unestimated {quote(reason)}',)),
        ),
    )
    written = Written(text)
    page = scenario_methods(compiled(text), link=lambda target: target)
    calculation = row(page, written.texts['output:/other/""'])[-1]
    assert reason in calculation and '`' not in calculation
    # An estimated output still shows its expression as code.
    assert row(page, written.texts['output:/delivered/""'])[-1] == f'`{written.value("output:/delivered")}`'


def test_no_number_in_a_methods_table_has_an_exponent():
    low = 1e-05
    text = edited(scenario(), low_end('service/rate', q(low, 'people/day')))
    written = Written(text)
    allowed = cell(
        scenario_methods(compiled(text), link=lambda target: target),
        written.texts['service/rate/""'],
        'Allowed values',
    )
    shown_low, shown_high = allowed.split('–')
    assert 'e' not in allowed.lower()
    assert (float(shown_low), float(shown_high)) == (low, number_of(written.keyed('service/rate/max:')))


def test_the_limits_of_the_first_move_follow_the_effect_of_the_attack(tmp_path):
    """The reviewers' premise for the first move needs no record, so it is not in the table of
    premises. It states the limits of the attack, so it follows the attack's effect."""
    text = sc99()
    blocks = attack_paragraphs(tmp_path, text)
    assert blocks[1] == start_limits(Written(text).review())


@pytest.mark.parametrize('sid', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_a_methods_page_states_the_limits_of_its_first_move_once(sid):
    model = catalogue_model(sid)
    limits = start_limits(Pages(model).reviewed)
    assert limits and scenario_methods(model, link=lambda target: target).count(limits) == 1


def test_a_methods_page_of_a_start_needs_its_limits():
    """The methods page gives the limits of the first move after its effect: a scenario with a start
    states them in the premise with id START, or its methods page fails at the line of its premises.
    A scenario without a start has none to state."""
    text = edited(
        sc99(),
        member('notes:/premises:', 'P1: "Another premise."  @fixture'),
        drop('notes:/premises:/START:'),
    )
    model = compiled(text, evidence_library())
    with pytest.raises(ModelError, match='START') as caught:
        scenario_methods(model, link=lambda target: target)
    (found,) = caught.value.diagnostics
    assert found['path'] == 'notes:/premises:'
    assert 'START' not in str(Written(scenario()).review())
    scenario_methods(compiled(scenario()), link=lambda target: target)


@pytest.mark.parametrize('sid', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_each_run_has_a_row_with_its_defender_response_and_its_option(sid):
    model = catalogue_model(sid)
    groups = Pages(model).options()['axis']['groups']
    text = scenario_methods(model, link=lambda target: target)
    for info in model.runs.values():
        (response,) = [p for p in info['options'] if p in model.menu[brief_of(model).choice_group]]
        option = ' · '.join(p for group in groups for p in info['options'] if p in model.menu[group])
        assert f'| {info["name"]} | {response} | {option} | ' in text


def two_structures():
    """The analytic transfer with a backup that serves everyone who waits, but only in the runs whose
    profile starts the service by hand. No event changes how the service starts, so the runs that
    start it by itself leave the backup and its count out: for them, an output reads zero for that
    count."""
    text = edited(
        scenario(),
        member('service', named('mode', 'automatic', 'manual')),
        after(
            'service',
            '',
            entity(
                'backup',
                stock('served', 0, size=10, kind='tally', doc='People the backup serves'),
                event('take_over', 'service.mode is "manual"', 'served += service.n'),
                doc='A backup that serves everyone who waits when the service starts by hand.',
                role='operator',
            ),
        ),
        after(
            'output:/delivered',
            output(
                'all_served',
                'service.served + backup.served',
                'people',
                doc='Served in all',
                under=('distinct  @fixture',),
            ),
        ),
        before(
            'runs:',
            options(
                'Start',
                option('Automatic start', 'The service starts by itself.'),
                option('Manual start', 'The service starts by hand.', 'service.mode = "manual"  @fixture'),
            ),
            '',
        ),
        reline('runs:/a', 'a = "Default" + "Automatic start"'),
        reline('runs:/b', 'b = "Default" + "Automatic start" + "Half rate"'),
        member('runs:', 'c = "Default" + "Manual start"'),
    )
    return compiled(text)


def test_an_output_that_runs_define_otherwise_has_a_row_for_each_definition_with_its_options():
    """An output reads zero for a stock that a run's structure leaves out, so runs can define it
    otherwise: each definition has its own row, which names the options of the runs that use it."""
    model = two_structures()
    assert len(model.structures) == 2
    runs = Pages(model).runs()
    text = scenario_methods(model, link=lambda target: target)
    outcomes = text.split('## Calculated outcomes\n')[1].split('\n## ')[0]
    differing = 0
    for name in next(iter(model.structures.values())).outcomes:
        definitions = {}
        for run in model.runs:
            expr = model.structure_of(run).outcomes[name].expr
            options = definitions.setdefault(expr, [])
            if runs[run]['option'] not in options:
                options.append(runs[run]['option'])
        if len(definitions) == 1:
            continue
        differing += 1
        label = next(iter(model.structures.values())).outcomes[name].label
        notes = {
            ('option: ' if len(options) == 1 else 'options: ') + '; '.join(options)
            for options in definitions.values()
        }
        rows = [line for line in outcomes.splitlines() if line.startswith(f'| {label} (')]
        assert {row[len(f'| {label} (') :].split(') |')[0] for row in rows} == notes
    assert differing


def test_an_input_applies_where_the_options_that_set_it_apply(tmp_path):
    """ "Applies to" follows the groups of the profiles that set an input: no profile, every pathway;
    the group of the responses (`choice_group` in brief.toml), that group by its name; a group that
    every run names (the options), the option; any other group, one pathway. Without a group of the
    responses, the group that every run names is an option too."""
    text = edited(
        scenario(),
        member('service', parameter('spare', 1, 'h', 0, 5, doc='Spare time')),
        member(
            'options:/Response',
            option('Late stop', 'The service stops late.', 'service.end = 20 h  @fixture'),
        ),
        before(
            'options:/Rate',
            options(
                'Size',
                option('Few people', 'Few people wait.'),
                option('Many people', 'Forty people wait.', 'service.n = 40 people  @fixture'),
            ),
            '',
        ),
        # Every run names a profile of Size; only run b names one of Rate.
        reline('runs:/a', 'a = "Default" + "Few people"'),
        reline('runs:/b', 'b = "Default" + "Few people" + "Half rate"'),
        member('runs:', 'c = "Late stop" + "Many people"'),
    )
    written = Written(text)
    responses = written.parts.profiles[0].name
    page = scenario_methods(
        written_model(tmp_path, text, f'choice_group = {json.dumps(responses)}\n'), link=lambda target: target
    )
    expected = {
        'spare': 'all pathways',
        'end': responses,
        'n': 'option',
        'rate': 'one pathway',
    }
    labels = {f: written.texts[f'service/{f}/""'] for f in expected}
    assert {f: cell(page, labels[f], 'Applies to') for f in expected} == expected
    page = scenario_methods(written_model(tmp_path, text), link=lambda target: target)
    assert {f: cell(page, labels[f], 'Applies to') for f in expected} == {**expected, 'end': 'option'}


@pytest.mark.parametrize('fixed', [False, True])
def test_a_bool_input_reads_yes_or_no_never_as_a_share(fixed):
    text = edited(
        scenario(),
        member('service', parameter('open', True, 'bool', None if fixed else 0, doc='Service open')),
        also_when('service/stop', 'open'),
    )
    page = scenario_methods(compiled(text), link=lambda target: target)
    label = Written(text).texts['service/open/""']
    assert cell(page, label, 'Unit') == 'yes/no'
    assert cell(page, label, 'Allowed values') == ('Fixed Yes' if fixed else 'Yes or No')


def test_a_premise_of_the_tests_own_file_has_the_explanation_of_its_record(tmp_path):
    model = built_own(tmp_path)
    page = scenario_methods(model, link=lambda target: target)
    statement = 'The users wait.'
    assert statement in OWN
    assert row(page, statement) == [statement, 'The test counts.']


def test_the_methods_show_authored_wording_verbatim():
    """Renderers arrange the authored text; the file and the library own every phrase."""
    label = 'Compound workers who cannot leave'
    explanation = 'Sum of the separate loss accounts, with no overlap between them.'
    scope = 'No value or zero is inferred.'
    text = edited(
        sc99(),
        uncited('service/n'),
        reline('service/n/""', quote(label)),
        after('service/n/""', in_place('identity', explanation)),
        member('output:/delivered', f'scope {quote(scope)}'),
    )
    written = Written(text)
    model = compiled(text, evidence_library())
    methods = scenario_methods(model, link=lambda target: target)
    low, high = (number_of(written.keyed(f'service/n/{edge}:')) for edge in ('min', 'max'))
    assert row(methods, label)[0] == f'{label} (`service.n`)'
    assert cell(methods, label, 'Unit') == written.typed('service/n')
    assert cell(methods, label, 'Allowed values') == f'{low}–{high}'
    assert row(methods, label)[-1] == explanation
    delivered = written.texts['output:/delivered/""']
    unit, expression = written.typed('output:/delivered'), written.value('output:/delivered')
    assert f'| {delivered} | {unit} | {scope} | `{expression}` |' in methods
