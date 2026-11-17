"""Scenario-owned brief assertions."""

import re

import pytest

from napkin.engine import sample_result
from napkin.model.ir import basis_records
from tests.publish.test_briefs import (
    authored,
    catalogue_context,
    changed_by,
    elapsed,
    harm_metrics,
    input_definitions,
    outcome_definitions,
    story,
    table_after,
    timeline_rows,
)
from tools.publish import Context, briefs
from tools.publish.brief import brief_of


@pytest.fixture(scope='module')
def published():
    ctx = catalogue_context('iv_fluid_shortage')
    return ctx, briefs.artifacts(ctx)


def test_a_generated_brief_follows_the_summary_the_review_and_both_default_runs(published):
    """A brief is generated: the main run's events are its steps and the human run's events
    its timeline. Only the summary and the reviewers' two texts are written by hand."""
    ctx, outputs = published
    document, text = authored('iv_fluid_shortage'), outputs['scenarios/iv_fluid_shortage/results/brief.md']
    pages, told = story(ctx, 'iv_fluid_shortage')
    assert told['hook'] and document['summary'].startswith(told['hook'])
    for part in (document['summary'], told['counterfactual'], told['decisive_choice']):
        assert part and part in text
    ai, human = told['runs']
    runs = pages.runs()
    sections = {
        ai: text.split(f'## What happens: {runs[ai]["name"]}\n')[1],
        human: text.split(f'### Timeline: {runs[human]["name"]}\n')[1],
    }
    # The wording fields that differ between the two runs, such as who acts.
    fields = pages.texts()
    differing = [name for name in fields[ai] if fields[ai][name] != fields[human][name]]
    assert differing
    for run, rival in ((ai, human), (human, ai)):
        rows = timeline_rows(sections[run])
        times = [elapsed(label) for label, _ in rows]
        assert times[0] == 0 and times == sorted(times)
        # Each run's rows are its events' docs with the braces filled for that run.
        texts = ' '.join(row for _, row in rows)
        assert '{' not in texts and '}' not in texts
        for name in differing:
            assert fields[run][name] in texts and fields[rival][name] not in texts
    assert set(outputs) == {'scenarios/iv_fluid_shortage/results/brief.md', 'scenarios/README.md'}
    assert (
        f'[iv_fluid_shortage — {document["title"]}](iv_fluid_shortage/results/brief.md)'
        in outputs['scenarios/README.md']
    )


def test_brief_numbers_are_the_study_outcomes_at_three_significant_figures(published):
    ctx, outputs = published
    text = outputs['scenarios/iv_fluid_shortage/results/brief.md']
    pages, told = story(ctx, 'iv_fluid_shortage')
    (deaths,) = harm_metrics(pages, 'deaths')
    final = sample_result(ctx.studies['iv_fluid_shortage'])['runs'][told['runs'][0]]['reporting_points'][
        'final'
    ]
    label = outcome_definitions(ctx, 'iv_fluid_shortage')[deaths].label
    # The brief shows the study's own value, rounded by the amount rule the unit tests below pin.
    assert f'| {label} | {briefs.amount(final["values"][deaths], "people")} |' in text


def test_timelines_run_forward_and_use_reader_labels_only(published):
    _, outputs = published
    text = outputs['scenarios/iv_fluid_shortage/results/brief.md']
    for block in text.split('### Timeline: ')[1:]:
        rows = [
            row for row in block.split('\n## ')[0].splitlines() if row.startswith('| ') and '---' not in row
        ]
        times = [row.split(' | ')[0][2:] for row in rows[1:]]
        assert times[0] == 'Start'
    # No engine identifiers: event suffixes, expressions or snake_case names. The heading names the
    # scenario by the name of its folder, and only there.
    body = text.split('\n---\n')[0]
    assert '__' not in body and 'q(' not in body
    heading = '# iv_fluid_shortage — '
    assert body.startswith(heading)
    assert not re.findall(r'\b[a-z]+_[a-z_]+\b', body.removeprefix(heading))


def test_selected_brief_is_unchanged_and_does_not_replace_the_catalogue_index(published):
    original, full = published
    selected = Context(studies=original.studies, scenario_ids=['iv_fluid_shortage'])
    assert briefs.artifacts(selected) == {
        'scenarios/iv_fluid_shortage/results/brief.md': full['scenarios/iv_fluid_shortage/results/brief.md']
    }


def test_brief_states_the_inputs_and_evidence_behind_the_ai_layer(published):
    ctx, outputs = published
    text = outputs['scenarios/iv_fluid_shortage/results/brief.md']
    parameters = input_definitions(ctx, 'iv_fluid_shortage')
    # The brief shows the inputs that the file names for it, or else the inputs that the options set.
    pages, told = story(ctx, 'iv_fluid_shortage')
    names = told['key_inputs']
    assert names
    for name in names:
        assert f'| {parameters[name].label} |' in text
    # The AI layer's evidence: the assumptions behind the operation and behind its tempo.
    assumptions = {a['id']: a for a in ctx.models['iv_fluid_shortage'].library['assumptions']}
    operation = pages.operation()
    cited = [
        record.get('assumption')
        for basis in (operation['basis'], parameters[operation['tempo']].basis)
        for record in basis_records(basis)
    ]
    assert any(cited)
    for aid in filter(None, cited):
        assert assumptions[aid]['statement'] in text
    # An input whose value differs between the two runs gives the comparison's value after what the
    # comparison changes: the options that it takes besides the AI run's.
    values = [ctx.studies['iv_fluid_shortage'].runs[run]['resolved'].parameter_values for run in told['runs']]
    differing = [name for name in names if values[0][name] != values[1][name]]
    assert differing
    changed = changed_by(ctx.models['iv_fluid_shortage'], *told['runs'])
    for name in differing:
        row = next(line for line in text.splitlines() if line.startswith(f'| {parameters[name].label} |'))
        assert f'; {changed}: ' in row


def test_every_pathway_lists_the_runs_by_option_then_response_and_each_comparison_after_its_run(published):
    ctx, outputs = published
    pages, _ = story(ctx, 'iv_fluid_shortage')
    runs = pages.runs()
    run_of = {info['name']: run for run, info in runs.items()}
    table = table_after(outputs['scenarios/iv_fluid_shortage/results/brief.md'], '| Pathway |')
    order = [run_of[row[2:-2].split(' | ')[0]] for row in table]
    assert sorted(order) == sorted(runs)
    # The runs of one option come together, in the order of the options.
    seen = [runs[run]['option'] for run in order]
    blocks = [option for i, option in enumerate(seen) if i == 0 or seen[i - 1] != option]
    assert blocks == [option['name'] for option in pages.options()['options'] if option['name'] in seen]
    # A comparison follows the run that it compares with.
    compared = [run for run in order if runs[run]['comparison_of']]
    assert compared
    for run in compared:
        assert order.index(runs[run]['comparison_of']) < order.index(run)


def test_the_comparison_leads_with_the_recovery_measures_then_the_harms(published):
    """The AI's edge is measured on recovery and service; harms follow, each row read from the study."""
    ctx, outputs = published
    text = outputs['scenarios/iv_fluid_shortage/results/brief.md']
    pages, told = story(ctx, 'iv_fluid_shortage')
    outcomes = outcome_definitions(ctx, 'iv_fluid_shortage')
    heading = f'## The same operation: {changed_by(ctx.models["iv_fluid_shortage"], *told["runs"])}'
    comparison = text.split(heading)[1].split('### Timeline')[0]
    rows = [line for line in comparison.splitlines() if line.startswith('| ') and '---' not in line][1:]
    harms = harm_metrics(pages, *briefs.HARM_STYLES)
    assert [row.split(' | ')[0][2:] for row in rows] == [
        outcomes[name].label for name in [*told['measures'], *harms]
    ]
    finals = sample_result(ctx.studies['iv_fluid_shortage'])['runs']
    resolutions = [ctx.studies['iv_fluid_shortage'].runs[run]['resolved'] for run in told['runs']]
    metrics = {metric.name: metric for metric in briefs.compared_metrics(pages, resolutions)}
    for name, row in zip(told['measures'], rows):
        metric = metrics[name]
        cells = row.strip('| ').split(' | ')[1:]
        assert cells == [
            briefs.amount(
                finals[run]['reporting_points']['final']['values'][name], metric.unit, words=metric.words
            )
            for run in told['runs']
        ]
        # A measure that says what it counts is defined under the table; the lead measure does.
        description = outcomes[name].description
        assert description is None or f'- **{outcomes[name].label}:** {description}' in text
    assert outcomes[told['measures'][0]].description


def test_the_index_summarizes_each_cases_edge_on_its_lead_measure(published):
    ctx, outputs = published
    pages, told = story(ctx, 'iv_fluid_shortage')
    outcomes = outcome_definitions(ctx, 'iv_fluid_shortage')
    lead = told['measures'][0]
    (deaths,) = harm_metrics(pages, 'deaths')
    finals = sample_result(ctx.studies['iv_fluid_shortage'])['runs']
    ai, human = (finals[run]['reporting_points']['final']['values'] for run in told['runs'])
    unit = outcomes[lead].unit
    cells = [
        f'[iv_fluid_shortage](iv_fluid_shortage/results/brief.md) {authored("iv_fluid_shortage")["title"]}',
        outcomes[lead].label,
        briefs.amount(ai[lead], unit),
        briefs.amount(human[lead], unit),
        f'{briefs.amount(ai[deaths], "people")} / {briefs.amount(human[deaths], "people")}',
    ]
    index = outputs['scenarios/README.md']
    assert '| ' + ' | '.join(cells) + ' |' in index
    assert index.index("## The AI's edge in each case") < index.index('## The cases')


def test_brief_defines_each_harm_figure_and_separates_the_human_comparison(published):
    ctx, outputs = published
    text = outputs['scenarios/iv_fluid_shortage/results/brief.md']
    pages, told = story(ctx, 'iv_fluid_shortage')
    outcomes = outcome_definitions(ctx, 'iv_fluid_shortage')
    harms = harm_metrics(pages, *briefs.HARM_STYLES)
    assert len(harms) == len(briefs.HARM_STYLES)
    for name in harms:
        assert f'- **{outcomes[name].label}:** {outcomes[name].description}' in text
    pathways = text.split('## Every pathway')[1]
    # The defender responses read under the name of the group that `swap` names.
    attackers, rest = pathways.split(f'**{brief_of(ctx.models["iv_fluid_shortage"]).choice_group}**')
    defenders, humans = rest.split(
        f'**The same operation: {changed_by(ctx.models["iv_fluid_shortage"], *told["runs"])}**'
    )
    menu = pages.options()
    for option in menu['options']:
        assert f'**{option["name"]}:**' in attackers
    for response in menu['responses']:
        assert f'**{response["name"]}:**' in defenders
    human = pages.runs()[told['runs'][1]]['name']
    assert f'**{human}:**' in humans.split('| Pathway |')[0]
    assert f'**{human}:**' not in attackers + defenders
