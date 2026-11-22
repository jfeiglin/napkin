"""Publish each package's named comparisons from the current model's completed records."""

from .. import catalogue
from . import cell
from .brief import Comparison, brief_of, comparisons_of, featured
from .paired import contrast, numeric
from .readings import check_support, display, reported_rows


def artifacts(ctx):
    return {
        catalogue.result(sid, 'brief.md'): render(model, completed=ctx.studies[sid])
        for sid, model in ctx.models.items()
    }


def render(model, *, jobs=1, completed=None):
    """Render end-of-run values for the featured run or pair and each other declared comparison."""
    check_support(model)
    brief = brief_of(model)
    first = tuple(featured(brief, model))
    comparisons = list(comparisons_of(brief, model))
    groups = []
    if len(first) == 2:
        comparisons.remove(Comparison(run=first[1], against=first[0]))
    if brief.featured or not comparisons:
        groups.append(first)
    groups.extend((pair.against, pair.run) for pair in comparisons)

    runs = list(dict.fromkeys(run for group in groups for run in group))
    if completed is None:
        completed = catalogue.completed_study(model, runs=runs, jobs=jobs)
    values = {}
    for run in runs:
        record = completed[run]
        values[run] = {
            path: reading for path, _, reading, _ in reported_rows(brief, model, run, record, [record.end])
        }

    scenario = model.declared.scenario
    lines = [f'# {cell(scenario.title)}', '']
    for paragraph in (scenario.summary, scenario.scope):
        if paragraph:
            lines.extend([paragraph, ''])
    lines.extend(
        [
            f'Readings at {model.base.request.horizon:g} h. [Run readings and evidence](readings.md).',
            '',
        ]
    )
    for group in groups:
        labels = [cell(name) if name is not None else 'Default run' for name in group]
        heading = f'{labels[1]} against {labels[0]}' if len(group) == 2 else labels[0]
        extra = ['Change (run − baseline)', 'Change (%)'] if len(group) == 2 else []
        lines.extend(
            [
                f'## {heading}',
                '',
                '| Reading | Unit | ' + ' | '.join([*labels, *extra]) + ' |',
                '|---|---|' + '---:|' * (len(group) + len(extra)),
            ]
        )
        paths = dict.fromkeys(path for run in group for path in values[run])
        for path in paths:
            cells = [values[run].get(path) for run in group]
            unit = next(item.unit for item in cells if item is not None)
            row = [path, unit, *(item.text if item is not None else 'Unavailable' for item in cells)]
            if len(group) == 2:
                change, percent = '—', '—'
                if all(item is not None and numeric(item.value) for item in cells):
                    base, compared = cells
                    if base.unit != compared.unit:
                        raise ValueError(f'{path}: units differ across runs')
                    delta, relative = contrast(base.value, compared.value, base.scale, compared.scale, unit)
                    change = display(delta)
                    if relative is not None:
                        percent = display(relative)
                row.extend((change, percent))
            lines.append('| ' + ' | '.join(cell(item) for item in row) + ' |')
        lines.append('')
    return '\n'.join(lines)
