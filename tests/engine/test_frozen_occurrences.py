"""A finished occurrence is frozen (re-audit 14, `briefs/audit3.md` part E).

The rule (spec, "State owned by an invocation": "A finished occurrence is frozen, and a write to it
is an error"; D7, a finished occurrence is a stable record; G0, "Allow writes to live
occurrences"): every write to a field or a store of an occurrence after it finished fails the run by
name at that moment, whatever makes it, and the same write while the occurrence runs is made.

- **Statements.** `=`, `+=`, `-=` and `= formula(...)` on a field, and a `move` into or out of a
  store, through a reference saved at the entry, a reference copied from one, `.occurrences.at(t)`,
  which names the newest start then, or a reference to another member's occurrence through a link. The property runs each of them at random
  times before and after the finish, with a later start of the same event or none: the run fails at
  the time of the write, naming the value, the finished occurrence and the statement, and holds
  nothing of the stage that wrote (its write before that one included); before the finish the write
  is made, and its effect is the closed form worked here.
- **Flows.** A flow of another occurrence that meets one of its stores: present when it finishes,
  the run fails then; started after, the run fails when it starts. A flow is present at its ends
  for its owner's lifetime, whatever its rate ("A flow whose rate falls to zero stays connected for
  its owner's lifetime"), and a store of a finished occurrence can neither take nor give. A store
  that another occurrence's flow met is retired as the occurrence's own stores are ("Each
  occurrence-owned physical store must have zero residual inventory at normal completion").
- **Stops.** Stopped before the write and resumed, in place and in a fresh process, the run fails at
  the same time with the same message; an edit at the stop that enables the write gives that
  failure; an edit of the finished occurrence's value is refused (change 15: "a finished
  occurrence stays frozen").
- **A shorter run.** A run whose horizon comes before the write finishes, and the failed run's
  record cut to that horizon (`store.served`) is its record.
"""

from __future__ import annotations

import os
import random
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

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
ROOT = Path(__file__).resolve().parents[2]

# The writes of a stage, as (statement with REF for the reference, the field it writes).
WRITES = {
    'set': ('REF.size = 1 L', 'size'),
    'add': ('REF.size += 1 L', 'size'),
    'subtract': ('REF.size -= 1 L', 'size'),
    'define': ('REF.rate = formula(this.water / 10 h)', 'rate'),
    'move in': ('move 1 L from this.water to REF.batch', 'batch'),
    'move out': ('move 0 L from REF.batch to this.water', 'batch'),
}
REFERENCES = {'saved': 'job', 'copied': 'other', 'newest': 'this.repair.occurrences.at(t)'}


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def frozen_model(write, reference, repair, writes, second):
    """A crew whose repair of 3 L starts at 0 h and takes `repair` hours, ending with its batch moved
    back; a watch, started with it, writes 5 L to `seen` and then makes `write` through `reference`
    at `writes` h; `second`, the time of a second repair of 7 L, or None."""
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
                batch: L = 0 L in [0,]
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


@pytest.mark.parametrize('seed', range(40))
def test_a_write_to_an_occurrence_is_made_while_it_runs_and_fails_by_name_after_it_finished(seed):
    rng = random.Random(seed)
    write, reference = rng.choice(sorted(WRITES)), rng.choice(sorted(REFERENCES))
    # Halves and wholes apart, so that no write is due with a finish.
    repair, writes = rng.choice([1, 2, 3, 4]), rng.choice([0.5, 1.5, 2.5, 3.5, 4.5])
    second = rng.choice([None, 0.5, 1.5, 2.5])
    found, horizon = frozen_model(write, reference, repair, writes, second)
    record = run(found.program, found.configuration)
    number, running = target_of(reference, repair, writes, second)
    occurrence, field = f'crew.repair#{number}', WRITES[write][1]
    if not running:
        assert record.failure is not None and record.failure.t == writes
        assert (
            f'{occurrence}.{field} belongs to the finished occurrence {occurrence}, which is frozen'
            in message(record)
        )
        assert 'crew.watch.step[0].do[1]' in message(record)
        # The stage that writes is discarded whole: its write of 5 L before is not in the record.
        assert value_at(record, found.program, 'crew.seen', writes) == 0
        return
    assert record.failure is None, message(record)
    assert value_at(record, found.program, 'crew.seen', horizon) == 5
    amount = 3 if number == 0 else 7
    if write in ('set', 'add', 'subtract'):
        expected = {'set': 1, 'add': amount + 1, 'subtract': amount - 1}[write]
        assert value_at(record, found.program, Key(occurrence, ('size',)), horizon) == expected
    elif write == 'define':
        # The water stays at 10 L, so the formula reads 1 L/h from the write and freezes there.
        assert value_at(record, found.program, Key(occurrence, ('rate',)), horizon) == 1
    else:
        moves = [entry for entry in record.entries('move') if entry.owner.startswith('crew.watch')]
        assert [(entry.t, entry.detail('amount')) for entry in moves] == [
            (writes, 1.0 if write == 'move in' else 0.0)
        ]
        # The repair moves its batch back as it finishes.
        assert value_at(record, found.program, 'crew.water', horizon) == 10


FLOWS = """
    scenario "Frozen"
        horizon 6 h
    crew:
        water: L = 10 L in [0,]
        repair = event():
            batch: L = 0 L in [0,]
            after 2 h:
                FINISH
        watch = event():
            job = this.repair.occurrences.at(t)
            flow pipe: ENDS
                request = 1 L/h
            after WATCH h
        later = event():
            after 3 h:
                this.watch.start()
    crew.repair.start()
    STARTS
    """


def flows(ends, watch, starts='crew.watch.start()', finish='move batch from batch to this.water'):
    text = FLOWS.replace('ENDS', ends).replace('WATCH', str(watch)).replace('STARTS', starts)
    return compiled(text.replace('FINISH', finish))


@pytest.mark.parametrize('ends', ['this.water -> job.batch', 'job.batch -> this.water'])
def test_a_flow_present_at_a_store_of_an_occurrence_when_it_finishes_fails_the_run_then(ends):
    """The watch's pipe meets the repair's batch from 0 h; the repair moves its batch back and
    finishes at 2 h while the pipe, which lasts 4 h, is present: the run fails at 2 h."""
    found = flows(ends, 4)
    record = run(found.program, found.configuration)
    assert record.failure is not None and record.failure.t == 2
    text = message(record)
    assert 'crew.watch#0.pipe' in text and 'crew.repair#0.batch' in text
    assert 'finished occurrence crew.repair#0, which is frozen' in text


@pytest.mark.parametrize('ends', ['this.water -> job.batch', 'job.batch -> this.water'])
def test_a_flow_that_leaves_before_the_finish_leaves_the_store_as_it_was(ends):
    """The pipe lasts 1 h: into the batch, 1 L arrives and the repair moves it back at 2 h; out of
    the empty batch, nothing can go. The run finishes with 10 L in the water."""
    found = flows(ends, 1)
    record = run(found.program, found.configuration)
    assert record.failure is None, message(record)
    assert value_at(record, found.program, 'crew.water', 6) == 10


def test_a_flow_that_starts_at_a_store_of_a_finished_occurrence_fails_the_run_when_it_starts():
    """The watch starts at 3 h, after the repair finished at 2 h, and saves it: its pipe would fill
    the frozen batch. The run fails at 3 h, and the later stage that started it commits nothing."""
    found = flows('this.water -> job.batch', 2, starts='crew.later.start()')
    record = run(found.program, found.configuration)
    assert record.failure is not None and record.failure.t == 3
    text = message(record)
    assert 'crew.watch#0.pipe' in text and 'crew.repair#0.batch' in text and 'frozen' in text
    assert not record.entries('start', 'crew.watch')


def test_a_store_that_another_occurrences_flow_filled_is_retired_as_its_own():
    """The watch's pipe brings 1 L into the repair's batch in its hour; the repair finishes at 2 h
    without moving it: it cannot finish, and the failure names the store and the litre."""
    found = flows('this.water -> job.batch', 1, finish='this.water = this.water')
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
        repair = event(amount: L):
            size: L = amount
            after 1 h
        watch = event():
            job = this.repair.occurrences.at(t)
            after 3 h when this.go:
                this.seen = 5 L
                job.size = 1 L
    crew.repair.start(3 L)
    crew.watch.start()
    """
STAGE = Breakpoint('crew.watch.step[0]')
FAILURE = (
    'crew.watch.step[0].do[1]: crew.repair#0.size belongs to the finished occurrence crew.repair#0, '
    'which is frozen'
)

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


def test_a_run_stopped_before_the_write_fails_by_name_when_it_resumes_three_ways(tmp_path):
    found = compiled(GUARDED.replace('GO', 'true'))
    straight = run(found.program, found.configuration)
    assert straight.failure.t == 3 and FAILURE in message(straight)
    made = Run(Plan.of(found.program, found.configuration), (STAGE,))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 3
    # An edit of the finished repair's value is refused by name, and changes nothing.
    with pytest.raises(CheckpointError, match=r'finished occurrence crew\.repair#0, which is frozen'):
        made.edit(Key('crew.repair#0', ('size',)), 2.0)
    assert in_a_fresh_process(found.program, stopped, tmp_path) == straight
    assert made.resume() == straight


def test_an_edit_at_a_stop_that_enables_the_write_gives_the_failure_three_ways(tmp_path):
    """Unedited, the guard is false and the run finishes; edited to true at the stop before the
    guard is read, the resumed run fails at 3 h by name, in place and in a fresh process."""
    found = compiled(GUARDED.replace('GO', 'false'))
    assert run(found.program, found.configuration).failure is None
    made = Run(Plan.of(found.program, found.configuration), (STAGE,))
    assert isinstance(made.run(), Checkpoint)
    edited = made.edit(Key('crew', ('go',)), True)
    fresh = in_a_fresh_process(found.program, edited, tmp_path)
    resumed = made.resume()
    assert resumed.failure.t == 3 and FAILURE in message(resumed)
    assert fresh == resumed


def test_a_shorter_run_finishes_and_is_the_failed_runs_record_cut_to_its_horizon():
    """To 2.5 h, before the write at 3 h, the run finishes; the failed run's record cut to 2.5 h, as
    the run store serves it, reads as that run at every time."""
    found = compiled(GUARDED.replace('GO', 'true'))
    failed = run(found.program, found.configuration)
    shorter = Request(2.5)
    fresh = run(found.program, replace(found.configuration, request=shorter))
    assert fresh.failure is None
    cut = store.served(failed, shorter)
    assert cut.failure is None
    keys, times = ['crew.seen', Key('crew.repair#0', ('size',))], [0, 1, 2, 2.5]
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
