"""The front end's chains of 5,000 links, run with Python's recursion limit at 400 (re-audit 15).

Agent F's rule test (`tests/model/test_deep_chains.py`) compiles a model whose values form a chain of
5,000 links in each form that the front end resolves: formulas of the top level and of an entity,
links between entities and between the rows of a table, keyed reads, collection values, stored values
whose initializers follow their dependencies, and an assertion over the chain. The engine's rule: the
same models run, their records are read, and a trigger on the head of each chain is read, with the
limit at 400; the head's value is the chain's closed form (a litre a link). Each model is compiled
at Python's own limit (the front end's rule is F's), then made into a plan, run and read under 400.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from tests.model.test_deep_chains import FORMS, LINKS
from tests.program.examples import UNITS

LIMIT = 400

# The head of each chain, its value at 1 h (in L, or a count), and its trigger's condition.
HEADS = {
    'top': ('v0', LINKS, 'v0 >= 1 L'),
    'asserted': ('v0', LINKS, 'v0 >= 1 L'),
    'entity': ('plant.v0', LINKS, 'plant.v0 >= 1 L'),
    'linked': ('e0.v', LINKS, 'e0.v >= 1 L'),
    'stored': ('v0', LINKS, 'v0 >= 1 L'),
    'keyed': ('m0.total', LINKS, 'm0.total >= 1 L'),
    'collections': ('total', 2, 'total >= 1'),
    'table': ('places.p0.total', LINKS + 1, 'places.p0.total >= 1 L'),
}
WATCH = """
watch:
    rung: h = -1 h
    ring = event():
        when CONDITION:
            this.ring.start()
            reset when false
        after 1 h:
            this.rung = t
"""


@contextmanager
def shallow(limit=LIMIT):
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(limit)
    try:
        yield
    finally:
        sys.setrecursionlimit(before)


@pytest.mark.deep
@pytest.mark.parametrize('form', sorted(HEADS))
def test_a_chain_of_five_thousand_links_runs_and_reads_with_the_recursion_limit_at_400(form):
    head, expected, condition = HEADS[form]
    made = FORMS[form](LINKS)
    text, tables = made if isinstance(made, tuple) else (made, None)
    found = compile_text(text + WATCH.replace('CONDITION', condition), UNITS, tables=tables)
    with shallow():
        record = Run(Plan.of(found.program, found.configuration)).run()
        assert record.failure is None, record.failure.detail('message')
        values = [reading.values[0] for reading in read(record, found.program, [head, 'watch.rung'], [1.5])]
    # The trigger holds at the start, so its event starts then and writes at 1 h.
    assert values == [pytest.approx(expected), 1]
