"""The timeline engine: the engine of every run (docs/engine.md).

It reads the hybrid core of a model (`napkin/model/hybrid.py`), and runs the families of a table
without writing them out; `engine/runtime.simulate` gives it the resolved run of a model with no
table (`trajectory`).

- `Plan.of(core)`: what follows from the structure alone (`plan.py`). One plan serves every run.
- `run(plan, values)`: one run to the horizon (`run.py`), as a `Result`.
- `batch(plan, samples)`: one run for each sample, each with its own status. Sample k of a batch is,
  bit for bit, the run of sample k alone: the samples share the plan and nothing of a run.
- `check(plan, values)`: the checking mode of D-65. It makes the run with the scoped reading of the
  rules and with the reading of every rule at every moment, and gives the differences of the two
  traces.
- `trajectory(resolved, library)`: the run of a resolved run of a model with no table, as the
  `Trajectory` that the reports, the studies and the tools read.

What it runs: quantities with rates and flows, with their bounds, allocation groups and flows that
move by one fraction; events with clocks, crossings and conditions on values that steps change;
`once`, `while`, windows and a delay; steps that set values, move amounts and name events; outcomes
with chances and conditions, drawn values and values of the past; statuses, checks of the state and
partitions; lists over the instances of a family in formulas, conditions, rates and outputs; links
between tables; a played run, with its picks, its pause at a decision and the decision that waits.
What it names as outside (`Outside`): a model with start-state options.

A space is in one of two tiers (`run.py`). When a run meets a state that the fast tier of a space
does not run, `run` makes the run again with that space in the general tier; a run that carries
derivatives has the things outside the tables in the fast tier.
"""

from __future__ import annotations

import hashlib
import pickle
from collections import OrderedDict
from dataclasses import dataclass

from ...core.errors import ExpressionError
from ...model import structure as typed
from ...model.ir import ModelError
from ..errors import SimulationError
from .plan import Outside, Plan
from .run import Result, Run

__all__ = [
    'Outside',
    'Plan',
    'Result',
    'Run',
    'Sample',
    'admit',
    'batch',
    'check',
    'flat_plan',
    'input_failures',
    'result',
    'run',
    'trajectory',
]


def run(plan, values=None, **options):
    """One run of a plan to its horizon. `values`: {input: a number in its unit, or one for each
    instance}. `options`: `settings` (the numerical settings), `reading` ('scoped' or 'every'),
    `directions` (the inputs by which the run carries derivatives), `adapter` (the solver), `luck`
    (the luck of a sample: {seed, sample}), `outcomes` (the given outcomes of the firings that go
    by chance, `Run`), and those of a played run: `play` ({control, picks}),
    `pause_at_decision`, `decision_events`, `settled_decisions`, `decision_resolver`, with the
    meaning that `engine/runtime.simulate` gives them."""
    if options.get('directions') and plan.fast() is not None:
        # The general tier carries no derivative: the things outside the tables go to the fast tier.
        plan = plan.fast()
    if options.get('decision_resolver') is not None:
        # A run that is made again asks each decision again: the resolver is asked once for each,
        # and the run that is made again gets the answer that the first one got.
        options = {**options, 'decision_resolver': _asked_once(options['decision_resolver'])}
    while True:
        try:
            return Run(plan, values, **options).run()
        except Outside as problem:
            # The run met a state that the fast tier of a space does not run: the run is made again
            # with that space in the general tier. The tier of a run follows from its own values alone.
            # A run that carries derivatives has no general tier: the state is named as it is.
            wider = None if options.get('directions') else plan.wider(problem.space)
            if wider is None:
                raise
            plan = wider


def _asked_once(resolver):
    answers = {}

    def resolve(decision, env, trace):
        key = decision['pick_index']
        if key not in answers:
            answers[key] = resolver(decision, env, trace)
        return answers[key]

    return resolve


def input_failures(plan, values=None):
    """The failing checks of the inputs of a run (an `assert` that reads only inputs and named
    states), for every instance of each family: what `analysis.values.input_check_failures` gives of
    a flat structure, with the flat name of the check of each instance. The model of the
    representatives has these checks for one row of each class only."""
    return Run(plan, values).input_failures()


def admit(core, run=None, values=None):
    """Refuse a run of a hybrid core whose inputs fail a blocking check for some row of a table, as
    the compiler refuses a run of a flat model (`model.compile.resolve_structure`): a ModelError with
    the check of each failing row. `run` names a run (default: each declared run of the model). A run
    of a model with a table is refused in the same way when it starts (`Run.admit`); this function
    serves a caller that asks before it runs anything."""
    for name in [run] if run is not None else list(core.model.runs):
        blocked = [
            item for item in input_failures(Plan.of(core, name, values), None) if item['severity'] == 'error'
        ]
        if blocked:
            raise ModelError([{**item, 'context': f'runs/{name}'} for item in blocked])


def trajectory(resolved, library, settings=None, **options):
    """The run of a resolved run of a model with no table, as the trajectory that
    `engine/runtime.simulate` gives of it. `options` are those of a played run (`play`, and how it
    stops at a decision), with the meaning that `simulate` gives them. The luck is that of the
    resolved run."""
    return result(resolved, library, settings, **options).trajectory()


def result(resolved, library, settings=None, **options):
    """The run of a resolved run of a model with no table, with its whole record: the result that
    `trajectory` reads. `options` are those of `trajectory`, and `outcomes`: the given outcomes of
    the firings that go by chance (`Run`), whose record is the `firings` of the result."""
    luck = typed.thawed(resolved.luck)
    try:
        plan = _plan(resolved, library)
        made = Run(
            plan,
            settings=settings,
            luck=luck,
            keep=True,
            inputs=resolved.values,
            resolved=resolved,
            **options,
        )
        return made.run()
    except Outside as problem:
        # A model that the compiler admits has no such part: the run stops, and names it.
        raise SimulationError(f'The engine does not run this part of the model: {problem}') from problem


# What a plan does not read of a resolved run: each run gives them itself.
OF_A_RUN = ('values', 'parameter_values', 'distributions', 'luck')
# What it reads of a run beside the parts of its structure: the other keys of a resolution.
OF_A_PLAN = tuple(
    key
    for key in (*typed.Resolved.ALWAYS, *typed.Resolved.NAMED, *typed.Resolved.SOMETIMES)
    if key not in OF_A_RUN
)
PLANS = 16
_plans = OrderedDict()
# The digest of each part of the last structures, by the part itself (`_digest`).
PARTS = 512
_digests = OrderedDict()


def _digest(part):
    """The digest of one part of a resolved run: a section of its structure, or its links. It is of
    the bytes that `pickle` writes of the typed parts: two different parts never have the same
    bytes. A part cannot change, and the runs of one structure share its parts, so the digest of a
    part is found once: it is kept by the part itself, which is held with it so that no other
    object can have its place in the memory."""
    kept = _digests.get(id(part))
    if kept is None:
        kept = _digests[id(part)] = (part, hashlib.blake2b(pickle.dumps(part), digest_size=20).digest())
        while len(_digests) > PARTS:
            _digests.popitem(last=False)
    else:
        _digests.move_to_end(id(part))
    return kept[1]


def _plan(resolved, library):
    """The plan of a resolved flat run. A plan follows from the structure alone, so the runs of one
    structure (each sample of a study, each edit of a number) share one: the last plans are kept
    by a digest of the typed parts of the structure, of what else a plan reads of the run and of
    the units. The first run of a structure pays the digest of each part, a few milliseconds; each
    next run reads the kept digests (`_digest`)."""
    try:
        parts = [_digest(getattr(resolved, section)) for section in typed.SECTIONS]
        parts.append(_digest(resolved.links))
        rest = (resolved.computed_order, [getattr(resolved, name) for name in OF_A_PLAN], library['units'])
        key = hashlib.blake2b(b''.join(parts) + pickle.dumps(rest), digest_size=20).digest()
    except (pickle.PicklingError, TypeError, AttributeError):
        return Plan.flat(resolved, library)
    plan = _plans.get(key)
    if plan is None:
        plan = _plans[key] = Plan.flat(resolved, library)
        while len(_plans) > PLANS:
            _plans.popitem(last=False)
    else:
        _plans.move_to_end(key)
    return plan


def flat_plan(resolved, library):
    """The plan of a resolved run of a model with no table. One plan serves the runs of one
    structure (`_plan`), so a run of it takes the values of its own resolved run:
    `run(plan, inputs=resolved.values, resolved=resolved)`."""
    return _plan(resolved, library)


@dataclass
class Sample:
    """One sample of a batch: 'finished' with its result, 'failed' with the error of its run, or
    'outside' with the part that this engine does not run."""

    status: str
    result: Result | None = None
    error: str | None = None


def batch(plan, samples, **options):
    """One run for each of `samples` (each a `values` of `run`), in their order. A sample that fails
    has its own status and changes no other sample."""
    found = []
    for values in samples:
        try:
            found.append(Sample('finished', run(plan, values, **options)))
        except Outside as problem:
            found.append(Sample('outside', error=str(problem)))
        except (SimulationError, ExpressionError) as problem:
            found.append(Sample('failed', error=str(problem)))
        except ModelError as problem:
            # The inputs of the sample fail a blocking check for a row of a table.
            found.append(
                Sample(
                    'failed',
                    error='; '.join(
                        f'{item["code"]} {item.get("path", "")}: {item.get("message", "")}'
                        for item in problem.diagnostics
                    ),
                )
            )
    return found


def check(plan, values=None, *, time_tolerance=0.0, **options):
    """The differences between the run that reads a rule only when its answer can have changed
    (D-65) and the run that reads every rule at every moment: a list of (place in the trace, the event
    of the scoped run, the event of the other run), each event as (time, rule, outcome) or None.
    Two events are the same when their rule and outcome are, and their times are within
    `time_tolerance` hours."""
    scoped = run(plan, values, reading='scoped', **options)
    every = run(plan, values, reading='every', **options)
    found = []
    for place in range(max(len(scoped.trace), len(every.trace))):
        one = scoped.trace[place] if place < len(scoped.trace) else None
        other = every.trace[place] if place < len(every.trace) else None
        same = (
            one is not None
            and other is not None
            and one[1:] == other[1:]
            and abs(one[0] - other[0]) <= time_tolerance
        )
        if not same:
            found.append((place, one, other))
    return found
