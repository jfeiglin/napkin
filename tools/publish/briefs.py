"""Scenario briefs: the AI story of each case in plain language, with its computed results.

A brief is written only from the scenario's document, the library records behind its AI layer and
its completed default study: the two default runs (the AI's run and its matched comparison), their
event timelines and final outcomes. The pages' data of the model (`publish/pages.py`) gives
every text, so a reader who never sees the engine can follow the case and an independent reviewer
can check it. Only the summary and the reviewers' texts are written by hand.

A brief also gives the spread of the outcomes where its brief settings define one (`[[spread]]` in
`brief.toml`): the brief calculates it afresh, for this model and this implementation, with the
engine's Monte Carlo study of the spread's runs under its edit document (`napkin/spread.py`). A spread
that the engine rejects stops the brief: a brief never shows part of a spread.
"""

from __future__ import annotations

import posixpath
import re
from collections import namedtuple
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from napkin import spread as sampling
from napkin.draw.model_map import filled
from napkin.engine import sample_result
from napkin.engine.uncertainty import chancy
from napkin.model import load_json
from napkin.model.ir import basis_records

from .. import catalogue
from . import cell, limits, stable
from .brief import brief_of, output_name, spread_document
from .formatting import OUTSIDE, decimal_text, dollars, rounded
from .pages import Pages
from .texts import (
    UNIT_WORDS,
    _text_options,
    cards_for,
    event_label,
    input_text,
    range_text,
)

HARM_STYLES = ('deaths', 'casualties', 'loss')
# The catalogue index, which links each brief.
INDEX = catalogue.INDEX
# The library's links from an assumption to a claim that bounds, qualifies or argues against the
# assumption, rather than supporting it, and the mark a reader sees beside each. No brief counts it
# as support.
EVIDENCE_MARKS = {'bounds': 'Limit', 'context_limitations': 'Limit', 'contradicts': 'Contradicts'}
FIGURES = 3
# Powers of ten a figure is written in once its rounded value reaches them.
MONEY_SCALES = ((9, 'bn'), (6, 'm'))
COUNT_SCALES = ((6, ' million'),)
# Counts that read without unit words.
BARE_UNITS = ('people', 'cases', 'fraction')
# A compared outcome: its reader label and unit, the words naming that unit after a figure, and its
# definition's description.
Metric = namedtuple('Metric', 'name label unit words description')


def when(hours):
    """Elapsed time for a lay reader: minutes, hours, then days, with ties rounded half up."""
    hours = stable(hours)
    if hours <= 0:
        return 'Start'
    minutes = int((hours * 60).quantize(Decimal(1), ROUND_HALF_UP))
    if minutes < 60:
        return f'{minutes} min'
    if hours < 72:
        whole, rest = divmod(minutes, 60)
        return f'{whole} h {rest} min' if rest else f'{whole} h'
    days = (hours / 24).quantize(Decimal('0.1'), ROUND_HALF_UP)
    return f'{float(days):g} days'


def significant(number, scales=()):
    """A Decimal's size at three significant figures, in the largest of ``scales`` its rounded value reaches.

    Rounding comes first, so $999.6m reads $1.00bn. A scaled figure keeps its trailing zeros (2.00bn);
    a plain one reads as a grouped number (12; 17,100). No figure is ever written with an exponent.
    """
    number = abs(rounded(number, FIGURES))
    for exponent, suffix in scales:
        if number >= Decimal(1).scaleb(exponent):
            return format(number.scaleb(-exponent), ',f') + suffix
    return decimal_text(number)


def amount(value, unit, status='estimated', words=''):
    """A final outcome for a reader: money in dollars, any other quantity as a plain figure.

    Figures have three significant figures; money below a million reads in plain dollars ($12) and a
    negative amount reads -$500m. ``words`` name a non-money unit after the figure. An outcome
    outside the run or not estimated says so: it is never zero.
    """
    if status == 'not_applicable':
        return OUTSIDE
    if value is None:
        return 'not estimated'
    money, _, per = unit.partition('-')
    if per and dollars(money):
        # Money accumulated over time, such as payments outstanding summed hour by hour.
        return f'{amount(value, money)}-{per}'
    number = stable(value)
    sign = '-' if number < 0 else ''
    if scale := dollars(unit):
        return f'{sign}${significant(number * Decimal(scale), MONEY_SCALES)}'
    text = sign + significant(number, COUNT_SCALES)
    return f'{text} {words}' if words else text


def unit_words(label, unit):
    """The words naming a measure's unit after its figure, unless its label already names the unit.

    Money carries its own sign and people are counted bare. Any other unit reads in the unit words of
    the texts (`UNIT_WORDS`), so "Fuel drivers could not get" reads 388 million litres; a label that
    uses the unit's counted noun ("Resident-hours without electricity") already names it.
    """
    if dollars(unit.partition('-')[0]) or unit in BARE_UNITS:
        return ''
    words = UNIT_WORDS.get(unit, unit.replace('_', ' '))
    noun = 'hour' if unit == 'h' else re.split(r'[\s-]', words)[-1].removesuffix('s')
    return '' if noun.lower() in label.lower() else words


def settled(run, name):
    """An outcome's final value in one run's report, with a residue of the solver read as zero.

    The solver holds each value only to its relative tolerance of the largest value that the outcome
    reaches in the run. A final value within that tolerance of zero, such as 4e-14 hours of work left
    once crews finish the work, is zero to the solver's accuracy. Any larger value keeps every digit.
    """
    value = run['reporting_points']['final']['values'].get(name)
    if not value:
        return value
    reached = [row['values'].get(name) for row in run['samples']]
    reached.append(run.get('peaks', {}).get(name, {}).get('value'))
    scale = max(abs(x) for x in [value, *reached] if x is not None)
    return 0.0 if abs(value) <= run['numerical_settings']['rtol'] * scale else value


def figure(run, name, unit, words=''):
    """One run's final value of an outcome, or why it has none, from the run's report. An outcome that
    the run's report does not have is outside the run."""
    final = run['reporting_points']['final']
    return amount(settled(run, name), unit, final['statuses'].get(name, 'not_applicable'), words)


def compared_metrics(pages, resolutions):
    """The story's recovery and service measures, then the displayed death, casualty and loss metrics.
    A measure reports no harm, so no outcome is both. Each takes its definition from the first of the
    story's resolved runs."""
    harms = [metric['outcome'] for metric in pages.metrics() if metric['style'] in HARM_STYLES]
    metrics = []
    outcomes = resolutions[0].outcomes
    for name in [*pages.story()['measures'], *harms]:
        definition = outcomes[name]
        label = definition.label
        metrics.append(
            Metric(
                name,
                label,
                definition.unit,
                unit_words(label, definition.unit),
                definition.description,
            )
        )
    return metrics


def timeline(pages, run, trace):
    """The semantic events of one run with their cards' texts, in time order. A card without its own
    text reads as its event, and the fields a text names in braces read as they are in the run."""
    cards = pages.cards()
    texts = pages.texts()[run]
    rows = []
    seen = {}
    for entry in trace:
        seen[entry['event']] = seen.get(entry['event'], 0) + 1
        if not entry['semantic']:
            continue
        presented = cards_for(cards.get(entry['event'], []), seen[entry['event']])
        if presented:
            text = ' '.join(item.get('text', event_label(entry)) for item in presented)
            rows.append((entry['t'], filled(text, texts)))
    return rows


def harm_names(pages):
    """The displayed outcomes that count deaths, casualties or loss."""
    return {metric['outcome'] for metric in pages.metrics() if metric['style'] in HARM_STYLES}


def harmed(pages, metrics):
    """Who is harmed, from the outputs: what each harm measure counts, and whom the study follows."""
    harms = harm_names(pages)
    lines = [f'- **{m.label}:** {m.description}' for m in metrics if m.description and m.name in harms]
    exposure = pages.review().get('exposure', {})
    if exposure.get('scope'):
        lines.append(f'- **The study follows:** {exposure["scope"]}')
    return '\n'.join(lines)


def differences(model, ai, human):
    """What the matched run changes against the AI run, read from the options of the two runs and
    nothing else: in each group of the menu where they take different options, the matched run's
    option, or "without" the AI run's option where the matched run takes none of that group. A matched
    run that takes another defender response shows that response."""
    changed = []
    for group_options in model.menu.values():
        mine = [option for option in model.runs[human]['options'] if option in group_options]
        theirs = [option for option in model.runs[ai]['options'] if option in group_options]
        if mine != theirs:
            changed.append(mine[0] if mine else f'without {theirs[0]}')
    return ' · '.join(changed)


def comparison_heading(model, ai, human):
    """The matched run's heading: what it changes against the AI run."""
    changed = differences(model, ai, human)
    return f'The same operation: {changed}' if changed else 'The same operation'


def options(pages):
    """The options that runs pair with a defender response, the defender responses and the matched
    comparisons, with their plain meaning. An option is whatever a run takes besides its response:
    an attack, a condition of the recovery or the AI's conduct."""
    menu = pages.options()
    runs = pages.runs()
    choices = [(option['name'], option['doc'] or '') for option in menu['options']]
    defenders = [(response['name'], response['doc']) for response in menu['responses']]
    docs = {option['name']: option['doc'] for option in menu['options']}
    humans = []
    for run in runs.values():
        if run['comparison_of'] is None:
            continue
        text = run['narrative'] or ''
        # A comparison's text can include the text of its own option, which the options above
        # already give: it is said once, and the comparison keeps only what it adds. A comparison
        # that adds nothing is named by its name alone.
        own = docs.get(run['option'])
        if own and own in text:
            text = ' '.join(text.replace(own, ' ').split()) or None
        humans.append((run['name'], text))
    return choices, defenders, humans


def key_inputs(pages, study, ai, human):
    """The story's key inputs: the AI run's value, the comparison's value where it differs, and the
    range. Values read as the input editor shows them; an on/off input has no range to show. The
    comparison's value is labelled with what the comparison changes (`differences`)."""
    resolutions = {run: study.runs[run]['resolved'] for run in (ai, human)}
    contrast = differences(pages.model, ai, human)
    rows = []
    for name in pages.story()['key_inputs']:
        values, texts = {}, {}
        for run, rs in resolutions.items():
            definition = rs.parameters[name]
            values[run] = rs.parameter_values[name]
            texts[run] = input_text(values[run], definition.unit, **_text_options(definition))
        definition = resolutions[ai].parameters[name]
        shown = texts[ai]
        if texts[human] != texts[ai] or values[human] != values[ai]:
            shown += f'; {contrast}: {texts[human]}'
        adjust, display = definition.adjust, _text_options(definition)
        if adjust.mode == 'range' and not display['switch']:
            limits = range_text(
                adjust.minimum, adjust.maximum, definition.unit, multiplier=display['multiplier']
            )
            shown += f'; range {limits}'
        explanation = ' '.join(record['explanation'] for record in basis_records(definition.basis))
        rows.append((definition.label, shown, explanation))
    return rows


def ai_assumptions(model, operation):
    """Assumptions behind the AI layer: the operation, its tempo and each event of the attacker's
    entity, first use first. A part that only some runs have is found in their
    structures."""
    if not operation:
        return []
    parameters, rules = {}, {}
    for structure in model.structures.values():
        parameters.update(structure.parameters)
        rules.update(structure.rules)
    attacker = operation['entity']
    bases = [operation['basis']]
    if operation.get('tempo'):
        bases.append(parameters[operation['tempo']].basis)
    bases += [rule.basis for rule in rules.values() if rule.entity == attacker and rule.basis]
    seen = {}
    for basis in bases:
        for record in basis if isinstance(basis, (list, tuple)) else [basis]:
            if record.get('assumption'):
                seen.setdefault(record['assumption'], None)
    return list(seen)


def evidence(library, assumption_ids):
    """Each assumption's statement with the published sources it rests on, each limit marked."""
    assumptions = {item['id']: item for item in library['assumptions']}
    claims = {item['id']: item for item in library['claims']}
    sources = {item['id']: item for item in library['sources']}
    lines = []
    for aid in assumption_ids:
        record = assumptions[aid]
        lines += [f'**{record.get("title", aid)}.** {record["statement"]}', '']
        for link in record.get('supports', []):
            claim = claims[link['claim']]
            source = sources[claim['source']]
            year = source.get('issued', {}).get('date-parts', [[None]])[0][0]
            who = source.get('publisher') or source.get('container-title') or ''
            credit = ', '.join(str(part) for part in (who, year) if part)
            mark = EVIDENCE_MARKS.get(link['relation'])
            lines.append(
                f'- {f"{mark}: " if mark else ""}{source.get("title", claim["source"])}'
                + (f' ({credit})' if credit else '')
                + f': {link.get("note", "")}'
            )
        lines.append('')
    return lines


def run_order(pages):
    """The runs by option, then response (the menu's option of the group of the responses); a comparison
    follows the run it compares with."""
    menu = pages.options()
    runs = pages.runs()
    choices = [option['name'] for option in menu['options']]
    responses = [response['name'] for response in menu['responses']]

    def key(run):
        info = runs[run]
        response = responses.index(info['response']) if info['response'] is not None else 0
        return choices.index(info['option']), response, bool(info['comparison_of'])

    return sorted(runs, key=key)


def option_lines(heading, items):
    """Labelled items under a heading. An item without a text is left out; one whose text is None
    because the page already gives it shows its label alone."""
    lines = [
        f'- **{label}:** {text}' if text else f'- **{label}**'
        for label, text in items
        if text or text is None
    ]
    return [f'**{heading}**', '', *lines, ''] if lines else []


def calculated_spread(model, entry, jobs=1):
    """The engine's report of one spread of the brief settings (`brief.Spread`, `uncertainty_report`):
    its runs, sampled with its settings under its edit document (`spreads/<id>.json`), in `jobs`
    processes (`napkin/spread.py`). The engine checks the document as it checks every edit document,
    its model revision included. A spread that the engine rejects, or whose report is not numerically
    valid, raises ValueError with its diagnostics."""
    path = spread_document(model, entry)
    if path is None or not path.is_file():
        raise ValueError(f'{model.origin}: the spread {entry.id} has no edit document {path}')
    settings = entry.settings
    found = sampling.spread(
        model,
        list(entry.runs),
        load_json(path),
        samples=settings.samples,
        seed=settings.seed,
        method=settings.method,
        jobs=jobs,
    )
    if found['status'] != 'completed':
        raise ValueError(f'{path}: the spread {entry.id} is {found["status"]}: {found["diagnostics"]}')
    return found['report']


def spread_of(model, entry, report):
    """What the brief shows of one spread (`brief.Spread`), from the engine's report of it: its
    description and settings, the outputs that it names for the brief (`outcomes`, by the names of the
    model's outcomes; none for the brief's measures) and, for each run that it samples, the inputs
    that it draws, whether its events go by chance in each sample (`chance`) and each outcome at the
    end of the run."""
    section = report['uncertainty']
    return {
        'description': entry.description,
        'settings': section['settings'],
        'outcomes': [model.outputs[output_name(name, model)] for name in entry.outputs],
        'runs': {
            run: {
                'inputs': {name: item['distribution']['text'] for name, item in data['inputs'].items()},
                'chance': chancy(model.structure_of(run)),
                'outcomes': {
                    outcome: {'final': summary['points']['final']}
                    for outcome, summary in data['outcomes'].items()
                },
            }
            for run, data in section['runs'].items()
        },
    }


def scenario_spread(ctx, sid, model):
    """The spreads that a scenario's brief gives, `{'studies': {id: spread_of}}`: each spread of its
    brief settings, calculated afresh for this model and this implementation in the publication's
    processes (`ctx.jobs`); None when the brief settings define none."""
    entries = brief_of(model).spreads
    if not entries:
        return None
    jobs, progress = getattr(ctx, 'jobs', 1), getattr(ctx, 'progress', None) or (lambda message: None)
    studies = {}
    for entry in entries:
        progress(f'briefs: {sid}: the spread {entry.id}, {entry.samples} samples of {len(entry.runs)} runs')
        studies[entry.id] = spread_of(model, entry, calculated_spread(model, entry, jobs))
    return {'studies': studies}


def mean_band(point, metric):
    """The mean of the calculations of an outcome at the end of a run, with the unit's words once, then
    the middle 90% of them in brackets; never a zero for an outcome that is not estimated. The mean of
    an outcome that is 1 or 0 is the share of the calculations in which it is 1, which no band shows."""
    if point is None or not point['estimated']:
        return 'not estimated'
    mean, low, high = (amount(point[p], metric.unit) for p in ('mean', 'p5', 'p95'))
    words = f' {metric.words}' if metric.words else ''
    return f'{mean}{words} ({low if low == high else f"{low} to {high}"})'


def study_metrics(model, names):
    """The outcomes that a spread names for the brief, each with its label, unit and unit words as a
    measure of the brief has them. Every structure of a model has the same outputs."""
    outcomes = next(iter(model.structures.values())).outcomes
    return [
        Metric(
            name,
            outcomes[name].label,
            outcomes[name].unit,
            unit_words(outcomes[name].label, outcomes[name].unit),
            outcomes[name].description,
        )
        for name in names
    ]


def drawn_text(model, study, runs):
    """What each calculation of a study draws: each input that has a distribution, and the outcome of
    each event that goes by chance when its runs have one."""
    drawn = dict.fromkeys(name for run in runs for name in study['runs'][run]['inputs'])
    chance = any(study['runs'][run]['chance'] for run in runs)
    count = study['settings']['samples']
    calculations = '1 calculation draws' if count == 1 else f'{count} calculations draw'
    if not drawn:
        return f'{calculations} the outcome of each event that goes by chance. No input has a distribution.'
    labels = '; '.join(model.inputs[name]['doc'] for name in drawn)
    also = ' Each calculation also draws the outcome of each event that goes by chance.' if chance else ''
    return f'{calculations} each input that has a distribution: {labels}.{also}'


# The heading of a brief's section on the spread of the outcomes (`spread_lines`).
SPREAD_HEADING = '## The spread of the outcomes'
# What a check without `--spreads` shows for a brief whose committed file has no spread section,
# so that the check reports that brief as stale.
MISSING_SPREAD = (
    'The committed brief has no spread section: check it with `tools.check --spreads`, or refresh it '
    'with `tools.publish --write`.'
)


def committed_spread_section(path):
    """The section of the committed brief at `path` on the spread of the outcomes, line for line: from
    its heading to the next section's heading (`## `). A check without `--spreads` uses it in place of
    a sampled spread (D-39). A missing file or section gives a placeholder section, which no
    committed brief holds, so the check reports the brief as stale."""
    path = Path(path)
    lines = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    if SPREAD_HEADING not in lines:
        return [SPREAD_HEADING, '', MISSING_SPREAD, '']
    start = lines.index(SPREAD_HEADING)
    end = next((at for at in range(start + 1, len(lines)) if lines[at].startswith('## ')), len(lines))
    return lines[start:end]


def spread_lines(model, spread, metrics):
    """The section of the brief on the spread of the outcomes (`scenario_spread`). For each spread: what
    it is, what its calculations draw, and the mean and the middle 90% of them at the end of each run
    that it samples, for the outcomes that the spread names, or else for the brief's measures
    (`metrics`)."""
    lines = []
    for ident, study in spread['studies'].items():
        runs = list(study['runs'])
        if not runs:
            continue
        shown = study_metrics(model, study['outcomes']) if study['outcomes'] else metrics
        lines += [
            *([SPREAD_HEADING, ''] if not lines else []),
            *([f'### {ident}', ''] if len(spread['studies']) > 1 else []),
            *([study['description'], ''] if study['description'] else []),
            f'{drawn_text(model, study, runs)} Each figure gives the mean of the calculations at the end of '
            'the pathway, then the middle 90% of them in brackets. The mean of an outcome that is 1 or 0 is '
            'the share of the calculations in which it is 1. The distributions are the ones that the study '
            'assumes: a figure is not a measured interval.',
            '',
            '| Pathway | ' + ' | '.join(cell(m.label) for m in shown) + ' |',
            '| --- |' + ' --- |' * len(shown),
            *[
                f'| {cell(model.runs[run]["name"])} | '
                + ' | '.join(
                    mean_band((study['runs'][run]['outcomes'].get(m.name) or {}).get('final'), m)
                    for m in shown
                )
                + ' |'
                for run in runs
            ],
            '',
        ]
    return lines


def brief(sid, model, study, report, library, spread=None, spread_section=None):
    pages = Pages(model)
    story = pages.story()
    runs = pages.runs()
    ai, human = story['runs']
    metrics = compared_metrics(pages, [study.runs[run]['resolved'] for run in (ai, human)])
    reports = report['runs']
    operation = pages.operation()
    assumptions = ai_assumptions(model, operation)
    choices, defenders, humans = options(pages)
    comparison = comparison_heading(model, ai, human)
    # The name of the groups that hold the options heads them. Without one they are options: they
    # can be conditions of the recovery or the AI's conduct, so the brief never calls them attacker
    # options.
    axis = pages.options()['axis']
    choice_lines = option_lines(axis['name'] if axis else 'Options', choices)
    summary = model.scenario.summary or ''
    # The main run's timeline is its steps, and the outputs say who is harmed.
    harms = harm_names(pages)
    counts = [f'- **{m.label}:** {m.description}' for m in metrics if m.description and m.name not in harms]

    def cells(run):
        return [figure(reports[run], m.name, m.unit, m.words) for m in metrics]

    def steps(run):
        return timeline(pages, run, study.runs[run]['trajectory'].trace)

    lines = [
        f'# {sid} — {model.scenario.title}',
        '',
        *([summary, ''] if summary else []),
        f'## What happens: {runs[ai]["name"]}',
        '',
        '| Time since the attack | What happens |',
        '| --- | --- |',
        *[f'| {when(t)} | {cell(text)} |' for t, text in steps(ai)],
        '',
        f'## {comparison}',
        '',
        *([story['counterfactual'], ''] if story.get('counterfactual') else []),
        f'| Outcome | {cell(runs[ai]["name"])} | {cell(runs[human]["name"])} |',
        '| --- | --- | --- |',
        *[
            f'| {cell(m.label)} | {shown_ai} | {shown_human} |'
            for m, shown_ai, shown_human in zip(metrics, cells(ai), cells(human))
        ],
        '',
        *([*counts, ''] if counts else []),
        f'### Timeline: {runs[human]["name"]}',
        '',
        '| Time since the attack | What happens |',
        '| --- | --- |',
        *[f'| {when(t)} | {cell(text)} |' for t, text in steps(human)],
        '',
    ]
    if spread_section is not None:
        lines += spread_section
    elif spread:
        lines += spread_lines(model, spread, metrics)
    if story.get('decisive_choice'):
        lines += ['## The decisive defender choice', '', story['decisive_choice'], '']
    lines += ['## Who is harmed', '', harmed(pages, metrics), '']
    # The reviewers' limits go after who is harmed. The part is made last, from the whole brief, so that
    # it leaves out a limit that the brief already states.
    caveats = len(lines)
    lines += [
        '## Key inputs',
        '',
        '| Input | Value | Where the value comes from |',
        '| --- | --- | --- |',
        *[
            f'| {cell(label)} | {cell(value)} | {cell(basis)} |'
            for label, value, basis in key_inputs(pages, study, ai, human)
        ],
        '',
    ]
    if assumptions:
        lines += [
            "## Evidence behind the AI's moves",
            '',
            'Each assumption is followed by the published sources behind it. A source marked "Limit" bounds '
            'or qualifies the assumption and one marked "Contradicts" argues against it; neither supports it.',
            '',
            *evidence(library, assumptions),
        ]
    # The group of the responses (`choice_group` in brief.toml), when there is one, heads its own options
    # by its name.
    option = 'one of the options below' if choice_lines else 'one option'
    lines += [
        '## Every pathway',
        '',
        f'Each pathway pairs {option} with one choice of {pages.brief.choice_group}.'
        if pages.brief.choice_group
        else f'Each pathway takes {option}.',
        '',
        *choice_lines,
        *option_lines(pages.brief.choice_group, defenders),
        *option_lines(comparison, humans),
        '| Pathway | ' + ' | '.join(cell(m.label) for m in metrics) + ' |',
        '| --- |' + ' --- |' * len(metrics),
        *[f'| {cell(runs[run]["name"])} | ' + ' | '.join(cells(run)) + ' |' for run in run_order(pages)],
        '',
    ]
    if operation:
        lines += ['## The AI operation', '', operation['doc'], '']
    lines += [
        '---',
        '',
        'This brief is generated from the scenario definition and its computed results. Figures are model '
        'outputs under the stated assumptions, rounded to three significant figures; they are not forecasts.',
        '',
    ]
    lines[caveats:caveats] = limits(pages.review()['limitations'], '\n'.join(lines))
    return '\n'.join(lines)


def edge_row(sid, model, study, report):
    """One index row: the case's lead recovery measure and its deaths on the AI and matched runs."""
    pages = Pages(model)
    runs = report['runs']
    ai, human = pages.story()['runs']
    resolutions = [study.runs[run]['resolved'] for run in (ai, human)]
    metrics = compared_metrics(pages, resolutions)
    lead = metrics[0] if metrics else None
    death = next((m['outcome'] for m in pages.metrics() if m['style'] == 'deaths'), None)
    unit = resolutions[0].outcomes[death].unit if death else None
    cells = [
        f'[{sid}]({index_link(sid)}) {cell(model.scenario.title)}',
        cell(lead.label) if lead else '—',
        *(figure(runs[run], lead.name, lead.unit, lead.words) if lead else '—' for run in (ai, human)),
        ' / '.join(figure(runs[run], death, unit) for run in (ai, human)) if unit else 'not estimated',
    ]
    return '| ' + ' | '.join(cells) + ' |'


def index_link(sid):
    """The link from the catalogue index to the brief of a scenario, in the results folder of its owner."""
    return posixpath.relpath(catalogue.result(sid, 'brief.md'), posixpath.dirname(INDEX))


def artifacts(ctx):
    outputs, index, rows = {}, [], []
    for sid, model in ctx.models.items():
        story = Pages(model).story()
        if story is None:
            continue
        study = ctx.studies[sid]
        report = sample_result(study)
        path = catalogue.result(sid, 'brief.md')
        if getattr(ctx, 'committed_spreads', False) and brief_of(model).spreads:
            # A check without `--spreads` (D-39): the spread section as committed, sampling none.
            section = committed_spread_section(Path(ctx.root) / path)
            outputs[path] = brief(sid, model, study, report, model.library, spread_section=section)
        else:
            spread = scenario_spread(ctx, sid, model)
            outputs[path] = brief(sid, model, study, report, model.library, spread)
        if ctx.scenario_ids is None:
            index.append(f'- [{sid} — {model.scenario.title}]({index_link(sid)}): {story["hook"]}')
            rows.append(edge_row(sid, model, study, report))
    if index:
        outputs[INDEX] = '\n'.join(
            [
                '# Scenario briefs',
                '',
                'Each brief tells one case as a story: what the AI does, why that is an AI threat, '
                'what changes at human pace, and what the model computes. Start here.',
                '',
                "## The AI's edge in each case",
                '',
                'Each case compares its AI pathway with a matched pathway under the same defender response: '
                "a human team at the documented pace, or, where the AI's conduct is the point, the same AI "
                "acting differently. The AI's edge is measured on recovery and service; deaths are reported "
                'alongside as an outcome of the model, never a design target. Figures are model outputs from '
                "each case's default study.",
                '',
                '| Case | Recovery measure | AI pathway | Matched pathway | Deaths (AI / matched) |',
                '| --- | --- | --- | --- | --- |',
                *rows,
                '',
                '## The cases',
                '',
                *index,
                '',
            ]
        )
    return outputs
