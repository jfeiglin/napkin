"""The engine's side of two front-end fixes of the re-audit (agent D's notes for B).

- **A reference to an occurrence** (re-audit 14; spec, "A finished occurrence is a stable record"):
  a local that holds one names, from the entry of its own occurrence on, the occurrence that its
  initializer names then, whatever starts later; a read through it reads that occurrence's fields,
  frozen once it finishes. Before any start of its event, the entry fails and names the reference.
- **A fixed key** (re-audit 15): a constant key over the natural keys of a literal selects one entry
  when the plan is made, so a value that the other entries read is no cycle. On random literals and
  keys, the reading member's value is the selected entry's, as a sum written by hand; a key that
  selects the reader itself is the one cycle.
"""

from __future__ import annotations

import random
import textwrap

import pytest

from napkin.engine.timeline import read, run
from napkin.engine.timeline.plan import Outside
from napkin.model.compile import compile_text
from napkin.program.build import Builder, formula, literal, named, this, value
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def model(text):
    return compile_text(textwrap.dedent(text), UNITS)


def test_a_reference_reads_the_frozen_value_of_its_occurrence_after_it_finishes():
    """The check enters at 0 h and saves the newest repair (3 L, which takes 2 h, its `left` reading
    its amount less 1 L); at 4 h, after it finished and a later repair of 7 L started at 1 h, it
    reads 2 L through the reference."""
    found = model(
        """
        scenario "Frozen"
            horizon 5 h
        crew:
            seen: L = 0 L
            repair = event(amount: L):
                left = formula(amount - 1 L)
                after 2 h
            check = event():
                job = this.repair.occurrences.at(t)
                after 4 h:
                    this.seen = job.left
            again = event():
                after 1 h:
                    this.repair.start(7 L)
        crew.repair.start(3 L)
        crew.check.start()
        crew.again.start()
        """
    )
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    (seen,) = read(record, found.program, ['crew.seen'], [5])
    assert seen.values == (2,)


def test_a_reference_before_any_start_of_its_event_fails_the_entry_by_name():
    found = model(
        """
        scenario "Early"
            horizon 2 h
        crew:
            seen: L = 0 L
            repair = event(amount: L):
                after 2 h
            check = event():
                job = this.repair.occurrences.at(t)
                after 1 h:
                    this.seen = job.amount
        crew.check.start()
        """
    )
    record = run(found.program, found.configuration)
    assert record.failure is not None and record.failure.t == 0
    assert 'no occurrence has started' in record.failure.detail('message')


@pytest.mark.parametrize('seed', range(30))
def test_a_constant_key_over_a_literal_reads_the_entry_that_it_selects(seed):
    """Members m0 ... m{n-1} with demands; the reader's total is its demand plus the total of the
    entry of a literal that a constant key selects (the greatest natural key at or below it). Each
    other member's total is its demand. A key that selects the reader is a cycle, and only then."""
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    demands = [rng.randint(1, 50) for _ in range(n)]
    reader = rng.randrange(n)
    chosen = sorted(rng.sample(range(n), rng.randint(1, n)))
    key = rng.choice([*chosen, *(c + 0.5 for c in chosen)])
    selected = max(c for c in chosen if c <= key)
    b = Builder(UNITS)
    node = b.template('Node', value('demand', '', 0), value('total', '', formula(this.demand)))
    for k in range(n):
        if k == reader:
            pick = literal(*[named(f'm{c}') for c in chosen]).at(key).total
            b.member(node, f'm{k}', demand=demands[k], total=formula(this.demand + pick))
        else:
            b.member(node, f'm{k}', demand=demands[k])
    program = b.finish()
    if selected == reader:
        with pytest.raises(Outside, match='reads itself'):
            run(program, Configuration(Request(1)))
        return
    record = run(program, Configuration(Request(1)))
    assert record.failure is None, record.failure.detail('message')
    (total,) = read(record, program, [f'm{reader}.total'], [1])
    assert total.values == (demands[reader] + demands[selected],)
