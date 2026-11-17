"""The report of the derivatives of a run: each output by each input, with its kind.

A run with `directions` carries the derivative of every value by each input, on the path of its
events (`run.py`). That number alone does not say what it is worth. This report gives, for each
output and each input:

- `value`: the derivative of the output at the horizon, in the unit of the output for one unit of
  the input, as the file writes the two;
- `class`: of which kind the derivative is (below);
- `why`: what the run met that decides the class;
- `error`: how far the value is from that of a second run with tolerances a hundred times
  tighter. It is an estimate of the numerical error of the value, and no bound.

The classes:

- `structurally zero`: no read of the model leads from the input to the output
  (`influence.Influence`). The derivative is 0 for every value of every input.
- `smooth`: the run met nothing that a small change of the input can change in kind. The value is
  the derivative.
- `one-sided`: the value is the derivative for changes of the input to one side. On the other
  side another piece of an expression gives a value, a condition changes, two events of one
  moment change their order, or the central run takes another outcome (`Run.note`). The class is
  the safe one: where a tie holds at one time only and the value passes through it, the
  derivative of both sides can be the same.
- `undefined`: the time of a crossing is not decided by its value (the value comes to its mark
  without a rate, or within its tolerance for longer than a step cap), or the value is not a
  finite number. No derivative is given.
- `unsupported`: the engine cannot carry a derivative through a part of this run, and names the
  part: a part that it does not run with derivatives, or a rate of a numeric block that jumps at a
  time that the input moves (a comparison in the rate whose two sides change their order). No
  derivative is given.

The margins of the run say how near it came to a change of kind: the longest time in which a
crossing is decided only within the tolerance of its value, the least time between two moments
with a step, and the least distance between the two likeliest outcomes of a firing.
"""

from __future__ import annotations

import math

from ..errors import SimulationError
from ..runtime import NumericalSettings
from .influence import Influence
from .places import output_place
from .plan import Outside

CLASSES = ('structurally zero', 'smooth', 'one-sided', 'undefined', 'unsupported')
UNDEFINED = frozenset({'grazing'})
# The kinds of a note that make a derivative unsupported: a jump of a rate at a place that the input
# moves, which the tangents of a block do not carry (`Run.jumps`).
UNSUPPORTED = frozenset({'jump'})
# How much tighter the tolerances of the second run are (`error`).
TIGHTER = 100.0


def _finite(value):
    return value if math.isfinite(value) else None


def _tighter(settings):
    cfg = NumericalSettings.parse(settings)
    return {**vars(cfg), 'rtol': cfg.rtol / TIGHTER, 'atol_factor': cfg.atol_factor / TIGHTER}


def report(plan, values=None, inputs=None, *, settings=None, error=True, **options):
    """The report of the derivatives of one run of a plan (the module). `inputs` names the inputs
    (default: every input of the model); `values`, `settings` and `options` are those of
    `timeline.run`. With `error` false, no second run is made and each error is None."""
    from . import run as run_plan

    names = tuple(inputs) if inputs is not None else tuple(plan.parameter_scale)
    for name in names:
        if name not in plan.parameter_scale:
            raise KeyError(f'{name} is no input of the model')
    options = {key: value for key, value in options.items() if key != 'directions'}
    unsupported, tight = None, None
    try:
        result = run_plan(plan, values, settings=settings, directions=names, **options)
    except Outside as problem:
        # The outputs have their values all the same: from the run with no derivative.
        unsupported = str(problem)
        result = run_plan(plan, values, settings=settings, **options)
    # The graph of the plan with each space in the fast tier where that plan can be made: there
    # each quantity has its own reads, and not those of its whole space.
    try:
        graph = Influence(plan.fast() or plan)
    except Outside:
        graph = Influence(plan)
    if unsupported is None and error:
        try:
            tight = run_plan(plan, values, settings=_tighter(settings), directions=names, **options)
        except (Outside, SimulationError):
            tight = None
    units, parts = plan.units, plan.resolved
    reached = {name: graph.after({name}) for name in names}
    notes = {}
    for kind, k, places, detail in result.notes:
        notes.setdefault(k, []).append((kind, graph.after(places), detail))
    found = {}
    for output in result.outputs:
        place, scale = output_place(output), units.scale(parts.outcomes[output].unit)
        row = found[output] = {}
        for k, name in enumerate(names):
            per = f'{parts.outcomes[output].unit} per {parts.parameters[name].unit}'
            if place not in reached[name]:
                if unsupported is None and result.tangents[name][output] != 0:
                    raise SimulationError(
                        f'The derivative of {output} by {name} is not zero, and no read of the model '
                        'leads from the one to the other'
                    )
                row[name] = {'value': 0.0, 'unit': per, 'class': 'structurally zero', 'why': [], 'error': 0.0}
                continue
            if unsupported is not None:
                row[name] = {
                    'value': None,
                    'unit': per,
                    'class': 'unsupported',
                    'why': [unsupported],
                    'error': None,
                }
                continue
            slope = result.tangents[name][output] / scale
            met = [(kind, detail) for kind, after, detail in notes.get(k, ()) if place in after]
            why = list(dict.fromkeys(detail for _, detail in met))
            if not math.isfinite(slope):
                kind, why = 'undefined', [*why, 'the derivative is no finite number']
            elif any(kind in UNDEFINED for kind, _ in met):
                kind = 'undefined'
            elif any(kind in UNSUPPORTED for kind, _ in met):
                kind = 'unsupported'
            else:
                kind = 'one-sided' if met else 'smooth'
            given = kind not in ('undefined', 'unsupported')
            other = None if tight is None else tight.tangents[name][output] / scale
            row[name] = {
                'value': slope if given else None,
                'unit': per,
                'class': kind,
                'why': why,
                'error': abs(slope - other) if given and other is not None and math.isfinite(other) else None,
            }
    return {
        'inputs': list(names),
        'outputs': {
            name: {
                'value': value / units.scale(parts.outcomes[name].unit),
                'unit': parts.outcomes[name].unit,
                'label': parts.outcomes[name].label,
            }
            for name, value in result.outputs.items()
        },
        'unestimated': list(result.unestimated),
        'derivatives': found,
        # A margin that the run has no case of is None: no crossing, one moment, no chance.
        'margins': {
            'crossing_time_h': result.margins['crossing_time_h'] or None,
            'moments_apart_h': _finite(result.margins['moments_apart_h']),
            'outcome': _finite(result.margins['outcome']),
        },
        'unsupported': unsupported,
    }
