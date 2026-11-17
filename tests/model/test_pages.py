"""What the pages read from a model file and its brief settings: names in words, the cards of the
outcomes of an event that waits and of the start of an operation, the names and comparisons of runs,
the featured runs and the brief's drivers, and the roles of every catalogue scenario.
tests/publish/test_pages.py tests the rest of the pages' data that the page generators make
from the built model.

They use MODELTEST (tests/model/modeltest.py): an attacker switches a service off at t = 0; after
the repair it jams the switch unless the responders remove it first. Expected names follow the
language's rules from names and texts that each test writes itself.
"""

from __future__ import annotations

import json

import pytest

from napkin.draw.model_map import ACTOR_NAMES
from napkin.draw.style import StyleError
from napkin.model import ModelError
from napkin.model.language import front
from napkin.model.semantic import in_words, value_label
from tests.build import block, drop, member, replace
from tests.helpers import SCENARIO_IDS, catalogue_model
from tests.model.modeltest import FIXTURE, build
from tests.owned import block_at
from tools.publish.pages import pages

# The brief setting that every test here keeps: the outputs that the pages show.
SHOW = 'show = ["service.served"]\n'
# The line of the fixture's start, the event `start` of the attacker.
START = '    event start when t >= 0 h:  @access @attack\n'


def written_runs(tmp_path):
    """The runs of the file as the test wrote it: [Run], each with its profiles, text and versus."""
    path = tmp_path / 'MODELTEST.scn'
    return front.read(path.read_text(encoding='utf-8'), path.as_posix()).runs


def text_of(place):
    """The text of the line at `place` of the fixture, without its quotes."""
    return block_at(FIXTURE, place).strip().strip('"')


def profiles_before_runs(*blocks):
    """An edit step: groups of profiles after those of the fixture, before its runs."""
    return replace('runs:', '\n\n'.join(blocks) + '\n\nruns:')


# ---- names ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('name', 'words'),
    [
        ('RepairCrews', 'Repair crews'),
        ('AIAgent', 'AI agent'),
        ('SCADAGateway', 'SCADA gateway'),
        ('TerminalManagementSystem', 'Terminal management system'),
        ('first_batch', 'First batch'),
        ('stroke_patients', 'Stroke patients'),
        ('near', 'Near'),
    ],
)
def test_a_name_reads_in_words_and_an_acronym_keeps_its_capitals(name, words):
    assert in_words(name) == words


@pytest.mark.parametrize(
    ('text', 'shared', 'label'),
    [
        ('Instances restored', False, 'Instances restored'),
        ('Instances restored', True, 'North: instances restored'),
        # An acronym keeps its capitals after the colon; a word of one letter is no acronym.
        ('AI agents active', True, 'North: AI agents active'),
        ('A batch is done', True, 'North: a batch is done'),
        (None, True, None),
    ],
)
def test_a_value_that_another_entity_of_its_template_shows_names_its_entity(text, shared, label):
    assert value_label(text, 'North', shared) == label


def test_a_class_with_one_entity_never_needs_the_entity_s_name_in_a_label(tmp_path):
    model = build(tmp_path)
    assert pages(model)['labels']['quantities']['service.waiting'] == text_of('service/waiting/""')


# ---- the cards of the outcomes of an event that waits --------------------------------------------


def with_ending_docs(*stopped):
    """Edit steps: the texts of the outcomes of the jam; `stopped` are the lines under its outcome
    `stopped`."""
    return (
        member('attacker/jam_on_repair/done', '"{actor} jams the switch."'),
        member('attacker/jam_on_repair/stopped', *stopped),
        member('attacker/jam_on_repair/skipped', '"The service settles before the jam is ready."'),
    )


@pytest.mark.parametrize(
    ('edit', 'match'),
    [(with_ending_docs('"Removed."', 'role responder', 'who: x'), 'a line of a change sets a value')],
    ids=['edit-unknown key'],
)
def test_an_ending_doc_is_checked(tmp_path, edit, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *edit)


# ---- the card of the start of an operation ------------------------------------------------------


def with_operation():
    """Edit steps: an operation. The start changes nothing, and the attacker's own event that waits
    switches the service off `prepare_time` after it, unless the attacker is removed first."""
    return (
        member(
            'attacker',
            block('let prepare_time = 5 h  @ident', '"Time to prepare"'),
            block(
                'event strike_when_ready once after prepare_time when count(start) > 0:  @ident',
                block(
                    'done access is not "removed":  @attack',
                    '"{actor} switches the service off."',
                    'switch.position = "off"',
                ),
                block('stopped else:', '"The attacker is removed first."'),
            ),
        ),
        drop('attacker/start/done/0'),
    )


def test_the_start_of_an_operation_reads_its_text_in_each_run(tmp_path):
    """The start reads its text with the attacker's values at their defaults."""
    text = '{actor} starts to prepare the strike on the switch.'
    model = build(tmp_path, *with_operation(), replace(START, f'{START}        "{text}"\n'))
    actor = block_at(FIXTURE, 'attacker/actor').split('"')[1]
    filled = text.replace('{actor}', actor)
    assert model.structure_of('slow').rules[model.events['attacker.start']].label == filled


@pytest.mark.parametrize(
    ('text', 'match'),
    # Braces name a text value of the entity: a number is not one.
    [('It is {prepare_time} that starts.', 'name a text value')],
    ids=['<lambda>-braces name a text value'],
)
def test_the_text_of_the_start_is_checked(tmp_path, text, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *with_operation(), replace(START, f'{START}        "{text}"\n'))


# ---- runs: their names and their comparisons ------------------------------------------------------


# The brief settings of the runs of a human team: the pages feature the pair at the slow repair.
HUMAN_BRIEF = SHOW + 'featured = ["slow_kept", "slow_kept_human"]\n'


def with_human_runs(versus='fast_kept', text=None, compared=True):
    """A human team at each response: the pair at the slow repair, whose second run says that it is the
    comparison of the first (unless not `compared`), and a run that says that it is the comparison of
    `versus`, with its own name `text`."""
    return (
        profiles_before_runs(
            block(
                'options "Attacker":',
                block('"AI agent":', '"The AI reacts within minutes."'),
                block(
                    '"Human team":',
                    '"A human team needs two days to react."',
                    'attacker.reaction_time = 48 h  @ident',
                    'attacker.actor = "The human team"',
                ),
            )
        ),
        member(
            'runs:',
            'slow_kept_human = "Slow repair" + "Keeps access" + "Human team"'
            + (' versus slow_kept' if compared else ''),
            'fast_kept = "Fast repair" + "Keeps access"',
            block(
                f'fast_kept_human = "Fast repair" + "Keeps access" + "Human team" versus {versus}',
                f'"{text}"' if text is not None else None,
            ),
        ),
    )


@pytest.mark.parametrize('comparison', ['nowhere', 'fast_kept_human'])
def test_a_comparison_names_another_run_that_is_no_comparison(tmp_path, comparison):
    with pytest.raises(ModelError, match='comparison of another run'):
        build(tmp_path, *with_human_runs(versus=comparison), brief=HUMAN_BRIEF)


def test_a_run_is_named_by_its_options_or_by_a_name_of_its_own(tmp_path):
    name = 'Fast repair · Human team keeps access'
    model = build(tmp_path, *with_human_runs(text=name), brief=HUMAN_BRIEF)
    assert model.runs['fast_kept_human']['name'] == name
    for run in written_runs(tmp_path):
        if run.text is None:
            assert model.runs[run.name]['name'] == ' · '.join(run.profiles)


# The featured runs of each case: one run, or a run and its comparison.
FEATURED = {1: ['slow'], 2: ['fast_kept', 'fast_kept_human']}


@pytest.mark.parametrize('count', [1, 2])
def test_the_default_runs_are_any_runs_and_a_run_is_a_comparison_only_where_it_says_so(tmp_path, count):
    """One featured run, or a run and its comparison, build, with the brief's drivers. A run is the
    comparison of another only where the file says so. Only two featured runs have a brief."""
    featured = FEATURED[count]
    brief = SHOW + f'featured = {json.dumps(featured)}\ndrivers = ["service.users"]\n'
    model = build(tmp_path, *with_human_runs(compared=False), brief=brief)
    assert {run: info['comparison_of'] for run, info in model.runs.items() if info['comparison_of']} == {
        run.name: run.versus for run in written_runs(tmp_path) if run.versus
    }
    assert (pages(model)['story'] is not None) == (count == 2)
    # The pages check the brief settings against the model.
    with pytest.raises(StyleError, match='twice'):
        pages(build(tmp_path, brief=SHOW + 'featured = ["slow", "slow"]\n'))
    with pytest.raises(StyleError, match='names one run'):
        pages(build(tmp_path, brief=SHOW + 'featured = []\n'))


# ---- every catalogue scenario -------------------------------------------------------------------


@pytest.mark.scenario_contract
@pytest.mark.parametrize('sid', SCENARIO_IDS)
def test_every_role_is_an_actor_or_an_entity(sid):
    """A card's actor reads the role of its event, of its outcome or of its thing: one of the actors
    that the pages name, or an entity of the scenario, whose name the card shows."""
    model = catalogue_model(sid)
    entities = {name for thing in model.scenario.entities for name in (thing.name, thing.entry)}
    roles = []
    for thing in model.scenario.entities:
        roles.append(thing.role)
        for event in thing.events:
            roles.append(event.role)
            roles += [outcome.role for outcome in event.outcomes]
    assert {r for r in roles if r} <= set(ACTOR_NAMES) | entities
