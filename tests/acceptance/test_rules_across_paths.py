"""Rules that every path of napkin must keep, each checked from source through every public path that
reads it (the readiness audit of `8b3a01a`: a rule fixed on one path was still broken on another).

Written by the main session, apart from the agents that fixed the causes, so that a blind spot of one
agent's fix and of its own test is not shared by these:

- **No walk of a model's graph recurses in Python.** A model whose values form long chains (a chain
  of top-level formulas over a store, and a chain of members through their links) compiles, runs,
  reads, reports with a lag (the never-falls proof through the chain) and with its trail, and goes
  through `napkin compile`, `napkin run` and the run store cold and warm, with the recursion limit far
  below the length of a chain.
- **A value's trail is its own.** The trail of a value is the same whatever else its report holds, and
  in whatever order: on random models of nested formulas that branch on the time and on a store that
  fills, with a lag on the store in the larger report.

Each expected value is worked by hand from the text."""

from __future__ import annotations

import random
import sys
from contextlib import contextmanager

import pytest

from napkin.engine import read, run
from napkin.engine.report import Lag, report
from napkin.model.compile import compile_text
from tests.commands.call import napkin, package
from tests.program.examples import UNITS

LINKS = 1_000
FORMULAS = 2_000
# Far below the length of either chain, and above what pytest and the paths need on their own.
LIMIT = 300

FILES_UNITS = {'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'A litre.'}}


def chains():
    """The text of a model with two chains: `v0` reads `v1` and so on to `v1999`, which reads a store
    filled at 1 L/h from 0 L, so each `v` is the store's water; and members `l0` to `l999` of a
    template whose `total` is its own 1 L and the `total` of the member that it links to, the last
    member's being its 1 L alone, so `l0.total` is 1,000 L."""
    rows = [
        'scenario "Chains"',
        '    horizon 2 h',
        '',
        'store:',
        '    water: L = 0 L in [0,]',
        '    flow fill: SOURCE -> this.water',
        '        request = 1 L/h',
        '',
        'Link:',
        '    input level: L = 1 L',
        '    next: Link',
        '    total: formula(L) = formula(this.level + this.next.total)',
        '',
    ]
    for k in range(LINKS):
        rows.append(f'l{k}: Link')
        if k + 1 < LINKS:
            rows.append(f'    next = l{k + 1}')
        else:
            rows += ['    next = l0', '    total = formula(this.level)']
    rows.append('')
    rows += [f'v{k} = formula(v{k + 1} + 0 L)' for k in range(FORMULAS - 1)]
    rows.append(f'v{FORMULAS - 1} = formula(store.water)')
    return '\n'.join(rows) + '\n'


@contextmanager
def recursion_limit(limit):
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(limit)
    try:
        yield
    finally:
        sys.setrecursionlimit(before)


@pytest.mark.deep
def test_long_chains_go_through_every_path_with_no_recursion(tmp_path, capsys, monkeypatch):
    """At 2 h the store holds 2 L, so `v0` is 2 L; its lag of 0.5 to 1 h is the mean of the store's
    1 L to 1.5 L, 1.25 L, which the never-falls proof grants through the chain of 2,000 formulas
    (each adds 0 L to a store that only fills). `l0.total` is 1,000 L at every time, its lag too."""
    text = chains()
    paths = ['v0', 'l0.total']
    lags = {'v0': Lag(0.5, 1), 'l0.total': Lag(0.5, 1)}
    with recursion_limit(LIMIT):
        compiled = compile_text(text, UNITS)
        program, configuration = compiled.program, compiled.configuration
        record = run(program, configuration)
        assert record.failure is None, record.failure
        assert [found.values for found in read(record, program, paths, [2])] == [(2.0,), (1000.0,)]
        found = report(record, program, configuration, paths, [2], lags, model=compiled.declared)
        assert [value.lag for value in found.values] == [Lag(0.5, 1), Lag(0.5, 1)]
        assert [value.values for value in found.values] == [(pytest.approx(1.25),), (pytest.approx(1000),)]
        assert all(value.trail for value in found.values)
        folder = package(tmp_path / 'chains', text, FILES_UNITS)
        compiled_command = napkin(capsys, 'compile', folder)
        assert compiled_command.code == 0, compiled_command.err
        ran = napkin(capsys, 'run', folder, '--value', 'v0', '--at', '2h', '--json')
        assert ran.code == 0, ran.err
        assert ran.doc['values']['v0']['values'] == [2.0]
        from napkin import store

        with store.use(tmp_path / 'store'):
            cold = store.run(program, configuration)
            warm = store.run(program, configuration)
        assert [found.values for found in read(cold, program, paths, [2])] == [(2.0,), (1000.0,)]
        assert [found.values for found in read(warm, program, paths, [2])] == [(2.0,), (1000.0,)]


# ---- a value's trail is its own ---------------------------------------------------------------------

TRAILS = """\
scenario "Trails"
    horizon 6 h

record ra: assumption "The first source."
record rb: assumption "The second source."
record rc: assumption "The third source."
record rs: assumption "The store fills at a litre an hour."

plant:
    input a: L = {a} L  @ra
    input b: L = {b} L  @rb
    input c: L = {c} L  @rc
    water: L = 0 L in [0,]  @rs
    flow fill: SOURCE -> this.water  @rs
        request = 1 L/h
    f1 = formula({f1})
    f2 = formula({f2})
    f3 = formula({f3})
"""
LEAVES = ('this.a', 'this.b', 'this.c', 'this.water')


def formula(rng, earlier, depth=0):
    """A random expression over the inputs, the store and the formulas before it: a leaf (a formula
    before it three times as likely as an input, so that formulas nest), or most often a branch on the
    time or on the store at one of two thresholds (so that a formula and one that it reads branch at
    the same time), else a `max`, a `min` or a sum of two."""
    leaves = LEAVES + 3 * tuple(f'this.{name}' for name in earlier)
    if depth >= 2 or rng.random() < 0.25:
        return rng.choice(leaves)
    left, right = formula(rng, earlier, depth + 1), formula(rng, earlier, depth + 1)
    form = rng.random()
    if form < 0.5:
        return f'({left} if t < {rng.choice((2, 3))} h else {right})'
    if form < 0.7:
        return f'({left} if this.water < {rng.choice((2, 3))} L else {right})'
    if form < 0.8:
        return f'max({left}, {right})'
    if form < 0.9:
        return f'min({left}, {right})'
    return f'({left} + {right})'


def trails_model(rng):
    found = {}
    for name in ('f1', 'f2', 'f3'):
        found[name] = formula(rng, tuple(found))
    numbers = {key: rng.choice((1, 2, 3, 5)) for key in 'abc'}
    return TRAILS.format(**numbers, **found)


PATHS = ('plant.f1', 'plant.f2', 'plant.f3', 'plant.a', 'plant.water')
TIMES = (0.5, 1.5, 2.5, 3.5, 5.0)
CASES = 200


@pytest.mark.parametrize('seed', range(CASES))
def test_a_values_trail_is_the_same_whatever_else_its_report_holds(seed):
    """For a random model and a random set of times, each path's trail in a report of several paths, in
    a random order and with a lag on the store, equals its trail in a report of it alone, with the
    store's lag only when it is the store's own report: what the reader read for the other values
    takes no part in it."""
    rng = random.Random(seed)
    compiled = compile_text(trails_model(rng), UNITS)
    program, configuration, model = compiled.program, compiled.configuration, compiled.declared
    record = run(program, configuration)
    assert record.failure is None, record.failure
    times = sorted(rng.sample(TIMES, rng.randint(1, len(TIMES))))
    paths = rng.sample(PATHS, rng.randint(2, len(PATHS)))
    lags = {'plant.water': Lag(0.5, 1)} if 'plant.water' in paths else {}
    together = report(record, program, configuration, paths, times, lags, model=model)
    for path, value in zip(paths, together.values, strict=True):
        own = {path: lags[path]} if path in lags else {}
        (alone,) = report(record, program, configuration, [path], times, own, model=model).values
        assert value.values == alone.values, (seed, path)
        assert value.trail == alone.trail, (seed, path, paths, times)


# ---- one request, one outcome, from the store or not ------------------------------------------------

EDITED = """\
scenario "Edited"
    horizon 4 h

plant:
    water: L = 5 L in [0 L,]
    ticks = 0
    flow fill: SOURCE -> this.water
        request = 1 L/h
    tick = event():
        after 2 h:
            this.ticks += 1

plant.tick.start()
"""


def edited_log(program, configuration):
    """The log of a session that stops before the tick at 2 h, where the water holds 7 L, and sets it
    to 4 L: an edit of -3 L from outside, which the store's ledger keeps."""
    from napkin.program.checkpoint import Breakpoint
    from napkin.session import Session

    session = Session(program, configuration, (Breakpoint('plant.tick.step[0]'),))
    stop = session.advance()
    assert stop is not None and stop.stop.t == 2
    session.edit('plant.water', 4)
    assert session.advance() is None
    return session.log


def outcome(record, program):
    """How a record ends (finished, or its stop's kind and time) and the water that it holds."""
    stop = record.stop
    ended = ('finished',) if stop is None else (stop.kind, float(stop.t))
    (water,) = read(record, program, ['plant.water'], [0, 1])
    return ended, water.values


@pytest.mark.parametrize('pieces', [1, 2, 10])
def test_a_request_has_one_outcome_cold_warm_and_with_a_later_edit(tmp_path, pieces):
    """A request for the water to 1 h, within a budget of pieces, replays the log of an edit at 2 h:
    the edit is after its horizon, so it takes no part, and the water is 5 L at 0 h and 6 L at 1 h. Its
    history has two pieces at 0 h, its start and the rate of the first round, so a budget of one piece
    ends the run at 0 h, by name, and one of two or more finishes. Asked of a fresh store (cold) and of
    one that holds both horizons of the same log (warm), the request ends the same way, holds the same
    values and offers the same paths. The readiness audit of 8b3a01a found a budget of 2 met cold and
    broken warm, by the ledger of the later edit."""
    from dataclasses import replace

    from napkin import store
    from napkin.commands.run import held
    from napkin.program.config import Request
    from napkin.program.record import Key

    compiled = compile_text(EDITED, UNITS)
    program, configuration = compiled.program, compiled.configuration
    log = edited_log(program, configuration)
    water = Key('plant', ('water',))
    short = replace(configuration, request=Request(1, everything=False, keys=(water,), pieces=pieces))
    with store.use(tmp_path / 'cold'):
        cold = store.run(program, short, log)
    with store.use(tmp_path / 'warm'):
        store.run(program, configuration, log)
        first_short = store.run(program, short, log)
        warm = store.run(program, short, log)
        assert first_short == warm
    assert outcome(cold, program) == outcome(warm, program)
    assert held(cold) == held(warm)
    if pieces == 1:
        assert outcome(cold, program)[0] == ('failure', 0.0) and cold.failure.detail('budget') == 1
    else:
        assert outcome(cold, program) == (('finished',), (5.0, 6.0)) and held(cold) == ['plant.water']


def test_a_run_over_its_budget_gives_no_checkpoint_after_it():
    """A run whose record holds more pieces at 0 h than its budget of one ends there, by name: it never
    reaches its stop at 2 h, so a caller cannot receive and edit a checkpoint of a record that is
    already over its budget (the readiness audit of 8b3a01a, row 18)."""
    from dataclasses import replace

    from napkin.program.checkpoint import Breakpoint
    from napkin.program.config import Request
    from napkin.session import Session

    compiled = compile_text(EDITED, UNITS)
    configuration = replace(compiled.configuration, request=Request(4, pieces=1))
    session = Session(compiled.program, configuration, (Breakpoint('plant.tick.step[0]'),))
    assert session.advance() is None
    failure = session.record.failure
    assert failure is not None and float(failure.t) == 0 and failure.detail('budget') == 1
