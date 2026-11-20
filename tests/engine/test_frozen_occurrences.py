"""A finished occurrence is frozen (re-audit 14, `briefs/audit3.md` part E; PLAN, change 24 b).

The rule (spec, "State owned by an invocation": "A finished occurrence is frozen, and a write to it
is an error"; D7, a finished occurrence is a stable record; G0, "Allow writes to live occurrences";
the owner's answer, change 24 b): the error is an actual write to a finished occurrence, and it fails
the run by name at the moment that it happens; the same write while the occurrence runs is made.

- **Statements.** An assignment to its field is always a write: `=`, `+=` (of 0 L too), `-=` and
  `= formula(...)`. A `move` of a nonzero amount into or out of its store is a write; a move of 0 L
  moves nothing, and the run goes on. Each through a reference saved at the entry, a reference
  copied from one, `.occurrences.at(t)`, which names the newest start then, or a reference to
  another member's occurrence through a link. The property runs each of them at random times before
  and after the finish, with a later start of the same event or none: the run fails at the time of
  the write, naming the value, the finished occurrence and the statement, and holds nothing of the
  stage that wrote (its write before that one included); before the finish the write is made, and
  its effect is the closed form worked here.
- **Flows.** A flow of another occurrence that carries a nonzero rate into or out of one of its
  stores writes it: the run fails at the moment that the rate is nonzero, naming the flow, the store
  and the finished occurrence. A flow present at the finish with its rate fails then; one that joins
  after with a rate fails as it joins. A connected flow at zero rate writes nothing ("A flow whose
  rate falls to zero stays connected for its owner's lifetime"): out of the empty store, with no
  request or closed, the run goes on. A flow whose rate becomes nonzero after the finish fails at
  that moment: a stage that sets its request, the time that switches it, the store that feeds it
  filling, and a rate that rises from zero with the water that it reads. A store that another
  occurrence's flow met is retired as the occurrence's own stores are ("Each occurrence-owned
  physical store must have zero residual inventory at normal completion").
- **Stops.** Stopped before the write and resumed, in place and in a fresh process, the run fails at
  the same time with the same message, a write by a statement as one by a flow; an edit at the stop
  that enables the write gives that failure; an edit of the finished occurrence's value is refused
  (change 15: "a finished occurrence stays frozen").
- **A shorter run.** A run whose horizon comes before the write finishes, and the failed run's
  record cut to that horizon (`store.served`) is its record.

The oracle (`tests/reference/`) follows the same rule: each model here runs there too, and must fail
at the same time naming the same value, or go on.
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

from napkin import store
from napkin.engine.timeline import Plan, Run, read, run
from napkin.model.compile import compile_text
from napkin.program.artifact import Artifact
from napkin.program.checkpoint import Breakpoint, Checkpoint, CheckpointError, decode, dumps
from napkin.program.config import Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
ROOT = Path(__file__).resolve().parents[2]
FROZEN = 'belongs to the finished occurrence {0}, which is frozen'

# The writes of a stage, as (statement with REF for the reference, the field it writes, whether it
# writes after the finish: a move of 0 L moves nothing).
WRITES = {
    'set': ('REF.size = 1 L', 'size', True),
    'add': ('REF.size += 1 L', 'size', True),
    'add nothing': ('REF.size += 0 L', 'size', True),
    'subtract': ('REF.size -= 1 L', 'size', True),
    'define': ('REF.rate = formula(this.seen / 5 h)', 'rate', True),
    'move in': ('move 1 L from this.water to REF.batch', 'batch', True),
    'move out': ('move 1 L from REF.batch to this.water', 'batch', True),
    'move nothing': ('move 0 L from REF.batch to this.water', 'batch', False),
}
REFERENCES = {'saved': 'job', 'copied': 'other', 'newest': 'this.repair.occurrences.at(t)'}


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def frozen_model(write, reference, repair, writes, second):
    """A crew whose repair of 3 L starts at 0 h with its amount in its batch and takes `repair`
    hours, ending with its batch moved back to the water; a watch, started with it, writes 5 L to
    `seen` and then makes `write` through `reference` at `writes` h; `second`, the time of a second
    repair of 7 L, or None."""
    statement = WRITES[write][0].replace('REF', REFERENCES[reference])
    again = '' if second is None else 'crew.again.start()\n'
    horizon = max(repair, writes, second or 0) + repair + 1
    return compiled(
        f"""
        scenario "Frozen"
            horizon {horizon} h
        crew:
            water: L = 10 L in [0,]
            seen: L = 0 L
            repair = event(amount: L):
                size: L = amount
                rate = formula(0 L/h)
                batch: L = amount in [0,]
                after {repair} h:
                    move batch from batch to this.water
            watch = event():
                job = this.repair.occurrences.at(t)
                other = job
                after {writes} h:
                    this.seen = 5 L
                    {statement}
            again = event():
                after {second or 0} h:
                    this.repair.start(7 L)
        crew.repair.start(3 L)
        crew.watch.start()
        {again}"""
    ), horizon


def target_of(reference, repair, writes, second):
    """The occurrence that the write names (its number), and whether it runs at the write. Stages
    due together commit in the order in which their occurrences were made (D5): the watch, made at
    0 h, writes before the second repair's last stage due then, and after the first repair's."""
    if reference == 'newest' and second is not None and second < writes:
        return 1, writes <= second + repair
    return 0, writes < repair


def value_at(record, program, key, t):
    (reading,) = read(record, program, [key], [t])
    return reading.values[0]


def message(record):
    return record.failure.detail('message')


def oracle(found):
    """The oracle's run of a model: (the time at which it failed and its message, or None)."""
    ran, failed = run_of(found.program, found.configuration)
    return None if failed is None else (ran.view.t, str(failed))


@pytest.mark.parametrize('seed', range(48))
def test_a_write_to_an_occurrence_is_made_while_it_runs_and_fails_by_name_after_it_finished(seed):
    rng = random.Random(seed)
    write, reference = sorted(WRITES)[seed % len(WRITES)], rng.choice(sorted(REFERENCES))
    # Halves and wholes apart, so that no write is due with a finish.
    repair, writes = rng.choice([1, 2, 3, 4]), rng.choice([0.5, 1.5, 2.5, 3.5, 4.5])
    second = rng.choice([None, 0.5, 1.5, 2.5])
    found, horizon = frozen_model(write, reference, repair, writes, second)
    record = run(found.program, found.configuration)
    number, running = target_of(reference, repair, writes, second)
    occurrence, field, writing = f'crew.repair#{number}', WRITES[write][1], WRITES[write][2]
    if writing and not running:
        assert record.failure is not None and record.failure.t == writes
        text = f'{occurrence}.{field} {FROZEN.format(occurrence)}'
        assert text in message(record)
        assert 'crew.watch.step[0].do[1]' in message(record)
        # The stage that writes is discarded whole: its write of 5 L before is not in the record.
        assert value_at(record, found.program, 'crew.seen', writes) == 0
        (t, said) = oracle(found)
        assert t == writes and text in said
        return
    assert record.failure is None, message(record)
    assert oracle(found) is None
    assert value_at(record, found.program, 'crew.seen', horizon) == 5
    amount = 3 if number == 0 else 7
    if write in ('set', 'add', 'add nothing', 'subtract'):
        expected = {'set': 1, 'add': amount + 1, 'add nothing': amount, 'subtract': amount - 1}[write]
        assert value_at(record, found.program, Key(occurrence, ('size',)), horizon) == expected
    elif write == 'define':
        # `seen` holds 5 L from the stage on, so the formula reads 1 L/h and freezes there.
        assert value_at(record, found.program, Key(occurrence, ('rate',)), horizon) == 1
    else:
        moves = [entry for entry in record.entries('move') if entry.owner.startswith('crew.watch')]
        moved = {'move in': 1.0, 'move out': 1.0, 'move nothing': 0.0}[write]
        assert [(entry.t, entry.detail('amount')) for entry in moves] == [(writes, moved)]
        # Each repair moves what its batch holds back as it finishes: the water gains its amount,
        # whatever the watch moved in or out before.
        assert value_at(record, found.program, 'crew.water', horizon) == 10 + 3 + (0 if second is None else 7)


# --- flows ------------------------------------------------------------------------------------------

FLOWS = """
    scenario "Frozen"
        horizon 6 h
    crew:
        water: L = WATER in [0,]
        go: bool = true
        TAP
        repair = event():
            batch: L = BATCH
            after 2 h:
                FINISH
        watch = event():
            job = this.repair.occurrences.at(t)
            flow pipe: ENDS
                SETTINGS
            after 3.5 h when this.go:
                STAGE
            after 1 h
        later = event():
            after 3 h:
                this.watch.start()
        tick = event():
            after 2.5 h
    crew.repair.start()
    crew.tick.start()
    STARTS
    """
INTO, OUT_OF = 'this.water -> job.batch', 'job.batch -> this.water'
SWITCH = 'formula(1 L/h if t >= 3 h else 0 L/h)'
TAP = f'flow tap: SOURCE -> this.water\n            request = {SWITCH}\n            capacity = {SWITCH}'

# Each case: (ends, settings, and the parts of the model that differ from the plain one: a batch of
# 0 L in [0,] that the repair moves back, 10 L of water, no tap, no stage, the watch started at 0 h).
CASES = {
    # A flow that carries its rate when the repair finishes at 2 h.
    'into, at the finish': (INTO, 'request = 1 L/h', {}),
    'out of, at the finish': (OUT_OF, 'request = 1 L/h', {'BATCH': '0 L', 'FINISH': 'batch = 0 L'}),
    # A connected flow at zero rate writes nothing.
    'out of the empty store': (OUT_OF, 'request = 1 L/h', {}),
    'into, with no request': (INTO, 'request = 0 L/h', {}),
    'into, closed': (INTO, 'request = 1 L/h\n                capacity = 0 L/h', {}),
    'joins later at zero rate': (INTO, 'request = 0 L/h', {'STARTS': 'crew.later.start()'}),
    # A flow whose rate becomes nonzero after the finish: a stage at 3.5 h, the others at 3 h,
    # between moments but for the start of a later watch.
    'a stage opens it': (INTO, 'request = 0 L/h', {'STAGE': 'pipe.request = 1 L/h'}),
    'the time opens it': (INTO, f'request = {SWITCH}', {}),
    'its store fills': (INTO, 'request = 1 L/h\n                capacity = 1 L/h', {'WATER': '0 L', 'TAP': TAP}),
    'it rises with the water': (
        INTO,
        'request = formula(this.water / 10 h)\n                capacity = formula(this.water / 10 h)',
        {'WATER': '0 L', 'TAP': TAP},
    ),
    'joins later with a rate': (INTO, 'request = 1 L/h', {'STARTS': 'crew.later.start()'}),
}
# The time at which each case fails, or None where the run goes on.
FAILS = {
    'into, at the finish': 2,
    'out of, at the finish': 2,
    'a stage opens it': 3.5,
    'the time opens it': 3,
    'its store fills': 3,
    'it rises with the water': 3,
    'joins later with a rate': 3,
}
# The case whose rate rises from zero, and the cases that the oracle does not cover (a request that
# reads a store while the store moves).
RISING = UNCOVERED = {'it rises with the water'}


def flow_model(case, **changes):
    """The model of a case (`CASES`), with `changes` to its parts."""
    ends, settings, parts = CASES[case]
    text = FLOWS.replace('ENDS', ends).replace('SETTINGS', settings)
    plain = {
        'WATER': '10 L',
        'BATCH': '0 L in [0,]',
        'FINISH': 'move batch from batch to this.water',
        'TAP': '',
        'STAGE': 'this.go = true',
        'STARTS': 'crew.watch.start()',
    }
    for part, written in {**plain, **parts, **changes}.items():
        text = text.replace(part, written)
    return compiled(text)


def carries(case):
    """A pattern of the failure of a case: the flow carries 1 L/h into or out of the batch, or, as
    it rises from zero, what it carries once it is beyond its tolerance."""
    way = 'out of' if CASES[case][0] == OUT_OF else 'into'
    rate = r'[0-9.e+-]+' if case in RISING else '1'
    return rf'the flow crew\.watch#0\.pipe carries {rate} L/h {way} crew\.repair#0\.batch at t = '


@pytest.mark.parametrize('case', sorted(CASES))
def test_a_flow_that_carries_a_rate_at_a_store_of_a_finished_occurrence_fails_then_and_one_at_zero_goes_on(
    case,
):
    found = flow_model(case)
    record = run(found.program, found.configuration)
    when = FAILS.get(case)
    if when is None:
        assert record.failure is None, message(record)
        # Nothing moved: the water and the batch hold what they held.
        water = value_at(record, found.program, 'crew.water', 6)
        batch = value_at(record, found.program, Key('crew.repair#0', ('batch',)), 6)
        assert (water, batch) == (10, 0)
        assert oracle(found) is None
        return
    assert record.failure is not None, case
    # A rate that rises from zero is nonzero beyond its tolerance within the crossing tolerance.
    assert record.failure.t == pytest.approx(when, abs=1e-8)
    text = message(record)
    assert re.search(carries(case), text) and FROZEN.format('crew.repair#0') in text
    if case in UNCOVERED:
        with pytest.raises(NotCovered):
            oracle(found)
        return
    (t, said) = oracle(found)
    assert t == when and 'crew.repair#0.batch' in said and FROZEN.format('crew.repair#0') in said


def test_a_flow_that_joins_a_finished_occurrences_store_with_a_rate_fails_at_the_settling_of_its_start():
    """The watch starts at 3 h from the later event's stage, after the repair finished at 2 h, and
    saves it: its pipe fills the frozen batch from the settling of that round. The stage that
    started it committed (a start writes nothing to the batch): the run fails at 3 h."""
    found = flow_model('joins later with a rate')
    record = run(found.program, found.configuration)
    assert record.failure.t == 3
    assert [entry.t for entry in record.entries('start') if entry.owner.startswith('crew.watch')] == [3]


def test_a_store_that_another_occurrences_flow_filled_is_retired_as_its_own():
    """The watch's pipe brings 1 L into the repair's batch in its hour; the repair finishes at 2 h
    without moving it: it cannot finish, and the failure names the store and the litre."""
    found = compiled(
        """
        scenario "Frozen"
            horizon 6 h
        crew:
            water: L = 10 L in [0,]
            repair = event():
                batch: L = 0 L in [0,]
                after 2 h:
                    this.water = this.water
            watch = event():
                job = this.repair.occurrences.at(t)
                flow pipe: this.water -> job.batch
                    request = 1 L/h
                after 1 h
        crew.repair.start()
        crew.watch.start()
        """
    )
    record = run(found.program, found.configuration)
    assert record.failure is not None and record.failure.t == 2
    assert 'crew.repair#0 cannot finish at t = 2 h: its store crew.repair#0.batch still holds 1 L' in (
        message(record)
    )


# --- with a stop, an edit, a fresh process and a shorter run ---------------------------------------

GUARDED = """
    scenario "Frozen"
        horizon 6 h
    crew:
        go: bool = GO
        seen: L = 0 L
        water: L = 10 L in [0,]
        repair = event(amount: L):
            size: L = amount
            batch: L = 0 L in [0,]
            after 1 h
        watch = event():
            job = this.repair.occurrences.at(t)
            flow pipe: this.water -> job.batch
                request = 0 L/h
            after 3 h when this.go:
                this.seen = 5 L
                WRITE
            after 1 h
    crew.repair.start(3 L)
    crew.watch.start()
    """
STAGE = Breakpoint('crew.watch.step[0]')
# A write by a statement, and one by a flow that the stage opens.
GUARDED_WRITES = {
    'statement': (
        'job.size = 1 L',
        'crew.watch.step[0].do[1]: crew.repair#0.size belongs to the finished occurrence crew.repair#0, '
        'which is frozen',
    ),
    'flow': (
        'pipe.request = 1 L/h',
        'the flow crew.watch#0.pipe carries 1 L/h into crew.repair#0.batch at t = 3 h: crew.repair#0.batch '
        'belongs to the finished occurrence crew.repair#0, which is frozen',
    ),
}


def guarded(go, write):
    return compiled(GUARDED.replace('GO', go).replace('WRITE', GUARDED_WRITES[write][0]))


FRESH = """
import sys
from napkin.engine.timeline import resume
from napkin.program.artifact import load
from napkin.program.checkpoint import encode, loads

program = load(sys.argv[1]).program
with open(sys.argv[2], 'rb') as file:
    print(encode(resume(program, loads(file.read()))))
"""


def in_a_fresh_process(program, checkpoint, folder):
    """The record that a fresh process gives when it resumes a checkpoint of a run of `program`."""
    Artifact(program).save(folder / 'program')
    (folder / 'stop.checkpoint').write_bytes(dumps(checkpoint))
    done = subprocess.run(
        [sys.executable, '-c', FRESH, str(folder / 'program'), str(folder / 'stop.checkpoint')],
        cwd=ROOT,
        env={**os.environ, 'PYTHONHASHSEED': '4321', 'NAPKIN_STORE': 'off'},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return decode(done.stdout.strip())


@pytest.mark.parametrize('write', sorted(GUARDED_WRITES))
def test_a_run_stopped_before_the_write_fails_by_name_when_it_resumes_three_ways(write, tmp_path):
    found = guarded('true', write)
    straight = run(found.program, found.configuration)
    assert straight.failure.t == 3 and GUARDED_WRITES[write][1] in message(straight)
    made = Run(Plan.of(found.program, found.configuration), (STAGE,))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 3
    # An edit of the finished repair's value is refused by name, and changes nothing.
    with pytest.raises(CheckpointError, match=r'finished occurrence crew\.repair#0, which is frozen'):
        made.edit(Key('crew.repair#0', ('size',)), 2.0)
    assert in_a_fresh_process(found.program, stopped, tmp_path) == straight
    assert made.resume() == straight


@pytest.mark.parametrize('write', sorted(GUARDED_WRITES))
def test_an_edit_at_a_stop_that_enables_the_write_gives_the_failure_three_ways(write, tmp_path):
    """Unedited, the guard is false and the run finishes; edited to true at the stop before the
    guard is read, the resumed run fails at 3 h by name, in place and in a fresh process."""
    found = guarded('false', write)
    assert run(found.program, found.configuration).failure is None
    made = Run(Plan.of(found.program, found.configuration), (STAGE,))
    assert isinstance(made.run(), Checkpoint)
    edited = made.edit(Key('crew', ('go',)), True)
    fresh = in_a_fresh_process(found.program, edited, tmp_path)
    resumed = made.resume()
    assert resumed.failure.t == 3 and GUARDED_WRITES[write][1] in message(resumed)
    assert fresh == resumed


@pytest.mark.parametrize('case', ['the time opens it', 'it rises with the water'])
def test_a_flow_opened_between_moments_fails_at_its_time_after_a_resume_three_ways(case, tmp_path):
    """Stopped at 2.5 h, after the repair finished and before the pipe's rate leaves zero at 3 h, a
    resumed run fails as the straight run does, in place and in a fresh process: what the stopped
    run held of the finished store's flows is what a restored run finds."""
    found = flow_model(case)
    straight = run(found.program, found.configuration)
    assert straight.failure.t == pytest.approx(3, abs=1e-8) and re.search(carries(case), message(straight))
    made = Run(Plan.of(found.program, found.configuration), (Breakpoint('crew.tick.step[0]'),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 2.5
    assert in_a_fresh_process(found.program, stopped, tmp_path) == straight
    assert made.resume() == straight


@pytest.mark.parametrize('write', sorted(GUARDED_WRITES))
def test_a_shorter_run_finishes_and_is_the_failed_runs_record_cut_to_its_horizon(write):
    """To 2.5 h, before the write at 3 h, the run finishes; the failed run's record cut to 2.5 h, as
    the run store serves it, reads as that run at every time."""
    found = guarded('true', write)
    failed = run(found.program, found.configuration)
    shorter = Request(2.5)
    fresh = run(found.program, replace(found.configuration, request=shorter))
    assert fresh.failure is None
    cut = store.served(failed, shorter)
    assert cut.failure is None
    keys = ['crew.seen', Key('crew.repair#0', ('size',)), Key('crew.repair#0', ('batch',))]
    times = [0, 1, 2, 2.5]
    assert [r.values for r in read(cut, found.program, keys, times)] == [
        r.values for r in read(fresh, found.program, keys, times)
    ]


LINKED = """
    scenario "Frozen"
        horizon 6 h
    Crew:
        partner: Crew
        size: L = 0 L
        repair = event(amount: L):
            size: L = amount
            after 1 h
        watch = event():
            job = this.partner.repair.occurrences.at(t)
            after WHEN h:
                job.size = 1 L
    north: Crew
        partner = south
    south: Crew
        partner = north
    south.repair.start(3 L)
    north.watch.start()
    """


@pytest.mark.parametrize('when', [0.5, 2])
def test_a_reference_through_a_link_to_another_members_occurrence_is_frozen_too(when):
    """North's watch saves south's repair, which takes 1 h: at 0.5 h its write is made; at 2 h it
    fails, naming south's occurrence."""
    found = compiled(LINKED.replace('WHEN', str(when)))
    record = run(found.program, found.configuration)
    if when < 1:
        assert record.failure is None, message(record)
        assert value_at(record, found.program, Key('south.repair#0', ('size',)), 6) == 1
    else:
        assert record.failure is not None and record.failure.t == 2
        assert 'south.repair#0.size belongs to the finished occurrence south.repair#0, which is frozen' in (
            message(record)
        )
