"""Scenario briefs tell the AI story in plain language from the scenario and its completed study."""

import math
import re
from types import SimpleNamespace

import pytest

from napkin.engine import evaluate_study
from napkin.model.language import front
from napkin.model.language.evidence import Evidence, notes_of
from napkin.model.model import build_model
from tests.build import (
    block,
    drop,
    entity,
    evidence_library,
    fixture_claim,
    in_place,
    library,
    member,
    number_of,
    option,
    options,
    output,
    quote,
    scenario,
    toml,
    value,
)
from tests.helpers import ROOT, catalogue_default
from tests.publish.test_pages import Written, after, also, before, edited, reline
from tools import catalogue
from tools.publish import Context, briefs
from tools.publish import brief as styles
from tools.publish.pages import Pages, review_of


def catalogue_context(sid):
    """A publication context of one catalogue case and its completed default study."""
    return Context(studies={sid: catalogue_default(sid)})


def authored(sid):
    """A catalogue case's title, summary and notes as its file writes them, the notes as the pages read
    them: the source of the texts that its brief copies."""
    path = catalogue.scenario_path(ROOT, sid)
    file = front.read(path.read_text(encoding='utf-8'), str(path))
    review = review_of(notes_of(file.notes, Evidence(file)))
    block = file.scenario
    return {'title': block.title.value, 'summary': block.summary.value, 'review': review}


def story(ctx, sid):
    """The pages' data of a case, and the story of its two default runs."""
    pages = Pages(ctx.models[sid])
    return pages, pages.story()


def input_definitions(ctx, sid):
    """The input definitions of a case's main default run."""
    _, told = story(ctx, sid)
    return ctx.studies[sid].runs[told['runs'][0]]['resolved'].parameters


def outcome_definitions(ctx, sid):
    """The outcome definitions of a case's main default run."""
    _, told = story(ctx, sid)
    return ctx.studies[sid].runs[told['runs'][0]]['resolved'].outcomes


def changed_by(model, ai, human):
    """The options that the matched run takes besides the AI run's, in its order: what it changes, as
    the brief names it when the two runs differ in no group that the matched run leaves out."""
    return ' · '.join(name for name in model.runs[human]['options'] if name not in model.runs[ai]['options'])


def harm_metrics(pages, *styles):
    """The displayed outcomes of these styles, in the order of `show`."""
    return [m['outcome'] for m in pages.metrics() if m['style'] in styles]


def elapsed(label):
    """The hours that a brief's time label stands for, to the label's precision."""
    if label == 'Start':
        return 0.0
    if label.endswith(' days'):
        return float(label.split()[0]) * 24
    parts = re.fullmatch(r'(?:(\d+) h)? ?(?:(\d+) min)?', label)
    return int(parts[1] or 0) + int(parts[2] or 0) / 60


def timeline_rows(section):
    """(time label, text) of each row of the first timeline table in a part of a brief."""
    rows = table_after(section, '| Time since the attack | What happens |')
    return [tuple(row[2:-2].split(' | ', 1)) for row in rows]


@pytest.mark.parametrize(
    'hours,text',
    [
        (0, 'Start'),
        (0.25, '15 min'),
        (18.25, '18 h 15 min'),
        (48, '48 h'),
        (72, '3 days'),
        (216, '9 days'),
        (84, '3.5 days'),
        # Ties round half up, as figures do.
        (78, '3.3 days'),
        (0.075, '5 min'),
    ],
)
def test_elapsed_time_reads_naturally(hours, text):
    assert briefs.when(hours) == text


@pytest.mark.parametrize('hours', [78, 102, 0.075])
def test_a_time_on_a_label_tie_reads_the_same_on_every_computer(hours):
    # 78 h is 3.25 days and 0.075 h is 4.5 minutes. The solver's last digits differ between computers,
    # so such a time can come out one unit in the last place either side of the tie.
    lower, upper = math.nextafter(hours, 0), math.nextafter(hours, math.inf)
    assert briefs.when(lower) == briefs.when(hours) == briefs.when(upper)


@pytest.mark.parametrize('value,unit', [(4125, 'people'), (1.125, 'USD2025_bn'), (-69.45, 'people')])
def test_a_figure_on_a_rounding_tie_reads_the_same_on_every_computer(value, unit):
    lower, upper = math.nextafter(value, -math.inf), math.nextafter(value, math.inf)
    assert briefs.amount(lower, unit) == briefs.amount(value, unit) == briefs.amount(upper, unit)


@pytest.mark.parametrize(
    'value,unit,text',
    [
        (1.915, 'USD2025_bn', '$1.92bn'),
        (0.01036, 'USD2025_bn', '$10.4m'),
        (5.17e6, 'USD2025', '$5.17m'),
        (2.0, 'USD2025_bn', '$2.00bn'),
        (0, 'USD2025_bn', '$0'),
        (0.0, 'USD2025', '$0'),
        (None, 'USD2025_bn', 'not estimated'),
        (17095, 'people', '17,100'),
        (190_823_000, 'person-hours', '191 million'),
        (2_316_910, 'person-hours', '2.32 million'),
        (2.061e11, 'USD2025-hours', '$206bn-hours'),
        # Rounding comes before the scale: these round up into the next scale, never to 1.00e+03.
        (999.6e6, 'USD2025', '$1.00bn'),
        (0.9997, 'USD2025_bn', '$1.00bn'),
        (999.7e6, 'person-hours', '1,000 million'),
        (999.8e6, 'USD2025-hours', '$1.00bn-hours'),
        # Money below a million reads in plain dollars, not fractions of a million.
        (12, 'USD2025', '$12'),
        (523_456, 'USD2025', '$523,000'),
        (0.5, 'USD2025', '$0.5'),
        # The sign leads the dollar sign.
        (-0.5, 'USD2025_bn', '-$500m'),
        (-17_095, 'people', '-17,100'),
        # Money in millions, other price years and amounts past a thousand billion.
        (534, 'USD2025_m', '$534m'),
        (1.25, 'USD2024_bn', '$1.25bn'),
        (1234.5, 'USD2025_bn', '$1,230bn'),
    ],
)
def test_amounts_read_in_dollars_or_counts_at_three_significant_figures(value, unit, text):
    assert briefs.amount(value, unit) == text


def test_an_outcome_outside_its_pathway_or_unestimated_is_never_a_number():
    assert briefs.amount(5.0, 'people', 'not_applicable') == 'Outside this pathway'
    assert briefs.amount(None, 'USD2025_bn', 'not_applicable') == 'Outside this pathway'
    assert briefs.amount(None, 'people', 'unestimated') == 'not estimated'
    assert briefs.amount(0.0, 'people', 'estimated') == '0'


def run_of(final, reached=(), *, peak=None, rtol=1e-9, status='estimated'):
    """One pathway's report of an outcome x: the values it reaches at its reporting times, then its final
    value; the largest value seen between reporting times; and the solver's relative tolerance."""
    rows = [
        {'t': float(i), 'values': {'x': value}, 'statuses': {'x': status}}
        for i, value in enumerate([*reached, final])
    ]
    return {
        'samples': rows,
        'reporting_points': {'final': rows[-1]},
        'peaks': {} if peak is None else {'x': {'value': peak}},
        'numerical_settings': {'rtol': rtol},
    }


@pytest.mark.parametrize('residue', [4.3e-14, -4.3e-14, 7e-8])
def test_a_final_value_within_the_solvers_tolerance_of_zero_reads_zero(residue):
    """72 hours of work, all done: what is left is zero to the solver, which holds each value to its
    relative tolerance of the largest value the outcome reaches in the run (1e-9 x 72 h)."""
    assert briefs.figure(run_of(residue, [72.0, 24.0]), 'x', 'h') == '0'
    # The largest value can fall between reporting times.
    assert briefs.figure(run_of(residue, [0.0], peak=72.0), 'x', 'h') == '0'


@pytest.mark.parametrize(
    'run',
    [
        # Above the tolerance of the outcome's largest value in the run.
        run_of(1e-7, [72.0]),
        # A value is measured against its own run, never against another pathway's larger values.
        run_of(4.3e-14, [4.3e-14]),
        run_of(4.3e-14),
        # The tolerance is the run's own: a looser solver setting would make this value a residue.
        run_of(1e-5, [100.0]),
    ],
)
def test_a_real_value_keeps_every_figure(run):
    value = run['reporting_points']['final']['values']['x']
    assert briefs.figure(run, 'x', 'h') == briefs.amount(value, 'h') != '0'


def test_the_solvers_own_tolerance_decides_what_is_a_residue():
    assert briefs.figure(run_of(1e-5, [100.0], rtol=1e-6), 'x', 'h') == '0'
    assert briefs.figure(run_of(1e-5, [100.0], rtol=1e-9), 'x', 'h') != '0'


def test_an_outcome_without_a_value_is_never_a_residue_or_a_number():
    assert briefs.figure(run_of(None, [72.0], status='unestimated'), 'x', 'h') == 'not estimated'
    assert briefs.figure(run_of(0.0, [72.0]), 'missing', 'h') == 'Outside this pathway'


@pytest.mark.parametrize(
    'label,unit,value,text',
    [
        ('Fuel drivers and businesses could not get', 'L', 388_000_000, '388 million litres'),
        ('Qualification and reconciliation work completed', 'work_h', 336, '336 work-hours'),
        ('Time to restore service', 'h', 96, '96 h'),
        # A label that already names the unit is not repeated.
        ('Resident-hours without electricity', 'person-hours', 190_823_000, '191 million'),
        ('Days without fluid for other essential care', 'days', 12.5, '12.5'),
        ('Hours before pipeline fuel reaches inland terminals', 'h', 96, '96'),
        # People are counted bare and money carries its own sign.
        ('Deaths', 'people', 17_095, '17,100'),
        ('Economic loss', 'USD2025_bn', 1.915, '$1.92bn'),
        ('Provider payments outstanding, added up over time', 'USD2025-hours', 2.061e11, '$206bn-hours'),
    ],
)
def test_a_measure_names_its_unit_when_its_label_does_not(label, unit, value, text):
    assert briefs.amount(value, unit, words=briefs.unit_words(label, unit)) == text


# The profile of the comparison's option: the audited service, stopped early.
EARLY = 'Audited service, stopped early'


class Story:
    """A story's file and its brief settings, which a test can change."""

    def __init__(self, text, sheet):
        self.text = text
        self.sheet = sheet

    def edit(self, *steps):
        self.text = edited(self.text, *steps)

    def brief(self):
        return toml(self.sheet)


def story_scenario(*, harm=False):
    """A story of two featured runs: an audited service, and as its comparison the same service stopped
    early, a profile of the option group `Audit` that every run names. The defender responses, the
    group that `choice_group` names in brief.toml, have one profile.

    The story has no adversary, an input with no text and runs that give their own names: each is
    optional outside the catalogue, whose SCnn cases must have an adversary. ``harm`` adds an output
    that reports deaths.

    One person an hour (24 a day) leaves a stock of 10 until the service stops: the main run stops at
    12 h, after the stock empties at 10 h (10 served); the comparison stops at 6 h (6 served). Each
    served person waits for audit_h = 2 h, so 20 and 12 await audit; deaths are 1% of served.
    """
    outputs = [
        output(
            'audited',
            'service.served * audit.audit_h / 1 h',
            'people',
            doc='Deliveries awaiting audit',
            under=('about "People served whose delivery waits for its audit, counted per audit hour."',),
        ),
        output('pending', None, 'people', doc='Pending audits', under=('unestimated "No audit records."',)),
    ]
    if harm:
        outputs.append(
            output('deaths', 'service.served * 0.01', 'people', doc='Deaths', under=('category deaths',))
        )
    audit_h = value(
        'input',
        'audit_h',
        2,
        'h',
        records=None,
        bounds=(1, 10),
        under=(in_place('convention', 'Audit hours per delivery.'),),
    )
    text = edited(
        scenario(),
        # The first sentence of the summary is the hook; the reviewers give the brief's other two texts.
        reline('scenario:/summary:', 'summary "Hook. A synthetic story for tests only."'),
        after('service', '', entity('audit', audit_h, doc='The audit of each delivery.', role='operator')),
        after('output:/delivered', *outputs),
        drop('options:/Rate', 'runs:'),
        before(
            'record:/fixture',
            options(
                'Audit',
                option('Audited service', 'Each delivery waits for its audit.'),
                option(EARLY, 'The service stops early.', 'service.end = 6 h  @fixture'),
            ),
            '',
            block(
                'runs:',
                block('ai = "Default" + "Audited service"', '"AI pathway"'),
                block(f'human = "Default" + {quote(EARLY)} versus ai', '"Matched pathway"'),
            ),
            '',
        ),
        member('notes:', 'counterfactual: "Counterfactual."', 'decisive: "Choice."'),
    )
    sheet = {
        'show': ['audited', 'pending', *(['deaths'] if harm else [])],
        'drivers': ['audit.audit_h'],
        'featured': ['ai', 'human'],
        'choice_group': 'Response',
    }
    return Story(text, sheet)


def deaths_library():
    """The test library: an output's category, such as deaths, is a tag that no library lists."""
    return library()


def featured(model):
    """The runs that the pages show first: the brief's two runs."""
    return styles.featured(styles.brief_of(model), model)


def awaiting(model):
    """The deliveries awaiting audit at the end of each featured run, from the run's inputs: the
    people served, min(n, rate * end) with a rate a day over 24 hours, each counted for audit_h hours."""
    out = []
    for run in featured(model):
        values = model.run_values(run)
        served = min(values['service.n'], values['service.rate'] / 24 * values['service.end'])
        out.append(served * values['audit.audit_h'])
    return out


def option_texts(story, group='Audit', text='The {} option.'):
    """Name the option group of the story `group`, and give each of its profiles the menu line `text`."""
    options = {name: text.format(name) for name in Written(story.text).menu()['Audit']}
    story.edit(
        *(reline(f'options:/Audit/{name}/""', quote(line)) for name, line in options.items()),
        reline('options:/Audit', f'options {quote(group)}:'),
    )
    return options


def built(story, tmp_path, lib=None):
    """The model of a story, built from its file in a folder of its own, with its brief settings
    beside it."""
    folder = tmp_path / f'story{len(list(tmp_path.iterdir()))}'
    folder.mkdir()
    (folder / 'model.scn').write_text(story.text, encoding='utf-8')
    (folder / 'brief.toml').write_text(story.brief(), encoding='utf-8')
    return build_model(folder / 'model.scn', lib or library())


def story_outputs(story, tmp_path, lib=None):
    """The briefs of a story's default study."""
    lib = lib or library()
    model = built(story, tmp_path, lib)
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    # The story's brief settings define no spread, so its briefs give none. The catalogue names the
    # story by its folder.
    sid = 'story_fixture'
    ctx = SimpleNamespace(
        root=ROOT, models={sid: model}, studies={sid: study}, library=lib, scenario_ids=None
    )
    return briefs.artifacts(ctx)


def table_after(text, heading_row):
    """The rows of the markdown table whose header row starts with ``heading_row``."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading_row))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith('|'):
            break
        rows.append(line)
    return rows


def test_a_brief_reads_the_inputs_and_outputs_of_each_default_run(tmp_path):
    """Optional parts fall back as the pages do: an input with no text reads as its name, and an output
    that is not estimated says so in each run."""
    story = story_scenario()
    written = Written(story.text)
    model = built(story, tmp_path)
    outputs = story_outputs(story, tmp_path)
    text = outputs['scenarios/story_fixture/results/brief.md']
    audited, pending = (written.texts[f'output:/{name}/""'] for name in ('audited', 'pending'))
    ai, human = (briefs.amount(value, 'people') for value in awaiting(model))
    assert table_after(text, '| Outcome |') == [
        f'| {audited} | {ai} | {human} |',
        f'| {pending} | not estimated | not estimated |',
    ]
    assert f'- **{audited}:** {written.texts["output:/audited/about:"]}' in text
    field = 'audit/audit_h'
    value, low, high = map(
        number_of, (written.value(field), *(written.keyed(f'{field}/{e}:') for e in ('min', 'max')))
    )
    (record,) = next(m for m in written.thing('audit').members if m.name == 'audit_h').support
    assert table_after(text, '| Input |') == [
        f'| {model.inputs["audit.audit_h"]["doc"]} | {value} h; range {low}–{high} h | {record.text} |'
    ]
    names = [model.runs[run]['name'] for run in featured(model)]
    assert table_after(text, '| Pathway |') == [
        f'| {names[0]} | {ai} | not estimated |',
        f'| {names[1]} | {human} | not estimated |',
    ]
    # The stop event reads as its text, at each run's stop time.
    stop = written.texts['service/stop/""']
    main, comparison = (briefs.when(model.run_values(run)['service.end']) for run in featured(model))
    steps = text.split(f'## What happens: {names[0]}\n')[1].split('\n## ')[0]
    assert steps.count(f'| {main} | {stop} |') == 1
    assert f'| {comparison} | {stop} |' in text.split(f'### Timeline: {names[1]}\n')[1]
    # The comparison takes another option than its run, not the same one at human pace.
    assert f'## The same operation: {EARLY}' in text
    # Without an adversary there is no operation section and no evidence behind its moves.
    assert '## The AI operation' not in text and "Evidence behind the AI's moves" not in text
    title = written.parts.scenario.title.value
    assert (
        f'| [story_fixture](story_fixture/results/brief.md) {title} | {audited} | {ai} | {human} | not estimated |'
        in outputs['scenarios/README.md']
    )


def test_a_matched_run_with_another_response_is_named_by_that_response(tmp_path):
    """The brief names what the matched run changes, read from the profiles of the two runs: one that
    takes another defender response shows that response in its heading and in the key inputs, and is
    never said to be at human pace (local-P3-review M1)."""
    story = story_scenario()
    story.edit(
        member(
            'options:/Response',
            option('Slow audit', 'Each audit takes longer.', 'audit.audit_h = 4 h  @fixture'),
        ),
        reline('runs:/human', 'human = "Slow audit" + "Audited service" versus ai'),
    )
    model = built(story, tmp_path)
    text = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md']
    assert changed_by(model, 'ai', 'human') == 'Slow audit'
    assert '## The same operation: Slow audit' in text
    (row,) = table_after(text, '| Input |')
    assert '; Slow audit: ' in row and 'human pace' not in text
    # A matched run that leaves out a profile of the AI run says what it is without.
    story.edit(reline('runs:/human', 'human = "Default" versus ai'))
    text = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md']
    assert '## The same operation: without Audited service' in text


def test_authored_text_cannot_split_a_brief_table_row(tmp_path):
    # A text with an empty line holds a line break.
    story = story_scenario(harm=True)
    story.edit(
        reline('runs:/ai/""', '"AI | first pathway"'),
        reline('output:/audited/""', '"Deliveries\n\n    awaiting | audit"'),
        reline('service/stop/""', '"Stop | and\n\n    hold"'),
        reline('audit/audit_h/@/0', '@convention "Audit | hours\n\n    per delivery."'),
    )
    lib = deaths_library()
    model = built(story, tmp_path, lib)
    ai, human = (briefs.amount(value, 'people') for value in awaiting(model))
    stop = briefs.when(model.run_values('ai')['service.end'])
    text = story_outputs(story, tmp_path, lib)['scenarios/story_fixture/results/brief.md']
    assert f'| Deliveries awaiting \\| audit | {ai} | {human} |' in text
    assert f'| {stop} | Stop \\| and hold |' in text
    tables, current = [], []
    for line in [*text.splitlines(), '']:
        if line.startswith('|'):
            current.append(line)
        elif current:
            tables.append(current)
            current = []
    assert len(tables) == 5
    for rows in tables:
        # Every row of a table has its header's number of cell boundaries.
        assert len({len(re.findall(r'(?<!\\)\|', row)) for row in rows}) == 1, rows


def test_brief_evidence_marks_limits_and_contradictions_apart_from_support():
    lib = evidence_library()
    lib['claims'] += [fixture_claim('C-LIMIT'), fixture_claim('C-AGAINST')]
    lib['assumptions'][0]['supports'] = [
        {'claim': 'C-ACTION', 'relation': 'mechanism_precedent', 'note': 'Precedent.'},
        {'claim': 'C-LIMIT', 'relation': 'context_limitations', 'note': 'Elsewhere.'},
        {'claim': 'C-AGAINST', 'relation': 'contradicts', 'note': 'Restored at once.'},
    ]
    assert briefs.evidence(lib, ['RT-FIXTURE']) == [
        '**RT-FIXTURE.** The cyber effect stops service.',
        '',
        '- Fixture source: Precedent.',
        '- Limit: Fixture source: Elsewhere.',
        '- Contradicts: Fixture source: Restored at once.',
        '',
    ]


def test_the_responses_read_under_the_name_of_the_swap_group_and_a_brief_needs_none(tmp_path):
    """The profiles of the group of the responses (`choice_group` in brief.toml) read under that
    group's name, whatever it is. Without one, the brief lists no responses and still gives a row for
    each pathway."""
    story = story_scenario()
    swap = story.sheet['choice_group']
    story.edit(reline(f'options:/{swap}', 'options "Defence":'))
    story.sheet['choice_group'] = 'Defence'
    pathways = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md'].split(
        '## Every pathway\n'
    )[1]
    listed = pathways.split('**Defence**\n')[1].split('\n\n**')[0]
    assert [line for line in listed.splitlines() if line] == [
        f'- **{name}:** {line}' for name, line in Written(story.text).menu()['Defence'].items()
    ]
    del story.sheet['choice_group']
    text = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md']
    assert '**Defence**' not in text
    assert len(table_after(text, '| Pathway |')) == len(Written(story.text).runs())


@pytest.mark.parametrize('group', ['Audit', 'Recovery conditions'])
def test_the_options_read_under_the_name_of_the_group_that_holds_them(tmp_path, group):
    """An option is a profile that a run takes besides its defender response. The brief heads the
    options with the name of the group that holds them, never as attacker options."""
    story = story_scenario()
    options = option_texts(story, group)
    text = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md']
    pathways = text.split('## Every pathway\n')[1].split(f'**{story.sheet["choice_group"]}**')[0]
    headings = re.findall(r'^\*\*(.+)\*\*$', pathways, re.MULTILINE)
    assert headings == [group]
    listed = pathways.split(f'**{group}**')[1]
    for name, line in options.items():
        assert f'- **{name}:** {line}' in listed
    assert 'attacker' not in pathways.lower()


@pytest.mark.parametrize('extra', [None, 'The matched team then waits a day.'])
def test_a_comparison_does_not_repeat_the_text_of_its_option(tmp_path, extra):
    """The options already give each option's text. A comparison's text is the menu lines of the
    profiles that it adds to its run: it keeps only what the options do not give, and one that adds
    nothing else is named by its name alone."""
    story = story_scenario()
    story.edit(reline('options:/Response/Default/""', '"The defenders respond."'))
    own = option_texts(story, text='The {} option holds.')[EARLY]
    if extra:
        # A profile that only the comparison takes, so its group is no option group: the brief reads
        # only its menu line.
        story.edit(
            before('runs:', options('Delay', option('Waits a day', extra)), ''),
            also('human', 'Waits a day'),
        )
    name = Written(story.text).texts['runs:/human/""']
    pathways = story_outputs(story, tmp_path)['scenarios/story_fixture/results/brief.md'].split(
        '## Every pathway\n'
    )[1]
    assert pathways.count(own) == 1
    item = next(line for line in pathways.splitlines() if line.startswith(f'- **{name}'))
    assert item == (f'- **{name}:** {extra}' if extra else f'- **{name}**')
