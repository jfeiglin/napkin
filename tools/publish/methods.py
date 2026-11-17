"""Render current scenario methods from typed definitions and independent references."""

from decimal import Decimal
from posixpath import relpath

from napkin import __version__
from napkin.model.ir import basis_records

from .. import catalogue
from . import cell, limits
from .pages import Pages
from .texts import input_text


def artifacts(ctx):
    return {
        catalogue.result(sid, 'methods.md'): scenario_methods(
            model, link=lambda target, sid=sid: relpath(target, catalogue.result(sid))
        )
        for sid, model in ctx.models.items()
    }


def by_definition(runs, resolved, collection, render):
    """Each name's distinct definitions in a resolved collection, as rendered, with their options.

    A run's structure can define an output otherwise than another's (an output reads zero for a stock
    that the structure leaves out), so one name can have several definitions: each keeps its own row
    instead of the last run's overwriting the rest. ``render(name, definition)`` gives a row as
    (label, identifier note, remaining cells); each result adds the options of the runs using that
    definition when the name has more than one.
    """
    rows = {}
    for run, structure in resolved.items():
        option = runs[run]['option']
        for name, definition in structure.section(collection).items():
            users = rows.setdefault(name, {}).setdefault(render(name, definition), [])
            if option not in users:
                users.append(option)
    return [
        (label, note, rest, options if len(definitions) > 1 else [])
        for definitions in rows.values()
        for (label, note, rest), options in definitions.items()
    ]


# Where an input applies, in reader words, by the groups of the options that set it.
APPLIES_TO = {
    'every': 'all pathways',
    'option': 'option',
    'run': 'one pathway',
}


def applies_to(pages, model):
    """{input: where it applies}: an input that no option sets applies to every pathway; one that only
    the options of the group of the responses (`choice_group` in brief.toml) set, to that group, by its
    name; one that only the options of the option groups set, to the option; one that a run's other
    options set, to one pathway."""
    options = set(pages.option_groups())
    responses = pages.brief.choice_group
    out = {}
    for name, info in model.inputs.items():
        groups = set(info['groups'])
        if groups and groups == {responses}:
            out[name] = responses
            continue
        if not groups:
            where = 'every'
        elif groups <= options:
            where = 'option'
        else:
            where = 'run'
        out[name] = APPLIES_TO[where]
    return out


def option_axis(pages):
    """The name of the options that each run takes besides its response (its option of the group of the
    responses): the groups that hold them, else "Option". Options may describe conduct or protection."""
    axis = pages.options()['axis']
    return axis['name'] if axis else 'Option'


def table_rows(rows):
    """Markdown rows; a definition that is one of several names the options it applies to."""
    lines = []
    for label, note, rest, options in rows:
        notes = [note] if note else []
        if options:
            names = '; '.join(cell(option) for option in options)
            notes.append(f'option{"s" if len(options) > 1 else ""}: {names}')
        first = f'{label} ({"; ".join(notes)})' if notes else label
        lines.append(f'| {first} | {rest} |')
    return lines


def number(value):
    """A number as the scenario gives it, never with an exponent: 2e-05 reads 0.00002."""
    text = str(value)
    return format(Decimal(text), 'f') if 'e' in text.lower() else text


def outcome_row(name, d):
    """An outcome's row. Its calculation is an expression; an outcome without one is not estimated, and
    the reason why is prose, not code."""
    if d.expr is not None:
        computation = f'`{cell(d.expr)}`'
    else:
        computation = ' '.join(['Not estimated.', *([cell(d.reason)] if d.reason else [])])
    return cell(d.label), '', f'{cell(d.unit)} | {cell(d.scope)} | {computation}'


def parameter_row(applies):
    """An input's row. A bool input reads Yes or No, as in the brief, never as a share between 0 and
    1."""

    def render(name, d):
        adjust = d.adjust
        explanation = ' '.join(record['explanation'] for record in basis_records(d.basis))
        # The structure marks a bool input a binary control, and a named input a choice of its values.
        metadata = d.metadata if d.metadata is not None else {}
        switch = metadata.get('control') == 'binary'
        names = list(metadata.get('values') or ())
        if names:
            values = f'Fixed {names[int(d.value)]}' if adjust.mode == 'locked' else ' or '.join(names)
        elif adjust.mode == 'locked':
            values = f'Fixed {input_text(d.value, d.unit, switch=True) if switch else number(d.value)}'
        else:
            values = 'Yes or No' if switch else f'{number(adjust.minimum)}–{number(adjust.maximum)}'
        unit = 'yes/no' if switch else 'choice' if names else cell(d.unit)
        return (
            cell(d.label),
            f'`{name}`',
            f'{unit} | {applies[name]} | {values} | {cell(explanation)}',
        )

    return render


def premises(review):
    """The conditions the scenario holds true, each with where it comes from."""
    authored = review['premises']
    if not authored:
        return []
    return [
        '## Premises',
        '',
        'The scenario holds these conditions true. Where one does not hold, the results do not apply.',
        '',
        '| Premise | Where it comes from |',
        '|---|---|',
        *(
            f'| {cell(item["statement"])} | {cell(item.get("basis", {}).get("explanation", ""))} |'
            for item in authored
        ),
        '',
    ]


# The effect of the attack, for a start that has no doc of its own.
EFFECT = 'cyber attack'
# How each kind of start begins the pathways: a start that changes nothing, after which the
# operation's first events follow, and a start that changes the systems.
STARTS = {
    'first_effect': 'The AI operation starts with its first events. Whether each attack action happens or is blocked decides what follows.',
    'call': 'The first AI cyber action starts the incident and the clocks of the response.',
}


def starts_change(scenario):
    """Whether the start changes the systems: an outcome of the event `start` has lines."""
    event = scenario.start_event()
    return event is not None and any(outcome.lines for outcome in event.outcomes)


def start_limits(pages, review):
    """The limits of the first move: the statement of the reviewers' premise with id START, which needs
    no basis. The page gives them after the effect of the attack, so a scenario with a start states
    them."""
    if 'start_limits' not in review:
        pages.fail(
            ('notes:', 'premises:'),
            'a premise with id START states the limits of the first move, which the methods page gives',
        )
    return review['start_limits']


def sentence(text):
    """A phrase as a sentence of its own: it starts with a capital letter and ends with a full stop."""
    return text[:1].upper() + text[1:] + ('' if text.endswith('.') else '.')


def scenario_methods(model, *, link):
    """The methods record of one scenario's model; link maps repository-relative targets."""
    pages = Pages(model)
    scenario = model.scenario
    sid = catalogue.name_of(model.origin)
    responses = pages.brief.choice_group
    runs = pages.runs()
    review = pages.review()
    resolved = {run: model.resolve(run) for run in model.runs}
    start = scenario.start
    operation = pages.operation()
    lines = [
        f'# {sid} methods: {scenario.title}',
        '',
        scenario.summary or '',
        '',
        'This page describes the model of this scenario and its pathways.',
        f'Model version: `{model.model_hash}`. Engine version: `{__version__}`.',
        '',
        '## The attack and who it affects',
        '',
        *(
            [
                sentence(pages.brief.attack or EFFECT),
                '',
                start_limits(pages, review),
                '',
            ]
            if start
            else []
        ),
        review.get('exposure', {}).get(
            'scope', 'The outcome definitions name the people or services that the scenario counts.'
        ),
        '',
        *([STARTS['call' if starts_change(scenario) else 'first_effect'], ''] if start else []),
        # The attacker's own paragraph, apart from the page's account of how the model counts.
        *([operation['doc'], ''] if operation else []),
        # The group of the responses (`choice_group` in brief.toml), by its name, when there is one.
        (
            f'Each pathway combines one choice of {responses} with one option.'
            if responses
            else 'Each pathway is one option.'
        )
        + ' The model counts people,',
        'materials, services and money in the units of the scenario. When a quantity moves, what',
        'leaves one place arrives at the next. Shared resources go to their users by priority or in',
        'fixed shares, as the scenario sets.',
        '',
        *premises(review),
    ]
    # The reviewers' limits go after the premises. The part is made last, from the whole page, so that
    # it leaves out a limit that the page already states.
    caveats = len(lines)
    lines += [
        '## Calculated outcomes',
        '',
        '| Outcome | Unit | What it counts | Calculation |',
        '|---|---|---|---|',
        *table_rows(by_definition(runs, resolved, 'outcomes', outcome_row)),
    ]
    # The column of the group of the responses, by its name, when there is one.
    swap = [cell(responses)] if responses else []
    lines += [
        '',
        '## Pathways and reporting times',
        '',
        '| ' + ' | '.join(['Pathway', *swap, cell(option_axis(pages)), 'Results at, hours']) + ' |',
        '|---|' + '---|' * (len(swap) + 1) + '---:|',
    ]
    for run, structure in resolved.items():
        info = runs[run]
        cells = [info['name'], *([info['response']] if swap else []), info['option']]
        lines.append(f'| {" | ".join(cell(c) for c in cells)} | {number(structure.time.horizon)} |')
    lines += [
        '',
        'Each completed study keeps its inputs, its events, the values at each reporting time, its',
        'numerical settings and the versions of the model and the library. The briefs and the run',
        'tables come from these completed results.',
        '',
        '## Inputs and their sources',
        '',
        'The table shows the range of each input, where it applies and where its value comes from.',
        'It also includes the inputs that only some options use.',
        '',
        '| Input | Unit | Applies to | Allowed values | Where the value comes from |',
        '|---|---|---|---|---|',
        *table_rows(by_definition(runs, resolved, 'parameters', parameter_row(applies_to(pages, model)))),
    ]
    verification = review.get('verification', {})
    if verification:
        research = link(catalogue.in_package(sid, verification['research']))
        if verification.get('accounting'):
            lines += [
                '',
                '## How the harm is calculated and checked',
                '',
                f'[The research record]({research}) names the patient group, the source populations, the',
                'outcome and its timing, the source values applied to this scenario, the economic accounts',
                'and the local measurements that are still necessary.',
                verification['accounting'] + '.',
            ]
        else:
            lines += [
                '',
                '## Research basis and limits',
                '',
                f'[The research record]({research}) documents the sources, assumptions and limits of the model.',
                'The outcome definitions above identify the quantities that are calculated and those that are not estimated.',
            ]
        lines.append(
            'Each complete report keeps its inputs, its values at each reporting time and the versions used.'
        )
    lines += [
        '',
        '## Independent checks and how to repeat the results',
        '',
        f'Independent checks in the [test suite]({link("tests")}) calculate the mathematics again, check that',
        'no quantity is lost or created, and test the schedules and the cases that must fail.',
        f'[Evidence checks]({link(f"{catalogue.DOCS}/evidence/README.md")}) show how each source was found, read and matched to the text',
        f'that it supports. [Review records]({link(f"{catalogue.DOCS}/evidence/reviews/README.md")}) list the scientific and model reviews',
        'and what each one decided.',
        '',
        'The Radau solver uses the time step that the scenario sets. Parts of the model that',
        'are proved to be linear use exact solutions. Reports keep the full calculated precision; the',
        'pages round the values for display.',
        '',
        'Run `python -B -m tools.check` to check the software. Run',
        f'`napkin run {catalogue.in_package(sid)}'
        + (f' --variant {sid.partition(":")[2]}' if ':' in sid else '')
        + '` to run the scenario again; `--set NAME=VALUE` and',
        '`--edits FILE` change its inputs.',
        '',
    ]
    lines[caveats:caveats] = limits(review['limitations'], '\n'.join(lines))
    return '\n'.join(lines)
