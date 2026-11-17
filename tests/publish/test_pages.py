"""The pages' data that the publisher generates from a model (tools/publish/pages.py):
MODELTEST, and a model file of the tests' own.

The synthetic tests use MODELTEST (tests/model/modeltest.py): an attacker switches a service off at
t = 0, and after the repair it jams the switch unless the responders remove it first. Each test
writes the texts, menu lines, profiles, names and brief settings that it expects to see, reads what
the fixture writes from the file, and reads the engine's names of events, outputs and inputs from the
model. The catalogue test checks the rules of the language on every scenario file, never its wording.
"""

from __future__ import annotations

import dataclasses
import re
import tomllib

import pytest

from napkin.draw.model_map import ACTOR_NAMES
from napkin.draw.style import StyleError
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.language.evidence import Evidence, notes_of
from napkin.model.language.format import one_line
from napkin.model.language.nodes import Event, Keyed, Text
from napkin.model.model import build_model
from napkin.model.semantic import path_text
from tests.acceptance.helpers import LIBRARY
from tests.build import (
    block,
    drop,
    edit,
    entity,
    event,
    indent,
    member,
    named_event,
    number_of,
    option,
    options,
    output,
    parameter,
    places,
    quote,
    replace,
    status,
    template,
    text_value,
    toml,
    value,
)
from tests.helpers import SCENARIO_IDS, catalogue_model
from tests.model import modeltest
from tests.model.modeltest import BRIEF, FIXTURE
from tests.owned import block_at
from tools.publish import brief as styles
from tools.publish.pages import Pages, pages, review_of

# ---- edits of a model text -------------------------------------------------------------------------
#
# The steps of `tests.build.edit` put lines at the end of a line's block; these steps put a line where
# the file's order wants it. Each is a function of the text.


def edited(text, *steps):
    """`text` with the steps of an edit, in order: steps of `tests.build.edit`, and functions of the
    text."""
    for step in steps:
        text = step(text) if callable(step) else edit(text, step)
    return text


def depth(row):
    return (len(row) - len(row.lstrip(' '))) // 4


def reline(place, row):
    """An edit step: the first row of the line at `place` becomes `row`, at its depth."""

    def step(text):
        start, _ = places(text)[place]
        rows = text.split('\n')
        rows[start] = indent(row, depth(rows[start]))
        return '\n'.join(rows)

    return step


def uncited(place):
    """An edit step: the line at `place` cites no records at its end."""

    def step(text):
        start, _ = places(text)[place]
        rows = text.split('\n')
        rows[start] = rows[start].split('  @')[0]
        return '\n'.join(rows)

    return step


def after(place, *blocks):
    """An edit step: the blocks go right after the line at `place` and the lines under it, at its
    depth. A last block '' leaves an empty line after them."""

    def step(text):
        start, end = places(text)[place]
        rows = text.split('\n')
        added = indent('\n'.join(blocks), depth(rows[start])).split('\n')
        return '\n'.join(rows[:end] + added + rows[end:])

    return step


def before(place, *blocks):
    """An edit step: the blocks go right before the line at `place`, at its depth. A last block ''
    leaves an empty line between them and that line."""

    def step(text):
        start, _ = places(text)[place]
        rows = text.split('\n')
        added = indent('\n'.join(blocks), depth(rows[start])).split('\n')
        return '\n'.join(rows[:start] + added + rows[start:])

    return step


def also(run, profile_name):
    """An edit step: the run `run` also names the profile `profile_name`, last (before `versus`)."""

    def step(text):
        start, _ = places(text)[f'runs:/{run}']
        rows = text.split('\n')
        head, versus, other = rows[start].rstrip().partition(' versus ')
        rows[start] = f'{head} + {quote(profile_name)}{versus}{other}'
        return '\n'.join(rows)

    return step


def every_run(profile_of):
    """An edit step: each run also names the profile `profile_of(run)`, last."""

    def step(text):
        names = [
            place[len('runs:/') :]
            for place in places(text)
            if place.startswith('runs:/') and place.count('/') == 1
        ]
        return edited(text, *(also(run, profile_of(run)) for run in names))

    return step


# ---- the fixture and the file as the test wrote it ----------------------------------------------


class Draft:
    """MODELTEST as a test's edits change it: the text of its file and its brief settings."""

    def __init__(self):
        self.text = FIXTURE
        self.sheet = tomllib.loads(BRIEF)

    def edit(self, *steps):
        self.text = edited(self.text, *steps)

    def brief(self):
        return toml(self.sheet)


def build(tmp_path, *edits):
    """The model of MODELTEST with the edits, each a function that changes a `Draft`, built from its
    file with its brief settings beside it."""
    draft = Draft()
    for change in edits:
        change(draft)
    return modeltest.build(tmp_path, text=draft.text, brief=draft.brief())


class Written:
    """A model file as the parser reads it: its texts by their places (`texts`), its things, menu,
    runs, records and review, and what its lines write."""

    def __init__(self, text):
        self.text = text
        self.parts = front.read(text, 'model.scn')
        self.texts = {}
        # What each keyed part writes (`keyed`): an end of a range, a size, a rate or a limit.
        self.keys = {}
        self.collect(self.parts)

    def collect(self, node):
        if isinstance(node, Keyed) and node.expr is not None:
            self.keys[path_text(node.place)] = one_line(node.expr.tokens)
        if isinstance(node, Text):
            if node.place is not None:
                self.texts[path_text(node.place)] = node.value
        elif dataclasses.is_dataclass(node):
            for item in dataclasses.fields(node):
                self.collect(getattr(node, item.name))
        elif isinstance(node, (list, tuple)):
            for item in node:
                self.collect(item)
        elif isinstance(node, dict):
            for item in node.values():
                self.collect(item)

    def thing(self, name):
        return next(thing for thing in self.parts.things if thing.name == name)

    def record(self, name):
        """A named record as the pages write it out: its kind, its explanation and its name."""
        found = next(record for record in self.parts.records if record.name == name)
        return {'kind': found.kind, 'explanation': found.text, 'name': found.name}

    def menu(self):
        """{group: {profile: its line in the menu}}, in the order of the file."""
        return {
            group.name: {item.name: item.text.value for item in group.profiles}
            for group in self.parts.profiles
        }

    def runs(self):
        return {run.name: run.profiles for run in self.parts.runs}

    def review(self):
        """The notes as the pages read them, from the parts as written."""
        return review_of(notes_of(self.parts.notes, Evidence(self.parts)))

    def row(self, place):
        """The first row of the line at `place`, without its depth and its records."""
        return block_at(self.text, place).split('\n')[0].split('  @')[0].strip()

    def value(self, place):
        """What the line at `place` writes after its `=`: a text without its quotes, or a number with
        its unit."""
        written = self.row(place).split(' = ', 1)[1]
        return written[1:-1] if written.startswith('"') else written

    def keyed(self, place):
        """What the file writes for the key at `place`: an end of a range (`service/rate/min:`, the
        `lo` of `in lo to hi`), a size, a rate or a limit, as a number with its unit."""
        return self.keys[place]

    def typed(self, place):
        """The type that the line of a value or an output at `place` writes after its name."""
        return self.row(place).split(' = ', 1)[0].split(': ', 1)[1]


def written(tmp_path):
    """MODELTEST as the test wrote it."""
    return Written((tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8'))


# ---- edits of the fixture -----------------------------------------------------------------------

STOPPED = {'role': 'responder', 'text': 'Responders remove the attacker before the jam.'}
SKIPPED = {'role': 'operator', 'text': 'The service settles before the jam is ready.'}


def with_jam_docs(draft):
    """Texts for the jam: one for the attacker's waiting event, and one for each of its outcomes. The
    outcomes that the defenders bring about name their roles."""
    draft.edit(
        before('attacker/jam_on_repair/done', quote('The attacker gets ready to jam the switch.')),
        member('attacker/jam_on_repair/done', quote('{actor} jams the switch.')),
        member('attacker/jam_on_repair/stopped', quote(STOPPED['text']), f'role {STOPPED["role"]}'),
        member('attacker/jam_on_repair/skipped', quote(SKIPPED['text']), f'role {SKIPPED["role"]}'),
    )


def with_human_runs(draft):
    """A human team at each response: the featured pair at the slow repair, whose second run says it
    is the comparison of the first, and a run that says it is the comparison of the fast repair's run."""
    draft.edit(
        before(
            'runs:',
            options(
                'Attacker',
                option('AI agent', 'The AI reacts within minutes.'),
                option(
                    'Human team',
                    'A human team needs two days to react.',
                    'attacker.reaction_time = 48 h  @ident',
                    'attacker.actor = "The human team"',
                ),
            ),
            '',
        ),
        member(
            'runs:',
            'slow_kept_human = "Slow repair" + "Keeps access" + "Human team" versus slow_kept',
            'fast_kept = "Fast repair" + "Keeps access"',
            'fast_kept_human = "Fast repair" + "Keeps access" + "Human team" versus fast_kept',
        ),
    )
    draft.sheet['featured'] = ['slow_kept', 'slow_kept_human']


def with_load(draft):
    """A group of profiles that set inputs only and that every run names."""
    draft.edit(
        member(
            'service',
            parameter('load', 0.5, 'fraction', 0, 1, doc='Share of users who come back', records='@ident'),
        ),
        before(
            'runs:',
            options(
                'Load',
                option('Light load', 'Few users come back.'),
                option('Heavy load', 'Most come back.', 'service.load = 0.9  @ident'),
            ),
            '',
        ),
        every_run(lambda run: 'Heavy load' if run.startswith('fast') else 'Light load'),
    )


def load_first(draft):
    """The group Load first in the menu."""
    group = block_at(draft.text, 'options:/Load').rstrip()
    draft.edit(drop('options:/Load'), before('options:/Response', group, ''))


def with_start_text(text):
    """An edit of a draft: the start has the text `text`, before its lines."""
    return lambda draft: draft.edit(before('attacker/start/done/0', quote(text)))


def with_outputs(draft):
    """Five outputs besides the service's: totals over the run, a level and one that reports the
    people the study follows, in a `show` list of the brief settings that mixes them. (The test library
    lists only that category: an output that reports a harm needs the catalogue's library; the
    catalogue test checks those.)"""

    def total(name, *lines):
        return output(name, 'service.served', 'people', doc='An output', records='@ident', under=lines)

    draft.edit(
        before(
            'options:/Response',
            total('first_total'),
            total('level', 'level'),
            total('reach', 'category exposure', 'scope "The users of the service."'),
            total('second_total'),
            total('third_total'),
            '',
        )
    )
    draft.sheet['show'] = ['reach', 'level', 'first_total', 'service.served', 'second_total', 'third_total']


# ---- the timeline cards -------------------------------------------------------------------------


def test_a_card_reads_the_doc_of_its_trigger_or_else_of_its_method(tmp_path):
    def edit(draft):
        # The failure has a role of its own and fires an event with a text of its own; the repair has
        # no text and fires an event with one; the settling has no text and fires no event.
        draft.edit(
            after('service/fails/""', 'role environment'),
            member('service/fails', 'go_down'),
            drop('service/repaired/""', 'service/settles/""'),
            replace('        status = "back"\n', '        repair\n'),
            member(
                'service',
                named_event('go_down', doc='The service goes down.', records=None),
                named_event('repair', 'status = "back"', doc='Engineers repair the service.', records=None),
            ),
        )

    model = build(tmp_path, edit)
    file = written(tmp_path)
    cards = pages(model)['cards']
    # An event that fires at once shows its text when it fires; its role wins over its entity's.
    assert cards[model.events['service.fails.done']] == [
        {'text': file.texts['service/fails/""'], 'actor': 'environment'}
    ]
    # An event that a line fires shows its own text, with its entity's role.
    for named in ('go_down', 'repair'):
        assert cards[model.events[f'service.{named}.done']] == [
            {'text': file.texts[f'service/{named}/""'], 'actor': file.thing('service').role}
        ]
    # Neither the event nor its outcome has a text: the event has no card, also when the event that it
    # fires has one.
    assert model.events['service.repaired.done'] not in cards
    assert model.events['service.settles.done'] not in cards


def test_a_milestone_has_the_card_of_its_doc(tmp_path):
    def edit(draft):
        draft.edit(
            member(
                'service',
                event('busy', 't >= 50 h', doc='The service is busy.', records='@ident'),
                event('quiet', 't >= 60 h', records='@ident'),
            )
        )

    model = build(tmp_path, edit)
    texts = written(tmp_path).texts
    cards = pages(model)['cards']
    assert cards[model.events['service.busy.done']] == [
        {'text': texts['service/busy/""'], 'actor': 'operator'}
    ]
    assert model.events['service.quiet.done'] not in cards


def test_a_doc_that_set_gives_one_entity_is_the_text_of_its_card(tmp_path):
    def edit(draft):
        with_more_entities(draft)
        draft.edit(
            member('Queue', event('full', 't >= 10 h', doc='The queue is full.', records='@ident')),
            member('large', block('full:', quote('The large queue is full.'))),
        )

    model = build(tmp_path, edit)
    texts = written(tmp_path).texts
    cards = pages(model)['cards']
    assert cards[model.events['small.full.done']][0]['text'] == texts['Queue/full/""']
    assert cards[model.events['large.full.done']][0]['text'] == texts['large/full/""']


def test_a_list_of_texts_gives_one_card_for_each_time(tmp_path):
    texts = ['The service fails.', 'The service fails a second time.']
    model = build(tmp_path, lambda d: d.edit(reline('service/fails/""', f'[{", ".join(map(quote, texts))}]')))
    cards = pages(model)['cards'][model.events['service.fails.done']]
    assert [(card['text'], card['occurrence']) for card in cards] == list(zip(texts, (1, 2), strict=True))


def test_the_endings_of_the_attacker_s_waiting_method_show_who_ends_it(tmp_path):
    model = build(tmp_path, with_jam_docs)
    texts = written(tmp_path).texts
    cards = pages(model)['cards']

    def card(event):
        (item,) = cards[model.events[event]]
        return item

    # The event shows its own text when it triggers, with its entity's role; it waits, so its outcomes
    # show their own texts only. The attacker does the jam, as its outcome names no role; the
    # responders stop it and the operators see it skipped, as those outcomes say.
    assert card('attacker.jam_on_repair') == {
        'text': texts['attacker/jam_on_repair/""'],
        'actor': 'adversary',
    }
    assert card('attacker.jam_on_repair.done') == {
        'text': texts['attacker/jam_on_repair/done/""'].replace('{', '{attacker.'),
        'actor': 'adversary',
    }
    assert card('attacker.jam_on_repair.stopped') == {'text': STOPPED['text'], 'actor': STOPPED['role']}
    assert card('attacker.jam_on_repair.skipped') == {
        'text': texts['attacker/jam_on_repair/skipped/""'],
        'actor': SKIPPED['role'],
    }


def test_braces_name_the_field_of_the_entity_that_acts_as_each_run_sets_it(tmp_path):
    def item(draft):
        draft.edit(member('service', text_value('item', 'requests')))

    model = build(tmp_path, with_jam_docs, with_human_runs, item)
    file = written(tmp_path)
    generated = pages(model)
    (card,) = generated['cards'][model.events['attacker.jam_on_repair.done']]
    done = file.texts['attacker/jam_on_repair/done/""']
    assert card['text'] == done.replace('{', '{attacker.')
    actor = file.value('attacker/actor')
    human = file.value('options:/Attacker/Human team/attacker.actor')
    item = file.value('service/item')
    for run, info in model.runs.items():
        # The attacker's text value as the run's profiles set it; a text that no profile sets in every run.
        expected = human if 'Human team' in info['options'] else actor
        assert generated['texts'][run] == {'service.item': item, 'attacker.actor': expected}
        filled = re.sub(r'\{([^}]+)\}', lambda m: generated['texts'][run][m.group(1)], card['text'])
        assert filled == done.replace('{actor}', expected)
    # The human team acts in the runs whose profiles give the attacker's name another text.
    humans = [run for run, info in model.runs.items() if 'Human team' in info['options']]
    assert humans and generated['operation']['human_runs'] == humans


def test_the_first_move_of_an_incident_has_the_card_of_its_method(tmp_path):
    text = '{actor} switches the service off.'
    model = build(tmp_path, with_start_text(text))
    cards = pages(model)['cards']
    # The start fires at once: its outcome shows its text, and its trigger has no card.
    assert cards[model.events['attacker.start.done']] == [
        {'text': text.replace('{', '{attacker.'), 'actor': 'adversary'}
    ]
    assert model.events['attacker.start'] not in cards


# ---- the brief ----------------------------------------------------------------------------------


def test_one_default_run_has_no_story(tmp_path):
    model = build(tmp_path)
    assert len(styles.featured(styles.brief_of(model), model)) == 1 and pages(model)['story'] is None


def test_the_story_compares_the_two_default_runs(tmp_path):
    # The first sentence ends at the first full stop after a word, not at the one of a number.
    hook = 'An attacker cuts the service for 2.5 h.'

    def edit(draft):
        with_human_runs(draft)
        summary = f'{hook} It returns to jam the repair. The responders remove it.'
        draft.edit(
            reline('scenario:/summary:', f'summary {quote(summary)}'),
            member('notes:', 'counterfactual: "A human team reacts later."'),
        )

    model = build(tmp_path, edit)
    story = pages(model)['story']
    review = written(tmp_path).review()
    assert story['runs'] == list(styles.brief_of(model).featured)
    assert story['hook'] == hook
    # The reviewers' texts; one they do not write is empty.
    assert (story['counterfactual'], story['decisive_choice']) == (review['counterfactual'], '')


def test_the_brief_compares_the_first_totals_of_show(tmp_path):
    model = build(tmp_path, with_human_runs, with_outputs)
    measures = pages(model)['story']['measures']
    # The first two outputs of show that count a total over the run and report nothing.
    assert measures == [model.outputs['first_total'], model.outputs['second_total']]
    outcomes = model.whole[()].outcomes
    assert all(outcomes[m].kind == 'cumulative' and outcomes[m].category is None for m in measures)


def test_the_metrics_are_the_outputs_of_show(tmp_path):
    model = build(tmp_path, with_human_runs, with_outputs)
    show = styles.brief_of(model).show
    metrics = pages(model)['metrics']
    assert [m['outcome'] for m in metrics] == [model.outputs[x] for x in show]
    # An output that reports no harm shows a service, also the one of the people the study follows.
    assert {m['style'] for m in metrics} == {'service'}


def test_the_brief_lists_the_key_inputs_that_the_file_names(tmp_path):
    keys = ['service.users', 'attacker.reaction_time', 'service.repair_time']

    def edit(draft):
        with_human_runs(draft)
        draft.sheet['drivers'] = list(keys)

    generated = pages(build(tmp_path, edit))
    # The brief's drivers, in its order, by their names in the structure. The main controls do not
    # follow them: they are the inputs that the options set.
    assert generated['story']['key_inputs'] == keys
    model = build(tmp_path, with_human_runs)
    assert generated['controls'] == pages(model)['controls'] != keys
    # Without them, the brief lists the controls.
    assert pages(model)['story']['key_inputs'] == pages(model)['controls']


@pytest.mark.parametrize('name', ['service.waiting', 'service.nothing', 'nobody.users', 'attacker.actor'])
def test_key_inputs_name_inputs(tmp_path, name):
    """The pages check the names of the brief settings when they read them (the check lives once, in
    their reader), so they never meet a name that is not an input. The model never reads the brief
    settings, so it builds."""

    def edit(draft):
        with_human_runs(draft)
        draft.sheet['drivers'] = ['service.users', name]

    model = build(tmp_path, edit)
    with pytest.raises(StyleError) as caught:
        pages(model)
    (error,) = caught.value.diagnostics
    # The problem names the file, the key of the list that holds the name, and the name.
    assert (error['file'], error['key']) == (str(tmp_path / 'brief.toml'), 'drivers')
    assert name in error['message']


def test_the_main_inputs_are_those_that_options_set(tmp_path):
    # The menu's groups in order: Response (`Fast repair` sets the repair time), Access (`Keeps
    # access` sets a start state, which is no input), Attacker (`Human team` sets the reaction time
    # and a text) and Load (`Heavy load` sets the load).
    model = build(tmp_path, with_human_runs, with_load)
    assert list(written(tmp_path).menu()) == ['Response', 'Access', 'Attacker', 'Load']
    assert pages(model)['controls'] == ['service.repair_time', 'attacker.reaction_time', 'service.load']

    model = build(tmp_path, with_human_runs, with_load, load_first)
    assert pages(model)['controls'] == ['service.load', 'service.repair_time', 'attacker.reaction_time']


# ---- options and runs ---------------------------------------------------------------------------


def test_the_options_are_the_groups_that_set_start_states(tmp_path):
    model = build(tmp_path, with_human_runs)
    menu = written(tmp_path).menu()
    options = pages(model)['options']
    # Access holds the profile that sets a start state; the human team only edits some runs.
    assert options['axis'] == {'name': 'Access', 'groups': ['Access']}
    assert options['options'] == [
        {'name': name, 'options': [name], 'doc': line} for name, line in menu['Access'].items()
    ]
    assert options['responses'] == [
        {'name': p, 'doc': line} for p, line in menu[styles.brief_of(model).choice_group].items()
    ]


def test_a_run_that_names_no_option_takes_the_one_that_sets_nothing(tmp_path):
    model = build(tmp_path)
    runs = written(tmp_path).runs()
    generated = pages(model)['runs']
    # `slow` names no profile of Access, which holds the start state: `No access` sets nothing.
    assert 'No access' not in runs['slow'] and generated['slow']['option'] == 'No access'
    assert generated['slow_kept']['option'] == 'Keeps access'


def test_a_group_that_every_run_names_is_an_option_too(tmp_path):
    model = build(tmp_path, with_human_runs, with_load)
    generated = pages(model)
    assert generated['options']['axis'] == {'name': 'Access · Load', 'groups': ['Access', 'Load']}
    for run, info in model.runs.items():
        option = [p for p in info['options'] if p in ('Keeps access', 'Light load', 'Heavy load')]
        if 'Keeps access' not in option:
            option.insert(0, 'No access')
        assert generated['runs'][run]['option'] == ' · '.join(option)
    names = [o['name'] for o in generated['options']['options']]
    assert sorted(names) == sorted({r['option'] for r in generated['runs'].values()})


def test_runs_with_no_options_have_no_name_for_them(tmp_path):
    def edit(draft):
        draft.edit(drop('options:/Access', 'runs:/slow_kept'))
        draft.sheet['featured'] = ['slow']

    generated = pages(build(tmp_path, edit))
    assert generated['options']['axis'] is None
    assert generated['options']['options'] == [{'name': '', 'options': [], 'doc': None}]
    assert {run['option'] for run in generated['runs'].values()} == {''}


def test_each_run_has_its_response_and_its_comparison(tmp_path):
    model = build(tmp_path, with_human_runs)
    file = written(tmp_path)
    menu = file.menu()
    human = number_of(file.value('options:/Attacker/Human team/attacker.reaction_time'))
    runs = pages(model)['runs']
    for run, info in model.runs.items():
        (response,) = [p for p in info['options'] if p in menu[styles.brief_of(model).choice_group]]
        assert (runs[run]['name'], runs[run]['response']) == (info['name'], response)
    # Each comparison is a run that names the run it compares with.
    comparisons = {run: r['comparison_of'] for run, r in runs.items() if r['comparison_of']}
    assert comparisons == {'slow_kept_human': 'slow_kept', 'fast_kept_human': 'fast_kept'}
    # Its narrative is the profiles that it adds to that run; the inputs they set are its own.
    for run in comparisons:
        assert runs[run]['narrative'] == menu['Attacker']['Human team']
        assert runs[run]['inputs'] == {'attacker.reaction_time': human}
    assert all(
        r['narrative'] is None and r['inputs'] == {} for run, r in runs.items() if run not in comparisons
    )


# ---- inputs, names and labels -------------------------------------------------------------------

# The title of an entity, which holds an acronym.
GATEWAY = 'SCADA gateway'


def with_more_entities(draft):
    """An entity with a title of its own, a template with two entities (one with a text of its own,
    and the text of a value that it changes), and two copies of a template, which share its texts."""
    draft.edit(
        before(
            'options:/Response',
            entity(
                'gateway',
                parameter('delay', 1, 'h', 0, 5, doc='Delay of a command', records='@ident'),
                doc='The gateway between the switch and the control room.',
                role='operator',
                records='@ident',
                title=GATEWAY,
            ),
            '',
            template(
                'Queue',
                parameter('size', 300, 'people', 0, 1000, doc='Users in the queue', records='@ident'),
                value('stock', 'waiting', 'size', 'people', doc='Users still waiting', records='@ident'),
                doc='A queue of users.',
                role='community',
                records='@ident',
            ),
            '',
            entity('small', template='Queue', records=None),
            '',
            entity(
                'large',
                quote('The queue of the large customers.'),
                block('size:', quote('Users in the large queue')),
                template='Queue',
                records=None,
            ),
            '',
            template(
                'Lane',
                value('stock', 'cars', 0, 'people', doc='Cars in the lane', records='@ident'),
                value('stock', 'chargers', 0, 'people', doc='EV chargers in the lane', records='@ident'),
                doc='A lane of the road to the service.',
                role='environment',
                records='@ident',
            ),
            '',
            entity('lanes', template='Lane', copies=2, records=None),
            '',
        )
    )


def test_an_entity_is_named_by_its_class_or_by_its_own_name(tmp_path):
    names = pages(build(tmp_path, with_more_entities))['entities']
    # An entity: its title, or else its own name in words, as an entity of a template is. A copy: its
    # set and its number. A text never names one.
    assert {e: names[e] for e in ('switch', 'service', 'responders', 'gateway')} == {
        'switch': 'Switch',
        'service': 'Service',
        'responders': 'Responders',
        'gateway': GATEWAY,
    }
    assert [names[e] for e in ('small', 'large', 'lanes_1', 'lanes_2')] == [
        'Small',
        'Large',
        'Lanes 1',
        'Lanes 2',
    ]


def test_entities_of_one_class_never_show_one_label(tmp_path):
    labels = pages(build(tmp_path, with_more_entities))['labels']
    # A text that two entities share starts with each entity's name and goes on in lower case; an
    # acronym keeps its capitals; a text of an entity's own stays as it is.
    assert (labels['quantities']['small.waiting'], labels['quantities']['large.waiting']) == (
        'Small: users still waiting',
        'Large: users still waiting',
    )
    assert [labels['quantities'][f'lanes_{k}.cars'] for k in (1, 2)] == [
        'Lanes 1: cars in the lane',
        'Lanes 2: cars in the lane',
    ]
    assert labels['quantities']['lanes_1.chargers'] == 'Lanes 1: EV chargers in the lane'
    assert (labels['inputs']['large.size'], labels['inputs']['small.size']) == (
        'Users in the large queue',
        'Users in the queue',
    )
    assert labels['inputs']['gateway.delay'] == 'Delay of a command'


def test_each_entity_with_inputs_has_an_input_group(tmp_path):
    model = build(tmp_path, with_more_entities)
    texts = written(tmp_path).texts
    generated = pages(model)
    groups = {g['entity']: g for g in generated['groups']}
    # The entity's name labels the group, and its text, its own or its template's, describes it.
    for entity_name, doc in (
        ('small', texts['Queue/""']),
        ('large', texts['large/""']),
        ('gateway', texts['gateway/""']),
    ):
        assert (groups[entity_name]['name'], groups[entity_name]['doc']) == (
            generated['entities'][entity_name],
            doc,
        )
    # Each input is in the group of its entity, once, in the model's order; an entity without
    # inputs has no group.
    assert [i for g in generated['groups'] for i in g['inputs']] == list(model.inputs)
    assert all(model.inputs[i]['entity'] == g['entity'] for g in generated['groups'] for i in g['inputs'])
    assert 'switch' not in groups and 'lanes_0' not in groups


def test_the_entities_that_show_a_status(tmp_path):
    def edit(draft):
        draft.edit(
            member('responders', status(('ok', 'attacker.access is "removed"', 'Done'), ('ok', None, 'Busy')))
        )

    model = build(tmp_path, edit)
    # The service shows a status; the responders show one of their own.
    assert pages(model)['statuses'] == ['service', 'responders']
    entities = model.whole[()].entities
    assert all(entities[e].health for e in pages(model)['statuses'])


# ---- the review and the attacker ----------------------------------------------------------------


def test_the_review_gives_its_records_to_the_pages(tmp_path):
    def edit(draft):
        with_outputs(draft)
        draft.edit(
            member('notes:/premises:', 'P1: "The users wait."  @ident'),
            member(
                'notes:',
                block('limitations:', 'L1: "The users are synthetic."  @ident'),
                'exposure: "The users of the service set the study area."',
                block('benchmark:', 'kind: "published_source_benchmark"', 'excess_deaths: 3'),
            ),
        )

    model = build(tmp_path, edit)
    file = written(tmp_path)
    review = pages(model)['review']
    written_review = file.review()
    assert review['limitations'] == [{'id': 'L1', 'statement': written_review['limitations'][0]['statement']}]
    # The premise with id START gives the limits of the first move, apart from the other premises; a
    # named record is written out as its record.
    (premise,) = review['premises']
    assert premise['id'] == 'P1' and premise['basis'] == file.record('ident')
    (start,) = [p for p in written_review['premises'] if p['id'] == 'START']
    assert review['start_limits'] == start['statement']
    assert review['benchmark'] == written_review['benchmark']
    assert 'verification' not in review and 'reachability' not in review
    outcome = model.outputs['reach']
    assert review['exposure'] == {
        'outcome': outcome,
        'scope': file.texts['output:/reach/scope:'],
        'interpretation': written_review['exposure'],
    }


def test_the_operation_is_the_entity_with_the_role_adversary(tmp_path):
    model = build(tmp_path)
    file = written(tmp_path)
    attacker = file.thing('attacker')
    operation = pages(model)['operation']
    assert operation['doc'] == attacker.text.value
    assert attacker.text.value.startswith(operation['actor'] + '. ')
    assert operation['entity'] == 'attacker' == model.initiation['entity']
    (cited,) = attacker.support
    assert operation['basis']['kind'] == file.record(cited.name)['kind']
    # The delay names an input that no profile sets: no tempo. No profile changes the attacker's name.
    assert operation['tempo'] is None
    assert operation['human_runs'] == []


def test_the_tempo_is_the_input_of_a_wait_that_a_run_s_other_options_set(tmp_path):
    model = build(tmp_path, with_human_runs)
    assert pages(model)['operation']['tempo'] == 'attacker.reaction_time'

    # A profile of the choice group that sets the delay's input is a response, not a tempo.
    def response(draft):
        with_human_runs(draft)
        draft.edit(
            drop('options:/Attacker/Human team/attacker.reaction_time'),
            member('options:/Response/Fast repair', 'attacker.reaction_time = 20 h  @ident'),
        )

    assert pages(build(tmp_path, response))['operation']['tempo'] is None


def test_the_pages_show_one_ai_operation(tmp_path):
    """The role is a tag that only the pages read. The model builds with two entities tagged adversary;
    the pages, which show one AI operation, reject it, at the file's line of one of the two."""
    model = build(tmp_path, lambda d: d.edit(reline('responders/role:', 'role adversary')))
    with pytest.raises(ModelError, match='the pages show one AI operation') as caught:
        pages(model)
    (found,) = caught.value.diagnostics
    tagged = ('attacker', 'responders')
    assert found['path'] in {*tagged, *(f'{e}/role:' for e in tagged)}
    assert found['line'] == {path_text(where): line for where, line in model.lines.items()}[found['path']]


def test_the_start_of_an_operation_acts_as_the_entity_of_its_first_effect(tmp_path):
    """The card of the start shows the entity whose event it is, as the builder reads the start, also
    when no entity is tagged adversary: its role is the card's actor, and its text values fill the
    braces."""
    text = '{actor} starts to prepare the strike on the switch.'

    def untagged(draft):
        with_start_text(text)(draft)
        draft.edit(reline('attacker/role:', 'role contractor'))

    model = build(tmp_path, untagged)
    generated = pages(model)
    assert generated['operation'] is None
    file = written(tmp_path)
    # The start is the event `start` of the entity that it acts as.
    (owner,) = [
        thing.name
        for thing in file.parts.things
        if any(isinstance(m, Event) and m.name == 'start' for m in thing.members)
    ]
    assert model.initiation['entity'] == owner
    assert generated['cards'][model.events[f'{owner}.start.done']] == [
        {'text': text.replace('{', f'{{{owner}.'), 'actor': 'contractor'}
    ]
    # The builder fills the start's label from the same entity: its actor text, with no braces left.
    actor = file.value(f'{owner}/actor')
    assert model.structure_of('slow').rules[model.initiation['rule']].label == text.replace('{actor}', actor)


def test_a_document_without_an_adversary_has_no_operation(tmp_path):
    """A file outside the catalogue can have no adversary: its pages have no AI operation, and every
    card and run is still generated."""

    def edit(draft):
        draft.edit(reline('attacker/role:', 'role operator'))
        with_start_text('The service is switched off.')(draft)

    model = build(tmp_path, edit)
    generated = pages(model)
    assert generated['operation'] is None
    # The attacker's moves are the operator's now: their cards show its role.
    attacker = written(tmp_path).thing('attacker')
    assert generated['cards'][model.events['attacker.start.done']][0]['actor'] == attacker.role
    assert set(generated['runs']) == set(model.runs)


# ---- every catalogue scenario -------------------------------------------------------------------


@pytest.mark.scenario_contract
@pytest.mark.parametrize('sid', SCENARIO_IDS)
def test_the_pages_of_every_scenario_keep_the_rules_of_the_language(sid):
    model = catalogue_model(sid)
    generated = Pages(model).all()
    brief = styles.brief_of(model)
    structure_events = {e for whole in model.whole.values() for e in whole.events}
    entities = set(model.entities)

    # Cards: each is an event of the model, its actor a role that the pages name or an entity, and
    # each field it names in braces is a text of every run.
    assert generated['cards'] and set(generated['cards']) <= set(model.events.values()) & structure_events
    for cards in generated['cards'].values():
        assert all(card['actor'] in ACTOR_NAMES or card['actor'] in entities for card in cards)
        assert [card.get('occurrence') for card in cards] in ([None], list(range(1, len(cards) + 1)))
        for card in cards:
            for field in re.findall(r'\{([^}]+)\}', card['text']):
                assert all(field in texts for texts in generated['texts'].values()), field
    assert set(generated['texts']) == set(model.runs)

    # Options and runs: every run has its option of the brief's `choice_group` as its response, and
    # one of the options; the options are named after their groups and listed once each.
    options = generated['options']
    menu = thaw(model.menu)
    names = [o['name'] for o in options['options']]
    assert len(names) == len(set(names))
    swapped = menu.get(styles.brief_of(model).choice_group) or {}
    assert [r['name'] for r in options['responses']] == list(swapped)
    groups = options['axis']['groups'] if options['axis'] else []
    for item in options['options']:
        assert item['name'] == ' · '.join(item['options'])
        assert [g for p in item['options'] for g in menu if p in menu[g]] == groups
    for run, info in generated['runs'].items():
        assert info['response'] == next((p for p in model.runs[run]['options'] if p in swapped), None)
        assert info['option'] in names
        assert info['name'] == model.runs[run]['name']
        assert set(info['inputs']) <= set(model.inputs)
        other = info['comparison_of']
        assert other == model.runs[run]['comparison_of']
        if other is not None:
            assert generated['runs'][other]['comparison_of'] is None and info['narrative']
    # The options that set start states make the runs' options: runs of one option share one structure.
    starts = {}
    for run, info in generated['runs'].items():
        starts.setdefault(info['option'], set()).add(model.runs[run]['starts'])
    assert all(len(s) == 1 for s in starts.values())

    # The metrics are the outputs of show; each shows the harm that the builder says it counts.
    outcomes = next(iter(model.whole.values())).outcomes
    shown = [model.outputs[x] for x in styles.shown(brief, model)]
    assert [m['outcome'] for m in generated['metrics']] == shown
    harms = {'deaths': 'deaths', 'casualties': 'casualties', 'loss': 'loss'}
    for metric in generated['metrics']:
        assert metric['style'] == harms.get(outcomes[metric['outcome']].category, 'service')

    # The brief: its two runs are the default runs, its measures totals of show that report nothing.
    story = generated['story']
    featured = styles.featured(brief, model)
    if len(featured) == 2:
        assert story['runs'] == featured
        exposure = generated['review'].get('exposure', {}).get('outcome')
        assert set(story['measures']) <= set(shown) - {exposure} and len(story['measures']) <= 2
        assert all(
            outcomes[m].kind == 'cumulative' and outcomes[m].category is None for m in story['measures']
        )
        assert story['key_inputs'] and set(story['key_inputs']) <= set(model.inputs)
        assert thaw(model.scenario.summary).startswith(story['hook'])
    else:
        assert story is None

    # Inputs: the controls and every group's inputs are inputs; each input is in one group, its
    # entity's, and each group is named and described.
    assert set(generated['controls']) <= set(model.inputs)
    assert len(generated['controls']) == len(set(generated['controls']))
    grouped = [i for g in generated['groups'] for i in g['inputs']]
    assert sorted(grouped) == sorted(model.inputs)
    for group in generated['groups']:
        assert group['doc'] and group['name'] == generated['entities'][group['entity']]
        assert {model.inputs[i]['entity'] for i in group['inputs']} == {group['entity']}

    # Names: every entity has a short name of its own; no two inputs or quantities show one label.
    listed = [generated['entities'][e] for e in entities if e in generated['entities'] and e != 'simulate']
    assert len(set(listed)) == len(listed)
    assert all('.' not in label and '_' not in label and label[:1].isupper() for label in listed)
    for section in ('inputs', 'quantities'):
        labels = list(generated['labels'][section].values())
        assert len(set(labels)) == len(labels), section
    assert set(generated['statuses']) <= entities

    # The review and the attacker.
    review = generated['review']
    assert all(p.get('id') != 'START' for p in review['premises'])
    assert all(isinstance(p.get('basis', {}), dict) for p in review['premises'])
    if 'exposure' in review:
        assert review['exposure']['outcome'] in model.outputs.values() and review['exposure']['scope']
    operation = generated['operation']
    adversary = operation['entity']
    assert adversary in entities
    assert operation['tempo'] is None or model.inputs[operation['tempo']]['entity'] == adversary
    assert operation['doc'].startswith(operation['actor'])


# ---- a file of the tests' own -------------------------------------------------------------------

# A model file of the test's own: the attacker jams a switch after a delay that a human team takes
# longer for. The Attacker group is named by one run only, so it is not an option of the runs.
DONE = '{actor} jams the switch.'
OWN = f'''\
scenario "A test"
    summary "A file for tests only. The attacker jams a switch."
    horizon 100 h
    scope "The test."

attacker:  @counts
    "The AI agent. It jams the switch of the service."
    role adversary
    input actor = "The AI agent"
    input reaction_time = 2 h in 0.1 h to 72 h  @counts
        "Time the attacker needs to act"
    var access: "none" | "kept" = "none"
    event enters once when access is "kept":  @counts
    event jam once after reaction_time when since(enters) >= 1 h:  @counts
        "The attacker gets ready to jam the switch."
        done:  @counts
            "{DONE}"
            service.switch = "jammed"
    event start when t >= 0 h:  @counts
        "The attacker gets in."
        access = "kept"

service:  @counts
    "A service."
    role operator
    var switch: "on" | "jammed" = "on"
        "Switch"

options "Response":
    "Fast":
        "Fast."
    "Slow":
        "Slow."

options "Attacker":
    "AI agent":
        "The AI agent."
    "Human team":
        "A human team."
        attacker.actor = "The human team"
        attacker.reaction_time = 48 h  @counts

runs:
    fast = "Fast"
    fast_human = "Fast" + "Human team" versus fast
        "The fast response against a human team"

notes:
    premises:
        START: "The attacker has access."
        P1: "The users wait."  @counts

record counts: identity "The test counts."
'''


def built_own(tmp_path, text=OWN):
    path = tmp_path / 'model.scn'
    path.write_text(text, encoding='utf-8')
    return build_model(path, LIBRARY)


def test_own_braces_name_the_text_value_of_the_entity_that_acts_as_each_run_sets_it(tmp_path):
    model = built_own(tmp_path)
    generated = pages(model)
    (card,) = generated['cards'][model.events['attacker.jam.done']]
    assert card['text'] == DONE.replace('{', '{attacker.')
    assert {run: texts['attacker.actor'] for run, texts in generated['texts'].items()} == {
        'fast': 'The AI agent',
        'fast_human': 'The human team',
    }
    # The human team acts in the run whose profiles give the attacker's name another text.
    assert generated['operation']['human_runs'] == ['fast_human']


def test_own_the_tempo_is_the_input_of_a_wait_that_a_run_s_other_profiles_set(tmp_path):
    assert pages(built_own(tmp_path))['operation']['tempo'] == 'attacker.reaction_time'
    # A profile of the choice group that sets the delay's input is a response, not a tempo.
    response = OWN.replace('        attacker.reaction_time = 48 h  @counts\n', '').replace(
        '    "Slow":\n        "Slow."\n',
        '    "Slow":\n        "Slow."\n        attacker.reaction_time = 48 h  @counts\n',
    )
    assert response != OWN
    assert pages(built_own(tmp_path, response))['operation']['tempo'] is None


def test_own_the_review_gives_the_records_of_its_premises_to_the_pages(tmp_path):
    model = built_own(tmp_path)
    review = pages(model)['review']
    (premise,) = review['premises']
    assert premise['id'] == 'P1' and premise['basis'] == {
        'kind': 'identity',
        'explanation': 'The test counts.',
        'name': 'counts',
    }
    assert review['start_limits'] == 'The attacker has access.'
    # The review's records support no part of the model.
    assert not [use for use in model.index['uses'] if use['part'].startswith('review')]
