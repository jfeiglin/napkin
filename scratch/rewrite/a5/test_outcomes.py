"""The rule of the run step's outcomes (briefs/audit2.md, K; re-audit 19): the migration check passes a
run of a translation only when it ends as the old run did (finished, failed or paused; at the same
time, within the tolerance; for the same reason), or when the list of changes lists how it ends now,
whatever its values. A run that `napkin run` refuses (exit 1) fails the step until a row lists its
failure as that command reports it.

    NAPKIN_STORE=off /home/user/napkin/.venv/bin/python -m pytest -q -p no:cacheprovider \\
        scratch/rewrite/a5/test_outcomes.py

The old side is the piano tuners at the base commit, read once by the old compiler in a process of
its own (`check.old_facts`). Each new side is the hand translation (`examples/piano_tuners`) with one
change, written to a temporary folder and checked in this process. The expected rows come from
`napkin run` and from the record's own account of its stop, never from the check.
"""

from __future__ import annotations

import io
import json
import random
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # the scripts of A5 are no package: check.py imports newmodel.py

import check  # noqa: E402
import newmodel  # noqa: E402

from napkin.cli import main as napkin  # noqa: E402
from napkin.engine.timeline import Outside, run  # noqa: E402
from napkin.model.compile import load_scenario  # noqa: E402
from napkin.program.checkpoint import Breakpoint  # noqa: E402

OLD = check.BASE / 'examples' / 'piano_tuners' / 'model.scn'
NEW = HERE.parents[2] / 'examples' / 'piano_tuners'
TEST = 'check run examples/piano_tuners/model.scn'
YEAR = 8760.0  # the horizon of the old model, 1 year, in hours
FINISHED = 'finished at 8760 h'  # the old run's outcome
HEADER = '| test | quantity | old | new | cause | evidence |\n| --- | --- | --- | --- | --- | --- |\n'
# The line after which the audit goes, and the audit: it moves 2 tunings into a ledger that holds 1,
# so the run fails when it starts.
CAPACITY = '        capacity = formula(this.rate * this.staff)\n'
AUDIT = """    ledger: tunings = 0 in [0, 1]
    audit = event():
        when t >= {at!r} h:
            this.audit.start()
            reset when false
        after 0 h:
            move 2 tunings from this.due to this.ledger
"""
# The times of the failures: the audit's (re-audit 19: at the horizon, the old report's last time),
# the start, and times drawn between them.
DRAW = random.Random(19)
TIMES = [YEAR, 0.0, *sorted(round(DRAW.uniform(0, YEAR), 4) for _ in range(5))]


def translation(folder, *, audit=None, horizon=None):
    """The hand translation of the piano tuners, written to `folder`, with the audit at `audit` hours
    or with another `horizon` line; its entry file."""
    text = (NEW / 'model.scn').read_text(encoding='utf-8')
    if audit is not None:
        assert CAPACITY in text
        text = text.replace(CAPACITY, CAPACITY + AUDIT.format(at=audit))
    if horizon is not None:
        assert '    horizon 1 year\n' in text
        text = text.replace('    horizon 1 year\n', f'    horizon {horizon}\n')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'units.json').write_text((NEW / 'units.json').read_text(encoding='utf-8'), encoding='utf-8')
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    return folder / 'model.scn'


@pytest.fixture(scope='module')
def old_facts():
    """The facts of the old piano tuners, read once by the old compiler."""
    return check.old_facts(OLD)


@pytest.fixture
def checked(old_facts, monkeypatch, tmp_path):
    """A check of a new entry against the old piano tuners in this process, with a list of changes of
    one outcome row for each (old, new) pair of cells; its report."""

    def facts(entry, times=()):
        assert not times, 'an outcome row asks for no more old times'
        return old_facts

    monkeypatch.setattr(check, 'old_facts', facts)

    def checking(entry, outcomes=()):
        changed = tmp_path / 'changed.md'
        rows = ''.join(
            f'| {TEST} | outcome | {old} | {new} | made on purpose | napkin run |\n' for old, new in outcomes
        )
        changed.write_text(HEADER + rows, encoding='utf-8')
        return check.run(OLD, entry, quiet=True, out=io.StringIO(), changed=changed)

    return checking


@pytest.fixture
def standalone(monkeypatch, capsys):
    """`napkin run` of an entry with `--json`: (its exit code, why its run stopped, or None)."""
    monkeypatch.setenv('NAPKIN_STORE', 'off')

    def running(entry):
        code = napkin(['run', str(entry), '--value', 'tunings_done', '--json'])
        return code, json.loads(capsys.readouterr().out)['stopped']

    return running


def unlisted(outcome):
    """The check's line of a new outcome that no row lists, after the old run that finished."""
    return f'outcome: old {FINISHED}, new {outcome}; no row of the list of changes lists it'


def test_each_old_run_finishes_at_its_horizon(old_facts):
    """The old outcome is read from the old trajectory: the default study plays no run, so its run
    finishes at its horizon, and its times end there."""
    (entry,) = old_facts['runs']['runs'].values()
    assert entry['outcome'] == {'kind': 'finished', 'at': YEAR, 'why': None}
    assert entry['times'] == [0.0, YEAR]


@pytest.mark.parametrize('at', TIMES)
def test_a_run_that_fails_fails_the_step_until_a_row_lists_its_failure(at, checked, standalone, tmp_path):
    """Re-audit 19, as a rule: a new run that fails, at any time and whatever its values then (at the
    horizon every value is the old one), fails the run step as `napkin run` refuses it; the step
    passes once a row lists the failure as that command reports it, and not when the row's time,
    kind or reason is another."""
    entry = translation(tmp_path / 'new', audit=at)
    code, stopped = standalone(entry)
    found = re.fullmatch(r'the run failed at \S+ h: (?P<why>.+)', stopped or '', re.DOTALL)
    assert code == 1 and found is not None
    why = found['why']
    assert checked(entry).errors == {'run': [unlisted(f'failed at {at:.10g} h: {why}')]}
    assert not checked(entry, [(FINISHED, f'failed at {at!r} h: {why}')]).errors
    for other in (
        f'failed at {at + 1!r} h: {why}',
        f'paused at {at!r} h: {why}',
        f'failed at {at!r} h: {why[:40]}',
    ):
        assert list(checked(entry, [(FINISHED, other)]).errors) == ['run'], other


@pytest.mark.parametrize(('horizon', 'end'), [('2 year', 2 * YEAR), ('0.5 year', YEAR / 2)])
def test_a_run_that_finishes_at_another_time_fails_the_step_until_listed(horizon, end, checked, tmp_path):
    """A new run that finishes at another time ends otherwise: a longer one has the old times, which
    agree, and a shorter one does not reach the old horizon, whose values its outcome stands for. The
    number step also misses the old horizon, `1 year`."""
    entry = translation(tmp_path / 'new', horizon=horizon)
    assert checked(entry).errors['run'] == [unlisted(f'finished at {end:g} h')]
    assert 'run' not in checked(entry, [(FINISHED, f'finished at {end:g} h')]).errors


def test_a_run_that_a_breakpoint_stops_fails_the_step_until_listed(checked, tmp_path, monkeypatch):
    """A record that a breakpoint stopped ends `paused`, at its stop, at the breakpoint and before the
    stage that the record names (`Record.stopped`). A model's run sets no breakpoint (a caller does),
    so the check is given the record of such a run as the engine's."""
    entry = translation(tmp_path / 'new', audit=YEAR / 2)
    compiled = load_scenario(entry)
    stopped = run(compiled.program, compiled.configuration, (Breakpoint('tuners.audit.step[0]'),))
    found = re.fullmatch(r'the run stopped at \S+ h (?P<why>at the breakpoint .+)', stopped.record.stopped())
    paused = f'paused at {YEAR / 2:g} h: {found["why"]}'
    monkeypatch.setattr(newmodel, 'run_program', lambda program, configuration: stopped.record)
    assert checked(entry).errors == {'run': [unlisted(paused)]}
    assert not checked(entry, [(FINISHED, paused)]).errors


def test_a_run_that_the_engine_does_not_run_fails_the_step_until_listed(checked, monkeypatch):
    """A run that the engine refuses has no record: it fails, with no time and the engine's reason,
    and none of its values is compared."""

    def refused(program, configuration):
        raise Outside('tuners.tune: a flow that this engine does not run')

    monkeypatch.setattr(newmodel, 'run_program', refused)
    failed = 'failed: the engine does not run it: Outside: tuners.tune: a flow that this engine does not run'
    assert checked(NEW / 'model.scn').errors == {'run': [unlisted(failed)]}
    assert not checked(NEW / 'model.scn', [(FINISHED, failed)]).errors


def test_a_row_of_the_outcome_of_runs_that_end_alike_fails_the_step(checked):
    """A row that lists the outcome of a run that ends as the old one did is stale."""
    report = checked(NEW / 'model.scn', [(FINISHED, FINISHED)])
    assert report.errors == {'run': [f'outcome: changed.md:3 lists it, but the runs end alike: {FINISHED}']}


def test_a_report_that_fails_keeps_the_outcome_of_its_run(monkeypatch, tmp_path):
    """The outcome comes from the record before any value is read: a report that fails leaves the
    run without values and with its failure."""

    def broken(*arguments, **named):
        raise LookupError('a reader that fails')

    monkeypatch.setattr(newmodel, 'report', broken)
    entry = translation(tmp_path / 'new', audit=YEAR)
    reads = {'': {'paths': ['tunings_done'], 'times': [0.0, YEAR], 'lags': {}}}
    (result,) = newmodel.results(load_scenario(entry), reads).values()
    assert result['error'] == 'the report of the run fails: LookupError: a reader that fails'
    assert (result['outcome']['kind'], result['outcome']['at'], result['values']) == ('failed', YEAR, {})
