"""Other estimators of the expectation of an outcome (docs/engine.md, "Estimators").

A Monte Carlo study (`uncertainty.py`) draws every uncertain value and the outcome of every event
that goes by chance, and gives the mean of an outcome with the error of independent samples. Each
function here is another estimator of the same expectation, at the horizon of one run. A caller
asks for it by name; each says what it assumes and gives the interval that belongs to it
(`estimators.py` has the mathematics, with no model).

- `weighted`: the outcomes of the events that go by chance are not drawn. For each sample of the
  uncertain values, every path of those outcomes is run, and the paths are added with their
  weights. What is left of the error is that of the uncertain values and of the values that an
  event draws; a run with neither has no sampling error at all.
- `controlled`: the mean of a finished Monte Carlo study with a control, the linear form of the
  uncertain inputs at the central run. The estimate has no bias whatever the model is; its error
  is small where the outcome is near that linear form.
- `derivatives`: the derivative of the expectation of each outcome by an input. The mean of the
  derivatives of the samples is that derivative only where the outcome of a sample is continuous
  in the input. Each pair of an outcome and an input has a label that says which estimate it has,
  and why, or that it has none.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import integrate

from ..distributions import FAMILIES, quantile
from ..expressions import names_in
from ..model.ir import thaw
from ..model.uncertain import reads
from . import estimators
from .errors import SimulationError
from .report import evaluate_outputs
from .sampling import SamplingSettings, uncertain
from .study import evaluate_study
from .uncertainty import drawn, rows_of, run_sample, written_values

# The most paths of the outcomes of one sample (`weighted`).
PATHS = 4096


def _draws(rs):
    """Whether an event of the run draws a value when it fires."""
    return any(item.kind == 'draw' for rule in rs.rules.values() for item in rule.extras or ())


def _refused(diagnostics):
    return {'admissible': False, 'diagnostics': list(diagnostics)}


def _interval(values, settings, confidence):
    """The mean of one number for each sample, with the interval of the sampling method: that of
    the blocks for `sobol`, that of independent samples else. One sample has no interval."""
    if len(values) == 1:
        return {'mean': float(values[0]), 'se': None, 'low': None, 'high': None, 'n': 1}
    if settings.method == 'sobol':
        return estimators.replicate_interval(
            np.split(np.asarray(values, dtype=float), settings.replicates), confidence
        )
    return estimators.mean_interval(values, confidence)


def weighted(
    model,
    run,
    edits=None,
    settings=None,
    numerical_settings=None,
    *,
    limit=PATHS,
    confidence=0.95,
    check_samples=None,
):
    """The mean of each outcome of one run at its horizon, with the outcomes of the events that go
    by chance weighted and not drawn.

    The central study and the samples of the uncertain values are those of a Monte Carlo study
    with the same `settings` (`uncertainty.drawn`); the values that an event draws when it fires
    come from the streams of the sample, as there. For each sample, every path of the outcomes is
    run (`estimators.every_path`, at most `limit` paths), and the mean of an outcome in that sample
    is the sum over its paths, each with its weight: the expectation over the outcomes, given the
    values of the sample. The estimate is the mean of those sums over the samples, with the
    interval of the sampling method. A run with no uncertain value and no drawn value has one
    sample: the estimate is exact but for the numerical error of the runs (`se` is None).

    It gives {admissible, run, samples, paths, settings, confidence, outcomes, events}:
    `outcomes[name]` is {estimated, mean, se, low, high, sd, unit}, `sd` being the standard
    deviation of the outcome itself; an outcome that one path does not estimate has no value, and
    its statuses. `events[event][outcome]` is the expected number of firings with that outcome.
    A path that fails, or more paths than the limit, refuses the estimate, with the diagnostics."""
    settings = settings or SamplingSettings()
    study = evaluate_study(model, edits, numerical_settings, runs=[run])
    if not study.admissible:
        return _refused(study.diagnostics)
    values, points, errors = drawn(model, study, settings, check_samples)
    if errors:
        return _refused(errors)
    central = study.runs[run]
    rs, horizon = central['resolved'], central['trajectory'].horizon
    names = uncertain(values[run])
    sampled = bool(names) or _draws(rs)
    # With nothing drawn but the outcomes, every sample has the same paths: one is enough.
    samples = points[run] if sampled else [model.point_values(values[run])]
    means = {name: [] for name in rs.outcomes}
    squares = {name: [] for name in rs.outcomes}
    statuses = {name: set() for name in rs.outcomes}
    events, count = {}, 0
    for k, point in enumerate(samples):
        luck = {'seed': settings.seed, 'sample': k} if sampled else None
        context = {'run': run, 'sample': k, 'seed': settings.seed}
        failed = []

        def one(places, point=point, luck=luck, failed=failed):
            found = run_sample(model, run, point, numerical_settings, [horizon], luck, outcomes=places)
            if found['failures']:
                failed.extend({**item, 'outcomes': list(places)} for item in found['failures'])
                raise _Failed
            return [(chances, place) for _, chances, place, _ in found['firings']], found

        try:
            paths = estimators.every_path(one, limit)
        except _Failed:
            return _refused({**item, **context} for item in failed)
        except estimators.TooManyPaths as problem:
            return _refused([{'code': 'paths', 'severity': 'error', 'message': str(problem), **context}])
        count += len(paths)
        rows = [(weight, found['rows'][0]) for weight, _, found in paths]
        for name in rs.outcomes:
            statuses[name] |= {row['statuses'][name] for _, row in rows}
            if statuses[name] == {'estimated'}:
                one_mean = estimators.weighted([(weight, row['values'][name]) for weight, row in rows])
                means[name].append(one_mean['mean'])
                squares[name].append(one_mean['variance'] + one_mean['mean'] ** 2)
        for weight, _, found in paths:
            for event, counts in found['events'].items():
                total = events.setdefault(event, dict.fromkeys(counts, 0.0))
                for outcome, n in counts.items():
                    total[outcome] += weight * n / len(samples)
    outcomes = {}
    for name, definition in rs.outcomes.items():
        if statuses[name] != {'estimated'}:
            outcomes[name] = {'estimated': False, 'statuses': sorted(statuses[name])}
            continue
        found = _interval(means[name], settings, confidence)
        # The variance of the outcome is the mean of its squares less the square of its mean.
        spread = math.sqrt(max(0.0, float(np.mean(squares[name])) - found['mean'] ** 2))
        outcomes[name] = {'estimated': True, **found, 'sd': spread, 'unit': definition.unit}
    return {
        'admissible': True,
        'run': run,
        'samples': len(samples),
        'paths': count,
        'settings': settings.record(),
        'confidence': confidence,
        'outcomes': outcomes,
        'events': events,
    }


class _Failed(Exception):
    """A path of a sample failed: its diagnostics are with the caller."""


def mean_of(family, args):
    """The mean of a distribution of numbers: the integral of its quantile function over (0, 1),
    by adaptive quadrature. One function serves every family."""
    if FAMILIES[family].kind != 'number':
        raise ValueError(f'a {family} gives no numbers')
    found, _ = integrate.quad(
        lambda u: float(quantile(family, args, u)), 0.0, 1.0, epsabs=0.0, epsrel=1e-11, limit=400
    )
    return float(found)


def controlled(result, run, *, coefficients=None, numerical_settings=None, confidence=0.95):
    """The mean of each outcome of one run of a finished Monte Carlo study at its horizon, with a
    control: the linear form of the uncertain inputs at the central run.

    For an outcome y and the uncertain inputs x, the control of a sample is `c = sum g (x - x0)`:
    x0 the central values and g the derivative of the outcome by each input at the central run
    (`timeline.derivatives.report`). The mean of c is known, `sum g (E[x] - x0)`, with the mean of
    each input from its distribution (`mean_of`). The estimate is the mean of `y - (c - E[c])`
    (`estimators.control_variate`): it has no bias whatever g is, and its error is that of what
    the linear form does not explain.

    An input has no part in the control (its g is 0) when it is no number, when its distribution
    reads other values (its mean is then not that of one distribution), or when the engine gives no
    derivative by it; `left_out` has the reason of each. `coefficients`, {outcome: {input: g}} in
    the units of the file, takes the place of the derivatives of the engine: any numbers that do
    not come from the samples keep the estimate without bias (differences of two runs, say).

    It gives {run, samples, confidence, outcomes, left_out}: `outcomes[name]` is {estimated, mean,
    se, low, high, n, plain, coefficients}, `plain` being the mean with no control and its
    interval. With `sobol` sampling each interval is that of the blocks. With `latin` sampling it
    is that of independent samples, which is not too narrow for many samples."""
    if not result.admissible:
        raise ValueError('the study was rejected: it has no samples')
    model, settings = result.study.model, result.settings
    library = thaw(model.library)
    central = result.study.runs[run]
    rs, horizon = central['resolved'], central['trajectory'].horizon
    sampled = result.samples[run]
    written = written_values(model, result.study.effective_edits, [run])[run]
    left_out, means = {}, {}
    for name in uncertain(written):
        record = written[name]
        if FAMILIES[record['family']].kind != 'number':
            left_out[name] = 'its values are no numbers'
        elif reads(record):
            left_out[name] = 'its distribution reads other values'
    names = [name for name in uncertain(written) if name not in left_out]
    for name in names:
        means[name] = mean_of(written[name]['family'], written[name]['args'])
    centre = model.point_values(written)
    given = coefficients is not None
    slopes = {} if not given else {outcome: dict(row) for outcome, row in coefficients.items()}
    if not given and names:
        slopes, why = _central_slopes(rs, library, names, numerical_settings)
        for name in names:
            if all(row.get(name) is None for row in slopes.values()):
                left_out[name] = why.get(name, 'the engine gives no derivative by it')
    blocks = settings.replicates if settings.method == 'sobol' else None
    rows = [sample[horizon] for sample in rows_of(result, run, [horizon], library)]
    (central_row,) = evaluate_outputs(central, library, [horizon])
    outcomes = {}
    for name in rs.outcomes:
        statuses = {central_row['statuses'][name]} | {row['statuses'][name] for row in rows}
        if statuses != {'estimated'}:
            outcomes[name] = {'estimated': False, 'statuses': sorted(statuses)}
            continue
        used = {
            other: float(slope)
            for other, slope in (slopes.get(name) or {}).items()
            if other in names and slope is not None and math.isfinite(slope)
        }
        y = np.array([row['values'][name] for row in rows], dtype=float)
        control = np.zeros(len(y))
        expected = 0.0
        for other, slope in used.items():
            drawn_values = np.array([point[other] for point in sampled['values']], dtype=float)
            control += slope * (drawn_values - centre[other])
            expected += slope * (means[other] - centre[other])
        found = estimators.control_variate(y, control, expected, confidence, blocks)
        outcomes[name] = {'estimated': True, **found, 'coefficients': used}
    return {
        'run': run,
        'samples': len(sampled['values']),
        'confidence': confidence,
        'outcomes': outcomes,
        'left_out': left_out,
    }


def _central_slopes(rs, library, names, numerical_settings):
    """({outcome: {input: the derivative of the outcome by the input at the central run, or
    None}}, {input: why the engine gives none}), in the units of the file."""
    from . import timeline
    from .errors import SimulationError
    from .timeline import derivatives

    try:
        plan = timeline.Plan.flat(rs, library)
        report = derivatives.report(plan, None, names, settings=numerical_settings, error=False)
    except (timeline.Outside, SimulationError) as problem:
        return {}, dict.fromkeys(names, f'the engine gives no derivative of this run: {problem}')
    slopes, why = {}, {}
    for outcome, row in report['derivatives'].items():
        slopes[outcome] = {}
        for name, item in row.items():
            slopes[outcome][name] = item['value']
            if item['value'] is None:
                why[name] = f'the derivative by it is {item["class"]}: {"; ".join(item["why"])}'
    return slopes, why


# The labels of the derivative of an expectation (`derivatives`).
ZERO, SAMPLE_MEAN, BRANCHES, UNSUPPORTED = (
    'zero by the structure',
    'sample mean',
    'branch weighting',
    'unsupported',
)
CONTINUOUS = (
    'no event, no comparison and no store at rest on its bound is on a way from the input to the '
    'outcome: the outcome of a sample is continuous in the input'
)


def _reading(model, written, name):
    """The uncertain values whose draw changes with the input `name`: their distribution reads it,
    or reads one of them."""
    needs = {
        other: {
            symbol
            for source in (model.arguments.get(other, {}).get(written[other]['text']) or {}).values()
            for symbol in names_in(source)
        }
        for other in uncertain(written)
    }
    found, grows = set(), True
    while grows:
        more = {other for other, read in needs.items() if other not in found and read & ({name} | found)}
        found, grows = found | more, bool(more)
    return sorted(found)


def labels(model, plan, written, inputs):
    """{outcome: {input: (label, [why])}} of the derivative of the expectation of each outcome of
    a plan by each input, from the structure alone (`derivatives`).

    - Zero by the structure: no read of the model leads from the input to the outcome, and the
      draw of no uncertain value that reaches the outcome follows the input (`_reading`).
    - Unsupported, with each reason: the input is uncertain itself; the draw of an uncertain
      value that reaches the outcome follows the input; or, in a run whose outcomes are
      given, the outcome can jump when the input changes by a little (`Influence.breaks`), or a
      chance has a comparison that the input can change.
    - Branch weighting: the outcome of a path is continuous in the input, and the input changes
      the chance of an outcome of an event that reaches the outcome.
    - Sample mean: the outcome of a path is continuous in the input, and no such chance is."""
    from .timeline import Outside
    from .timeline.influence import Influence, chance_nodes
    from .timeline.places import output_place, rule_place

    try:
        of = plan.fast() or plan
    except Outside:
        of = plan
    full, lean = Influence(of), Influence(of, paths=True)
    names = uncertain(written)
    found = {output: {} for output in of.outputs}
    for name in inputs:
        reached, moved = full.after({name}), lean.after({name})
        reading = _reading(model, written, name)
        for output in of.outputs:
            place = output_place(output)
            before = full.before({place})
            # The input reaches the outcome by a read of the run, or by the draw of a value.
            draws = [other for other in reading if other in before]
            if place not in reached and not draws:
                found[output][name] = (ZERO, [])
                continue
            why = []
            if name in names:
                why.append('the input is uncertain: a study draws its values')
            why += [f'the draw of {other} follows the input' for other in draws]
            why += lean.breaks(name, output)
            chancy = [
                rule
                for rule in of.rules
                if rule_place(rule.index) in before
                and any(of.reads(node) & moved for node in chance_nodes(rule))
            ]
            jumps = sorted(
                rule.name
                for rule in chancy
                if any(lean.comparisons(node, moved) for node in chance_nodes(rule))
            )
            if jumps:
                why.append(f'a chance with a comparison that the input can change: {", ".join(jumps)}')
            if why:
                found[output][name] = (UNSUPPORTED, why)
            elif chancy:
                rules = ', '.join(sorted(rule.name for rule in chancy))
                found[output][name] = (
                    BRANCHES,
                    [
                        f'the input changes the chance of an outcome of {rules}: each path has the derivative of its weight'
                    ],
                )
            else:
                found[output][name] = (SAMPLE_MEAN, [CONTINUOUS])
    return found


def derivatives(
    model,
    run,
    inputs=None,
    edits=None,
    settings=None,
    numerical_settings=None,
    *,
    exceed=None,
    quantiles=None,
    limit=PATHS,
    confidence=0.95,
    check_samples=None,
):
    """The derivative of the expectation of each outcome of one run at its horizon by each of
    `inputs` (default: each input with one value), with a label for each pair.

    The mean of the derivatives of the samples is the derivative of the expectation only where the
    outcome of a sample is continuous in the input. Where an event, a comparison or a chance is
    between the two, a small change of the input moves an edge at which the outcome jumps, and the
    mean of the derivatives misses what crosses the edge: for a uniform number U and the outcome
    `1 if U < x else 0`, each sample has the derivative 0 and the expectation has the derivative 1.
    So each pair has one label (`labels`), from the structure of the model:

    - `zero by the structure`: the derivative is 0.
    - `sample mean`: the outcome of a sample is continuous in the input; the estimate is the mean
      of the derivatives of the samples.
    - `branch weighting`: the input changes the chance of outcomes. The outcomes are not drawn:
      every path of them is run (`estimators.every_path`), and a path gives the derivative of its
      value times its weight and the derivative of its weight times its value.
    - `unsupported`: no estimate is given, and `why` has each reason.

    The samples of the uncertain values are those of a Monte Carlo study with the same `settings`;
    the outcomes of the events are weighted in every case, at most `limit` paths for a sample.
    With no uncertain value there is one sample, and the estimate is exact but for the numerical
    error of the runs (`se` None). A pair whose run the engine carries no derivative through, or
    in which the run meets a change of kind that the structure did not show, is unsupported too.

    `exceed`, {outcome: a value in its unit}, asks the derivative of the chance that the outcome
    is above the value, and `quantiles`, {outcome: p}, that of its quantile
    (`estimators.tail_slopes`): they need independent samples (`random` sampling), and where they
    need the density of the outcome they converge more slowly than a mean (`slower`).

    It gives {admissible, run, samples, paths, settings, confidence, inputs, outcomes,
    derivatives}: `outcomes[name]` is the expectation with its interval; `derivatives[outcome]
    [input]` is {label, why, value, se, low, high, unit, one_sided}, and `exceedance` and
    `quantile` where asked. `one_sided` says that a sample sat on a bend of an expression: there
    the value is the derivative of one side. A chance that the input changes and that is 0 or 1
    has no estimate: a change of the input opens a path that has no weight now."""
    from . import timeline

    settings = settings or SamplingSettings()
    study = evaluate_study(model, edits, numerical_settings, runs=[run])
    if not study.admissible:
        return _refused(study.diagnostics)
    values, points, errors = drawn(model, study, settings, check_samples)
    if errors:
        return _refused(errors)
    library = thaw(model.library)
    rs = study.runs[run]['resolved']
    written = values[run]
    names = uncertain(written)
    plan = timeline.flat_plan(rs, library)
    chosen = (
        list(inputs) if inputs is not None else [name for name in plan.parameter_scale if name not in names]
    )
    for name in chosen:
        if name not in plan.parameter_scale:
            raise KeyError(f'{name} is no input of the model')
    label = labels(model, plan, written, chosen)
    wanted = [
        name for name in chosen if any(label[output][name][0] in (SAMPLE_MEAN, BRANCHES) for output in label)
    ]
    units, parts = plan.units, plan.resolved
    scale = {output: units.scale(parts.outcomes[output].unit) for output in label}
    samples = points[run] if names else [model.point_values(written)]
    # For each sample: the weight of each path, and for each outcome its value and for each
    # wanted input the derivative of the value and of the weight.
    weights, level, slope, lean = [], {o: [] for o in label}, {}, []
    problems, bends, unestimated, count = {}, set(), set(), 0
    graph = None
    for k, point in enumerate(samples if wanted else ()):
        context = {'run': run, 'sample': k, 'seed': settings.seed}
        try:
            own = model.resolve(run, point)
            own_plan = timeline.flat_plan(own, library)

            def one(places, own=own, own_plan=own_plan):
                made = timeline.run(
                    own_plan,
                    None,
                    settings=numerical_settings,
                    directions=wanted,
                    outcomes=places,
                    inputs=own.values,
                    resolved=own,
                )
                return [(chances, place) for _, chances, place, _ in made.firings], made

            paths = estimators.every_path(one, limit)
        except timeline.Outside as problem:
            # The engine carries no derivative through a part of this run: no pair has an estimate.
            for output in label:
                for name in wanted:
                    problems.setdefault((output, name), []).append(
                        f'the engine carries no derivative: {problem}'
                    )
            weights = []
            break
        except estimators.TooManyPaths as problem:
            return _refused([{'code': 'paths', 'severity': 'error', 'message': str(problem), **context}])
        except SimulationError as problem:
            return _refused({**item, **context} for item in _diagnostics(problem))
        count += len(paths)
        if graph is None:
            from .timeline.influence import Influence

            graph = Influence(paths[0][2].run.plan)
        w = np.array([weight for weight, _, _ in paths])
        weights.append(w)
        dw = np.zeros((len(wanted), len(paths)))
        for j, (weight, _, made) in enumerate(paths):
            unestimated |= set(made.unestimated)
            for _, chances, place, slopes in made.firings:
                for at, name in enumerate(wanted):
                    dw[at, j] += weight * slopes[place][at] / chances[place]
                    if any(chance <= 0 and row[at] != 0 for chance, row in zip(chances, slopes)):
                        # The input opens a path that has no weight now: that path is not run.
                        for output in label:
                            if label[output][name][0] == BRANCHES:
                                problems.setdefault((output, name), []).append(
                                    'a chance that the input changes is at the end of its range'
                                )
            for kind, at, places, detail in made.notes:
                for output in graph.outputs(places):
                    if kind == 'tie':
                        bends.add((output, wanted[at]))
                    else:
                        problems.setdefault((output, wanted[at]), []).append(f'a run met: {detail}')
        lean.append(dw)
        for output in label:
            if output in unestimated:
                continue
            level[output].append(np.array([made.outputs[output] / scale[output] for _, _, made in paths]))
            for name in wanted:
                slope.setdefault((output, name), []).append(
                    np.array([made.tangents[name][output] / scale[output] for _, _, made in paths])
                )
    ran = bool(weights)
    outcomes = {}
    for output in label if ran else ():
        if output in unestimated:
            outcomes[output] = {'estimated': False}
            continue
        found = _interval([float(w @ y) for w, y in zip(weights, level[output])], settings, confidence)
        outcomes[output] = {'estimated': True, **found, 'unit': parts.outcomes[output].unit}
    found = {}
    for output, row in label.items():
        found[output] = {}
        for name in chosen:
            kind, why = row[name]
            per = f'{parts.outcomes[output].unit} per {parts.parameters[name].unit}'
            item = {'label': kind, 'why': list(why), 'value': None, 'se': None, 'low': None, 'high': None}
            item |= {'unit': per, 'one_sided': (output, name) in bends}
            found[output][name] = item
            if kind == ZERO:
                item['value'] = 0.0
                continue
            if kind == UNSUPPORTED:
                continue
            met = list(dict.fromkeys(problems.get((output, name), ())))
            if output in unestimated:
                met.append('the outcome is not estimated')
            if not ran and not met:
                met.append('no run was made')
            at = wanted.index(name)
            columns = slope.get((output, name), [])
            if not met and not all(np.all(np.isfinite(column)) for column in columns):
                met.append('a derivative is no finite number')
            if met:
                item |= {'label': UNSUPPORTED, 'why': met}
                continue
            each = [float(w @ dy + dw[at] @ y) for w, dy, dw, y in zip(weights, columns, lean, level[output])]
            total = _interval(each, settings, confidence)
            item |= {'value': total['mean'], 'se': total['se'], 'low': total['low'], 'high': total['high']}
            tails = [(w, y, dy, dw[at]) for w, y, dy, dw in zip(weights, level[output], columns, lean)]
            for key, asked, argument in (('exceedance', exceed, 'threshold'), ('quantile', quantiles, 'p')):
                if asked and output in asked:
                    item[key] = (
                        estimators.tail_slopes(tails, confidence=confidence, **{argument: asked[output]})
                        if settings.method == 'random'
                        else None
                    )
    return {
        'admissible': True,
        'run': run,
        'samples': len(samples) if ran else 0,
        'paths': count,
        'settings': settings.record(),
        'confidence': confidence,
        'inputs': chosen,
        'outcomes': outcomes,
        'derivatives': found,
    }


def _diagnostics(problem):
    items = getattr(problem, 'diagnostics', None)
    return (
        list(items) if items else [{'code': 'evaluation_error', 'severity': 'error', 'message': str(problem)}]
    )
