"""Render instantaneous start and horizon readings for one current-language model."""

from pathlib import Path

from napkin import report
from napkin.engine.report import Shown
from napkin.engine.timeline.record import Reader, in_unit, key_of
from napkin.model import load_scenario
from napkin.model.runs import options_of
from napkin.model.support import CODE, DATUM
from napkin.package import entries
from napkin.program.record import Unavailable

from .. import catalogue
from . import cell, write
from .brief import brief_of, shown, value_note

OUTPUT = Path('results/readings.md')


def artifacts(ctx):
    return {
        catalogue.result(sid, OUTPUT.name): render(model, jobs=ctx.jobs) for sid, model in ctx.models.items()
    }


# A reading shows six significant figures, the legacy display precision, and a value within a
# millionth of its own comparison scale shows as zero. The last digits of a calculated value differ
# between computers (their BLAS and SIMD kernels round differently), and so does the residue that a
# drained queue or an emptied store keeps; a committed page must be the same on every computer.
FIGURES = 6
NEGLIGIBLE = 1e-6


def display(value, scale=None):
    """A reading as the page shows it; `scale` is its comparison scale in its displayed unit."""
    if isinstance(value, Unavailable):
        return f'Unavailable ({value.reason})'
    if isinstance(value, Shown):
        return value.text or value.rating
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        if scale is not None and abs(value) <= NEGLIGIBLE * scale:
            return '0'
        return format(value, f'.{FIGURES}g')
    return str(value)


def scale_of(reader, program, path, at):
    """The comparison scale of a reading at a time in its displayed unit, or None."""
    try:
        key = key_of(program, path)
        _, unit = reader.checked(key)
        floor = reader.comparison_floor(key, at)
    except (KeyError, LookupError, ValueError, TypeError):
        return None
    return None if floor is None else in_unit(floor, unit)


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
    lines.extend(
        [
            f'Model revision `{model.model_hash}`. Readings are instantaneous, without reporting lags. All times are in hours.',
            '',
        ]
    )
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
        reader = Reader(record, model.program)
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
                        display(value.values[0], scale_of(reader, model.program, path, at)),
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


def same_page(committed, rendered):
    """Whether a committed readings page is the current one. Every line must match, except that a
    value on a rounding tie can round to the next unit of its sixth figure on another computer."""
    old, new = committed.splitlines(), rendered.splitlines()
    return len(old) == len(new) and all(a == b or _same_row(a, b) for a, b in zip(old, new))


def _same_row(a, b):
    first, second = a.split(' | '), b.split(' | ')
    if len(first) != len(second) or len(first) < 5 or not a.startswith('| '):
        return False
    differ = [k for k, (x, y) in enumerate(zip(first, second)) if x != y]
    if differ != [2]:
        return False
    try:
        x, y = float(first[2]), float(second[2])
    except ValueError:
        return False
    return abs(x - y) <= 10.0 ** (1 - FIGURES) * max(abs(x), abs(y))


def publish_package(path, *, check, jobs=1):
    """Render every variant before writing any files. Each variant owns its readings."""
    pages = {entry.parent: render(load_scenario(entry), jobs=jobs) for entry in entries(path).values()}
    results = {}
    for folder, content in pages.items():
        target = folder / OUTPUT
        if check:
            results[target] = target.is_file() and same_page(target.read_text(encoding='utf-8'), content)
        else:
            write({OUTPUT: content}, folder)
            results[target] = True
    return results


def publish(path, *, check, jobs=1):
    """Generate or check one entry and return its path and whether it matches."""
    if len(entries(path)) != 1:
        raise ValueError('a family has more than one readings file; select a variant or use publish_package')
    return next(iter(publish_package(path, check=check, jobs=jobs).items()))
