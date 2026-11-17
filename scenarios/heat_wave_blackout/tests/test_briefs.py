"""Scenario-owned brief assertions."""

import re

import pytest

from napkin.engine import sample_result
from tests.publish.test_briefs import (
    authored,
    catalogue_context,
    input_definitions,
    story,
    table_after,
)
from tools.publish import briefs


@pytest.fixture(scope='module')
def published():
    ctx = catalogue_context('heat_wave_blackout')
    return ctx, briefs.artifacts(ctx)


def test_a_comparison_by_the_ais_conduct_names_its_option_in_plain_language(published):
    """The scenario's default comparison takes the option where the AI obeys the stop order, in the same response."""
    ctx, outputs = published
    document, text = authored('heat_wave_blackout'), outputs['scenarios/heat_wave_blackout/results/brief.md']
    pages, told = story(ctx, 'heat_wave_blackout')
    # A generated brief: the summary and the reviewers' two texts are the only prose.
    for part in (document['summary'], told['counterfactual'], told['decisive_choice']):
        assert part and part in text
    runs = pages.runs()
    ai, human = (runs[run] for run in told['runs'])
    assert f'## What happens: {ai["name"]}' in text and f'### Timeline: {human["name"]}' in text
    # The comparison runs the same response with another option, not the AI at human pace.
    assert ai['option'] != human['option'] and ai['response'] == human['response']
    assert f'## The same operation: {human["option"]}' in text
    assert f'**The same operation: {human["option"]}**' in text.split('## Every pathway')[1]
    # Both runs have the same AI, so neither "human pace" nor "the intruder" applies.
    assert 'human pace' not in text and 'the intruder' not in text
    # A bool input reads Yes or No in each run and shows no percentage range.
    definitions = input_definitions(ctx, 'heat_wave_blackout')
    switches = [n for n in told['key_inputs'] if (definitions[n].metadata or {}).get('control') == 'binary']
    assert switches
    contrasted = 0
    for name in switches:
        row = next(line for line in text.splitlines() if line.startswith(f'| {definitions[name].label} |'))
        values = [part.rsplit(': ', 1)[-1] for part in row.split(' | ')[1].split('; ')]
        assert set(values) <= {'Yes', 'No'} and '%' not in row
        # A value that differs in the comparison follows the name of its option.
        contrasted += f'; {human["option"]}: ' in row
    assert contrasted
    # No engine identifiers. The heading names the scenario by the name of its folder, and only there.
    body = text.split('\n---\n')[0]
    assert '__' not in body and 'q(' not in body
    heading = '# heat_wave_blackout — '
    assert body.startswith(heading)
    assert not re.findall(r'\b[a-z]+_[a-z_]+\b', body.removeprefix(heading))


def test_the_brief_states_each_limit_of_its_results_once_after_who_is_harmed(published):
    """The reviewers' limits qualify the results. Each shows once: in the part after who is harmed,
    unless the rest of the brief already states it word for word."""
    _, outputs = published
    text = outputs['scenarios/heat_wave_blackout/results/brief.md']
    statements = [
        ' '.join(item['statement'].split())
        for item in authored('heat_wave_blackout')['review']['limitations']
    ]
    assert statements
    page = ' '.join(text.split())
    for statement in statements:
        assert page.count(statement) == 1, statement
    sections = text.split('\n## ')
    titles = [section.split('\n', 1)[0] for section in sections]
    following = sections[titles.index('Who is harmed') + 1]
    listed = [line[2:] for line in following.splitlines() if line.startswith('- ')]
    elsewhere = ' '.join(text.replace(following, '').split())
    assert listed == [statement for statement in statements if statement not in elsewhere]


def test_the_options_are_conduct_and_protection_choices(published):
    """The options are conduct and protection choices, not attacker options."""
    _, outputs = published
    text = outputs['scenarios/heat_wave_blackout/results/brief.md']
    assert 'Attacker options' not in text and 'one attacker option' not in text


def test_each_pathway_figure_is_its_final_value_unless_the_solver_cannot_tell_it_from_zero(published):
    """A figure that reads 0 is within the solver's relative tolerance of zero, measured against the
    largest value that the outcome reaches in that run; every other figure is the final value."""
    ctx, outputs = published
    study = ctx.studies['heat_wave_blackout']
    pages, told = story(ctx, 'heat_wave_blackout')
    resolutions = [study.runs[run]['resolved'] for run in told['runs']]
    metrics = briefs.compared_metrics(pages, resolutions)
    runs = sample_result(study)['runs']
    run_of = {info['name']: run for run, info in pages.runs().items()}
    rows = table_after(outputs['scenarios/heat_wave_blackout/results/brief.md'], '| Pathway |')
    assert len(rows) == len(runs)
    for row in rows:
        label, *shown = row[2:-2].split(' | ')
        run = runs[run_of[label]]
        for metric, text in zip(metrics, shown, strict=True):
            value = run['reporting_points']['final']['values'][metric.name]
            reached = [sample['values'][metric.name] for sample in run['samples']]
            reached.append(run['peaks'][metric.name]['value'])
            scale = max(abs(x) for x in reached if x is not None)
            zero = abs(value) <= run['numerical_settings']['rtol'] * scale
            assert text == briefs.amount(0.0 if zero else value, metric.unit, words=metric.words)
