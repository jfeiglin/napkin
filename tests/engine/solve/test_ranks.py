"""Every rank of the selection order, the final distance included (the readiness audit of `8b3a01a`,
row 06; `solve.Answer.admits`): an answer that takes the place of the solver's is no worse on any rank,
the distance to the targets included, each to its tolerance.

The distance of a stage, the flows and then the other unknowns, is the spec's ("Final targets for
flows and other unknowns"): the sum of the squared deviations of its coordinates from their targets,
each over its reference scale. The tests measure it from the problem's arrays alone.

1. The audit's case and its variants, by hand: the answer (1, 0) of two pipes that carry 1 between
   them, the first asking 1 and the second idle, is not given away for (0, 1), which moves the whole
   delivery onto the idle pipe; nor is an answer whose flows are the solver's and whose other
   unknown is farther from its reference.
2. On random problems of the library, a feasible alternative that is equal on every earlier rank and
   farther from the targets is never admitted: the same problem solved with other targets, since no
   earlier rank reads a target (hard rows, objectives and fair levels read none). The answer itself,
   and a rounding of it by a few units of roundoff, are admitted.
3. On the random solver programs of `test_random_solvers`, in litres and at 1e-7 of them, at every
   solve: the published answer's distance of each stage is the solver's to the precision of its
   coordinates, and an alternative made the same way is never admitted.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest
import scipy.sparse as sp

from napkin.engine import run
from napkin.engine.solve import FLOW, OTHER, Problem, SolveFailure, Solver
from napkin.engine.timeline import declared
from napkin.program.config import Configuration, Request
from tests.engine.solve.test_random import library, tiny
from tests.engine.test_random_solvers import HORIZON, program

PRECISION = 1e-6  # the end checks hold a coordinate to this times (1 + its size), over its scale


def distance(arrays, x, kind):
    """The distance of the stage `kind` (FLOW or OTHER) of an answer `x` in author units: the sum of
    the squared deviations from the targets, each over its reference scale."""
    stage = arrays.kind == kind
    return float((((x - arrays.target) / arrays.scale)[stage] ** 2).sum())


def precision(arrays, x, kind):
    """How far a rounding of `x` within the precision of the end checks can move the root of the
    distance of a stage: the length of the vector of PRECISION * (1 + |x / scale|)."""
    stage = arrays.kind == kind
    return float(np.sqrt(((PRECISION * (1 + np.abs(x / arrays.scale)))[stage] ** 2).sum()))


def farther(arrays, x, y):
    """Whether `y` is clearly farther from the targets than `x` on a stage on which they are not
    otherwise apart: on the flows, or with the same distance of the flows, on the other unknowns, by a
    thousand times the precision of the coordinates."""
    for kind in (FLOW, OTHER):
        near, far = np.sqrt(distance(arrays, x, kind)), np.sqrt(distance(arrays, y, kind))
        margin = 1000 * precision(arrays, x, kind) + 1e-3 * near
        if far > near + margin:
            return True
        if far < near - margin:
            return False
    return False


def retargeted(arrays, target):
    """The problem of `arrays` with other targets: the same unknowns, positive parts, rows,
    objectives and claims, which no earlier rank of the selection order reads."""
    p = Problem()
    blocks = {int(parts[0]): (parts, matrix, constants) for parts, matrix, constants in arrays.positive}
    j = 0
    while j < arrays.n:
        if j in blocks:
            parts, matrix, constants = blocks[j]
            keys = [arrays.keys[k] for k in parts.tolist()]
            p.positive_parts(keys, sp.csr_array(matrix)[:, :j], constants, arrays.scale[parts])
            j += len(parts)
            continue
        p.unknown(
            arrays.keys[j], arrays.lower[j], arrays.upper[j], int(arrays.kind[j]), target[j], arrays.scale[j]
        )
        j += 1
    plain = [
        i
        for i, key in enumerate(arrays.row_keys)
        if not (isinstance(key, tuple) and key[:1] == ('positive part',))
    ]
    if plain:
        p.rows(
            [arrays.row_keys[i] for i in plain],
            arrays.A[plain],
            arrays.row_lower[plain],
            arrays.row_upper[plain],
        )
    for columns, values in arrays.objectives:
        p.minimize(dict(zip(np.asarray(columns).tolist(), np.asarray(values).tolist())))
    F = sp.csr_array(arrays.F)
    for i in range(F.shape[0]):
        terms = F.indices[F.indptr[i] : F.indptr[i + 1]].tolist()
        p.claim(
            dict(zip(terms, F.data[F.indptr[i] : F.indptr[i + 1]].tolist())),
            arrays.request[i],
            arrays.tier[i],
        )
    return p


def targets(rng, arrays, answer):
    """Other targets for the flows and the other unknowns: a point of each finite box, or a step of up
    to twice the answer's size from it."""
    lower, upper = arrays.lower, arrays.upper
    size = 1.0 + np.abs(answer)
    found = np.where(
        np.isfinite(lower) & np.isfinite(upper),
        lower + rng.random(arrays.n) * (upper - lower),
        answer + (rng.random(arrays.n) * 4 - 2) * size,
    )
    return np.where(arrays.kind == FLOW, found, np.where(arrays.kind == OTHER, found, arrays.target))


def alternatives(rng, arrays, answer, count=3):
    """Answers of the problem of `arrays` with other targets: feasible, and equal to the solver's on
    every rank before the distance."""
    found = []
    for _ in range(count):
        try:
            found.append(Solver().solve(retargeted(arrays, targets(rng, arrays, answer))).x)
        except SolveFailure:  # an alternative that the library cannot give is no alternative
            continue
    return found


# ---- 1. by hand ---------------------------------------------------------------------------------------


def two_pipes(scale=1.0):
    """Two pipes in [0, 2] that carry 1 between them (`a + b == 1`); `a` asks 1, `b` is idle."""
    problem = Problem()
    a = problem.unknown('a', 0, 2 * scale, target=1.0 * scale, scale=scale)
    b = problem.unknown('b', 0, 2 * scale, target=0.0, scale=scale)
    problem.equal('books', {a: 1.0, b: 1.0}, 1.0 * scale)
    return problem


@pytest.mark.parametrize('scale', [1.0, 1e-7, 1e4])
def test_a_change_that_moves_the_delivery_onto_the_idle_pipe_is_not_admitted(scale):
    """The audit's case: the solver's answer is (1, 0) (by hand: the nearest point of a + b = 1 to the
    targets (1, 0)); (0, 1) meets every row and bound and is equal on every earlier rank (there is
    none), and it is farther from the targets by a distance of 2, so it does not take the answer's
    place; nor does any split of the delivery that moves a tenth of it. The answer itself is admitted. Even a
    rounding by a millionth of its precision must preserve the exactly idle flow."""
    answer = Solver().solve(two_pipes(scale))
    assert answer.x == pytest.approx([scale, 0.0], abs=1e-9 * scale)
    for share in (1.0, 0.5, 0.1):
        assert not answer.admits(np.array([1 - share, share]) * scale), share
    assert answer.admits(answer.x)
    assert not answer.admits(answer.x + np.array([-1, 1]) * 1e-12 * scale)


def test_the_other_unknowns_are_a_rank_after_the_flows():
    """A pipe that carries 1 and a level that a row ties to nothing else, with the reference 3 in
    [0, 10]: the solver gives the pipe 1 and the level 3; the same pipe with the level at 7 is equal
    on the flows and farther on the other unknowns, so it is not admitted."""
    problem = Problem()
    pipe = problem.unknown('pipe', 0, 2, target=1.0)
    level = problem.unknown('level', 0, 10, kind=OTHER, target=3.0, scale=1.0)
    problem.at_most('room', {level: 1.0}, 10.0)
    problem.equal('books', {pipe: 1.0}, 1.0)
    answer = Solver().solve(problem)
    assert answer['pipe'] == pytest.approx(1) and answer['level'] == pytest.approx(3)
    assert not answer.admits(np.array([1.0, 7.0]))
    assert answer.admits(np.array([1.0, 3.0 + 1e-12]))


# ---- 2. random problems of the library ---------------------------------------------------------------------


def none_farther(seed):
    """Check a random problem of the library (`test_random.tiny`); gives how many of its
    alternatives were farther from the targets."""
    rng = np.random.default_rng(seed)
    spec = tiny(rng)
    answer = Solver().solve(library(spec))
    arrays = library(spec).arrays()
    assert answer.admits(answer.x)
    # A rounding of the flows and the other unknowns by a few units of roundoff, its positive parts
    # their values at it, as any change of an answer gives them (`declared.polished`).
    moved = (rng.random(arrays.n) - 0.5) * 4e-16 * (1 + np.abs(answer.x)) * (arrays.kind != 0)
    candidate = arrays.positive_parts(np.clip(answer.x + moved, arrays.lower, arrays.upper))
    idle = (arrays.kind == FLOW) & (answer.x == 0)
    assert answer.admits(candidate) == np.all(candidate[idle] == 0)

    found = 0
    for y in alternatives(rng, arrays, answer.x, count=4):
        if farther(arrays, answer.x, y):
            found += 1
            assert not answer.admits(y), (seed, answer.x, y)
    return found


@pytest.mark.parametrize('seed', range(60))
def test_no_alternative_farther_from_the_targets_takes_the_answers_place(seed):
    none_farther(seed)


def test_the_alternatives_are_farther_on_most_problems():
    """The rule above is not vacuous: most random problems have an alternative that is farther."""
    assert sum(none_farther(seed) > 0 for seed in range(20)) >= 10


# ---- 3. the random solver programs of the engine --------------------------------------------------------------


def solves(monkeypatch, source):
    """Each solve of a run of `source` to the horizon: (its arrays, the solver's answer, the published
    answer)."""
    found = []
    publish = declared.published

    def spy(arrays, answer):
        made = publish(arrays, answer)
        found.append((arrays, answer, np.array(made)))
        return made

    monkeypatch.setattr(declared, 'published', spy)
    run(source, Configuration(Request(HORIZON)))
    return found


def every_rank(monkeypatch, seed, size):
    source, _ = program(seed, size=size)
    rng = np.random.default_rng(seed)
    for arrays, answer, made in solves(monkeypatch, source):
        for kind in (FLOW, OTHER):
            near, published = (np.sqrt(distance(arrays, x, kind)) for x in (answer.x, made))
            assert abs(published - near) <= precision(arrays, answer.x, kind), (
                seed,
                size,
                kind,
                near,
                published,
            )
        for y in alternatives(rng, arrays, answer.x, count=2):
            if farther(arrays, answer.x, y):
                assert not answer.admits(y), (seed, size, answer.x, y)


@pytest.mark.parametrize('seed', range(40))
@pytest.mark.parametrize('size', [1, Fraction(1, 10**7)], ids=['litres', 'tiny'])
def test_the_published_answer_keeps_the_distance_and_no_farther_answer_is_admitted(monkeypatch, seed, size):
    every_rank(monkeypatch, seed, size)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(40, 400))
@pytest.mark.parametrize('size', [1, Fraction(1, 10**7)], ids=['litres', 'tiny'])
def test_more_published_answers_keep_the_distance(monkeypatch, seed, size):
    every_rank(monkeypatch, seed, size)
