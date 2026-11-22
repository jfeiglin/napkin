"""Reusable and single-pass path selections describe the same ordered report rows."""

from dataclasses import replace

from napkin.engine.report import Lag, report
from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key


def selection_case(seed):
    first, second = 7 + seed % 29, 3 - seed % 13
    source = f"""scenario "Selected counters"
    horizon 2 h
first = {first}
second = {second}
"""
    model = compile_text(source, {'h': {'time': 1}})
    config = model.configuration
    paths = ['first', 'second'] if seed % 2 == 0 else ['second', 'first']
    if seed % 3:
        paths.append(paths[seed % 2])
    if seed % 2:
        keys = tuple(Key('', (key,)) for key in dict.fromkeys(paths))
        config = replace(config, request=replace(config.request, everything=False, keys=keys))
    record = run(model.program, config)
    times = (1, 2) if seed % 3 == 0 else (2, 1)
    values = {'first': (first, first), 'second': (second, second)}
    expected = [(key, values[key]) for key in paths]
    readings = read(record, model.program, iter(paths), times)
    outcomes = {'read.iterator': (expected, [(row.path, row.values) for row in readings])}
    lag = Lag(1, 1)
    for name, make in (
        ('list', list),
        ('tuple', tuple),
        ('iterator', iter),
        ('generator', lambda p: (v for v in p)),
    ):
        for label, lags in (('plain', {}), ('lag', {paths[0]: lag})):
            rows = report(record, model.program, config, make(paths), times, lags=lags).values
            wanted = [(key, nums, lags.get(key)) for key, nums in expected]
            outcomes[f'{name}.{label}'] = wanted, [(row.path, row.values, row.lag) for row in rows]
        try:
            report(record, model.program, config, make(paths), times, lags={'missing': lag})
        except ValueError as exc:
            error = str(exc)
        else:
            error = 'accepted'
        outcomes[f'{name}.unselected lag'] = 'a lag of missing, which the report does not select', error
        try:
            report(record, model.program, config, make([*paths, 'missing']), times)
        except KeyError:
            error = 'unknown path'
        else:
            error = 'accepted'
        outcomes[f'{name}.unknown path'] = 'unknown path', error
    return source, outcomes


def check_path_selection(seed):
    source, outcomes = selection_case(seed)
    differences = {name: pair for name, pair in outcomes.items() if pair[0] != pair[1]}
    assert not differences, (seed, source, differences)
