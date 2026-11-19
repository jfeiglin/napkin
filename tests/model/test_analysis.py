"""Facts that follow from a model's text: which formulas move in a run, and the bound that an input
gives a store (spec, "Formulas and the values a caller can read").

A formula reads inputs, stores and other formulas, in any order of the file. It is fixed for the run
when each name that it reads is an input or such a formula: an assertion that reads it is then checked
once (`semantic.DeclaredAssert.fixed`), and its value is the value of its definition. A store's range
can read an input; the store is held at the value that the run's configuration gives the input. A
bound that cannot be a number stops the run with a failure that names its expression.

The classes of the triggers of the old analysis are in `tests/engine/test_trigger_classes.py`, the
never-falls proof in `tests/program/test_proofs.py`, and a crossing of a store whose rate moves in
`tests/engine/test_monotone_crossing.py`.
"""

from __future__ import annotations

import random

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine import read, run
from napkin.model.compile import compile_text
from tests.program.examples import UNITS


def chains(rng, count):
    """Formulas `f0` to `f{count-1}`, each a sum of some names with a number: of the inputs `a` and
    `b`, of the store `q`, which a flow fills, and of formulas before it. They are written in a random
    order, so a formula can come before one that it reads."""
    formulas = {}
    for k in range(count):
        names = rng.sample(['a', 'b', 'q', *(f'f{j}' for j in range(k))], rng.randint(1, min(3, k + 3)))
        formulas[f'f{k}'] = (names, float(rng.randint(1, 9)))
    written = list(formulas)
    rng.shuffle(written)
    return {name: formulas[name] for name in written}


def by_passes(formulas, values):
    """The formulas that do not move, by the definition: a formula is one when each name that it
    reads is an input or such a formula. The value is the sum that the formula writes."""
    found = dict(values)
    changed = True
    while changed:
        changed = False
        for name, (parts, number) in formulas.items():
            if name not in found and all(part in found for part in parts):
                found[name] = sum(found[part] for part in parts) + number
                changed = True
    return found


@pytest.mark.parametrize('seed', range(12))
def test_the_formulas_that_do_not_move_are_those_of_the_definition_in_any_order(seed):
    """Each formula is fixed or not as the definition says, whatever the order of the file, and a
    fixed formula has the value of its definition."""
    rng = random.Random(seed)
    formulas = chains(rng, 14)
    values = {'a': 2.0, 'b': 0.5}
    rows = ['scenario "Formulas"', '    horizon 1 h', 's:', '    input a = 2.0', '    input b = 0.5']
    rows += ['    q = 1.0', '    flow grow: SOURCE -> this.q', '        request = 0.5 / 1 h']
    for name, (parts, number) in formulas.items():
        rows.append(f'    {name} = formula({" + ".join(f"this.{part}" for part in parts)} + {number!r})')
    rows += [f'assert s.{name} > -1000' for name in formulas]
    model = compile_text('\n'.join(rows) + '\n', UNITS)
    expected = by_passes(formulas, values)
    fixed = dict(zip(formulas, (item.fixed for item in model.declared.asserts)))
    assert fixed == {name: name in expected for name in formulas}
    # Each case has both kinds.
    assert any(fixed.values()) and not all(fixed.values())
    names = [name for name in formulas if fixed[name]]
    record = run(model.program, model.configuration)
    found = read(record, model.program, [f's.{name}' for name in names], [0, 1])
    assert [reading.values for reading in found] == [pytest.approx((expected[name],) * 2) for name in names]


BOUNDED = """\
scenario "Queue"
    horizon 20 h

queue:
    input cap: L = 40 L in [10 L, 80 L]
    level: L = 30 L in [0 L, {upper}]
    flow fill: SOURCE -> this.level
        request = 2 L/h
"""


def queue(upper='this.cap', edits=None):
    """(the record of a run of the queue whose level's upper bound is `upper`, under the edits
    `edits`; the compiled model)."""
    model = compile_text(BOUNDED.format(upper=upper), UNITS)
    configuration = model.configuration
    if edits is not None:
        document = {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **edits}
        configuration = model.configure(edits=document)
    return run(model.program, configuration), model


def test_a_bound_that_reads_an_input_holds_the_store_at_the_value_of_the_run():
    """The level rises 2 L an hour from 30 L and is held at its upper bound: min(30 + 2 t, cap)."""
    times = [3, 10, 20]
    for edits, cap in ((None, 40), ({'set': {'queue.cap': 55}}, 55)):
        record, model = queue(edits=edits)
        assert record.failure is None
        (level,) = read(record, model.program, ['queue.level'], times)
        assert level.values == pytest.approx([min(30 + 2 * t, cap) for t in times], rel=1e-9)


def test_a_bound_that_cannot_be_a_number_stops_the_run_and_names_its_expression():
    record, _ = queue(upper='1 L * (this.cap / (this.cap - this.cap))')
    assert record.failure is not None
    message = record.failure.detail('message')
    assert 'queue.cap - queue.cap' in message and 'division by zero' in message
