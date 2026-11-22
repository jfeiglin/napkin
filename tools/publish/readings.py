"""Render instantaneous start and horizon readings for one current-language model."""

from pathlib import Path

from napkin import report
from napkin.engine.report import Shown
from napkin.model import load_scenario
from napkin.model.runs import options_of
from napkin.model.support import CODE, DATUM
from napkin.program.record import Unavailable

from .. import catalogue
from . import cell, write
from .brief import brief_of, shown, value_note

OUTPUT = Path('results/readings.md')


def display(value):
    if isinstance(value, Unavailable):
        return f'Unavailable ({value.reason})'
    if isinstance(value, Shown):
        return value.text or value.rating
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return format(value, '.9g')
    return str(value)


def render(model, *, jobs=1):
    """The completed named runs in featured order, with the exercised evidence at each reading."""
    problems = [item for item in model.reports if item.code in (CODE, DATUM)]
    if problems:
        raise ValueError('\n'.join(f'{p.file}:{p.line}: {p.message} [{p.code}]' for p in problems))
    brief = brief_of(model)
    ids = [r.name for r in model.declared.runs] or [None]
    order = list(dict.fromkeys([*(brief.featured or ()), *ids]))
    completed = catalogue.completed_study(model, runs=order, jobs=jobs)
    scenario = model.declared.scenario
    lines = [f'# {cell(scenario.title)}', '']
    if scenario.summary:
        lines.extend([cell(scenario.summary), ''])
    if scenario.scope:
        lines.extend([cell(scenario.scope), ''])
    lines.extend([f'Model revision `{model.model_hash}`. All times are in hours.', ''])
    cited = {}
    for name, record in completed.items():
        lines.extend(
            [
                f'## {cell(name) if name is not None else "Default run"}',
                '',
                '| Reading | Time (h) | Value | Unit | Evidence |',
                '|---|---:|---|---|---|',
            ]
        )
        paths = shown(brief, model, record)
        unavailable = {path: value_note(model, 'not_estimated', path, 'reason') for path in paths}
        measured = [path for path in paths if unavailable[path] is None]
        config = model.configure(name)
        options = options_of(model.declared, name)
        for at in dict.fromkeys([0, record.end]):
            result = report(record, model.program, config, measured, [at], table=model.table, options=options)
            definitions = {rid: (kind, text) for rid, kind, text in result.records}
            readings = {value.path: value for value in result.values}
            for path in paths:
                if path not in readings:
                    row = (path, f'{at:g}', f'Not estimated ({unavailable[path]})', '', '')
                else:
                    value = readings[path]
                    references = dict.fromkeys(
                        rid for item in value.trail if item.exercised for rid in item.records
                    )
                    for rid in references:
                        if rid in definitions:
                            cited[rid] = definitions[rid]
                    row = (
                        path,
                        f'{at:g}',
                        display(value.values[0]),
                        value.unit or '1',
                        ', '.join(references),
                    )
                lines.append('| ' + ' | '.join(cell(item) for item in row) + ' |')
        lines.append('')
    if cited:
        lines.extend(['## Evidence', ''])
        lines.extend(
            f'- **{cell(rid)}** ({cell(kind)}). {cell(text)}' for rid, (kind, text) in sorted(cited.items())
        )
        lines.append('')
    return '\n'.join(lines)


def publish(path, *, check, jobs=1):
    """Generate or check only this entry's readings file. Return its path and whether it matches."""
    entry = Path(path)
    if entry.is_dir():
        entry = entry / 'model.scn'
    content = render(load_scenario(entry), jobs=jobs)
    target = entry.parent / OUTPUT
    if check:
        return target, target.is_file() and target.read_bytes() == content.encode('utf-8')
    write({OUTPUT: content}, entry.parent)
    return target, True
