"""Monte Carlo studies: one run of a program sampled many times (docs/engine.md, "Monte Carlo studies").

`monte_carlo(program, configuration, paths, times, settings)` reads the values of `paths` at `times`
(the caller selects them, D10) in a central run and in each sample of a run:

1. **The central run** is the configuration in `median` mode: each numeric draw is its distribution's
   median, each categorical one its most likely eligible outcome. It runs first, alone, and its report
   (`report.report`) gives each value's unit and label and its central values. A central run that
   stops before its horizon, at a failure or a pause, refuses the study before any sample runs.
2. **The samples** are the configuration in `sampled` mode, each with its own seed
   (`sampling.sampled`), recording only the values that the study reads. Each runs through the run
   store, in this process or in `jobs` processes (`study.run_all`), and gives its values in their
   declared units (`napkin.engine.read`), the draws of its run in the order of its trace (their sites,
   owners and values, a number in its canonical unit), the number of its near-ties, and why it
   stopped if it did (`Sample`).
3. **A sample that stops** before its horizon refuses the study: every sample runs, `refused` names
   each that stopped, its seed and why, and the study has no summary. No sample is left out, because
   leaving one out biases the results.
4. **The summaries** (`expectations.summary`): for each value at each time, the central value, the
   mean with its interval, the standard deviation, the standard error, the extremes and the
   percentiles. A text, or a value that the central run or a sample could not give, has no summary,
   never zero, and says why.
5. **The drivers** of each summary: the rank correlation (Spearman) of the value with each draw that
   every sample made once at one site, by one owner, as a number or a yes/no, in the order of their
   strength. A draw that is the same in every sample has none.

N samples that run are not a proof for every draw: a value that no sample draws can still fail.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial

from ..program.config import MEDIAN
from . import expectations
from .report import reading_scale, report
from .sampling import SamplingSettings, sampled
from .study import run_all
from .timeline import paused, read
from .timeline.record import Reader, key_of, named


@dataclass(frozen=True)
class Sample:
    """One sample: its seed, the values of the study's paths at its times ([path][time], each in its
    declared unit, or `Unavailable`), the draws of its run ((site, owner, value) in the order of the
    trace), the number of its near-ties, and why it stopped before its horizon (None when it did not).
    When requested, scales are in the reading units at the same paths and times as the values."""

    seed: int
    values: tuple[tuple, ...]
    draws: tuple[tuple[str, str, object], ...]
    near_ties: int
    stopped: str | None
    scales: tuple[tuple[float | None, ...], ...] = ()


@dataclass(frozen=True)
class Spread:
    """What a study says of one path at one time: its unit and label, the summary of its samples
    (`expectations.Summary`), and its drivers, ((site, owner, rank correlation), ...) from the
    strongest."""

    path: str
    t: float
    unit: str
    label: str | None
    summary: expectations.Summary
    drivers: tuple[tuple[str, str, float], ...] = ()


@dataclass(frozen=True)
class MonteCarlo:
    """A Monte Carlo study (see the module): its settings, paths and times, the report of its central
    run, its samples in order, and the spread of each path at each time (path by path, then time by
    time); or, for a refused study, why (`refused`) and no spread."""

    settings: SamplingSettings
    paths: tuple[str, ...]
    times: tuple[float, ...]
    central: object
    samples: tuple[Sample, ...] = ()
    spreads: tuple[Spread, ...] = ()
    refused: str | None = None

    def spread(self, path, t):
        """The spread of a path at a time."""
        return next(item for item in self.spreads if item.path == path and item.t == float(t))


def stopped(record):
    """Why a record stops before its horizon, or None: a failure, or a pause."""
    if record.failure is not None:
        message = record.failure.detail('message') or 'the run failed'
        return f'the run failed at {float(record.failure.t):g} h: {message}'
    entry = paused(record)
    if entry is not None:
        return f'the run paused at {float(entry.t):g} h, where {entry.owner} waits'
    return None


def _sampled(paths, times, with_scales, program, configuration, record):
    """What a study keeps of one sample's run (`Sample`): it runs in the process that ran the sample."""
    values = tuple(reading.values for reading in read(record, program, paths, times))
    draws = tuple(
        (entry.part, entry.owner, entry.detail('value')) for entry in record.trace if entry.kind == 'draw'
    )
    scales = ()
    stop = stopped(record)
    if with_scales and stop is None:
        reader = Reader(record, program)
        scales = tuple(tuple(reading_scale(reader, program, path, at) for at in times) for path in paths)
    return Sample(configuration.seed, values, draws, len(record.near_ties()), stop, scales)


def monte_carlo(
    program,
    configuration,
    paths,
    times,
    settings=None,
    *,
    model=None,
    confidence=0.95,
    with_scales=False,
    jobs=1,
    progress=None,
    cancel=None,
):
    """The Monte Carlo study of a run (see the module): `paths` and `times` are the caller's, `model` the
    source or artifact evidence table (or a declared model), and `jobs`,
    `progress` and `cancel` are those of `study.run_all`. A path that the program does not have is a
    KeyError, and a time outside [0, horizon] or a number of jobs that is no whole number from 1 a
    ValueError, before any run starts."""
    settings = settings or SamplingSettings()
    paths, times = tuple(paths), tuple(float(t) for t in times)
    horizon = float(configuration.request.horizon)
    if not paths or not times:
        raise ValueError('a study reads one path or more at one time or more')
    for t in times:
        if not 0 <= t <= horizon:
            raise ValueError(f'a study reads times from 0 h to the horizon, {horizon:g} h, not {t:g} h')
    keys = tuple(dict.fromkeys(key_of(program, path) for path in paths))
    for found in keys:
        named(program, found)
    request = replace(configuration.request, everything=False, keys=keys)
    configuration = replace(configuration, request=request)
    central_run = replace(configuration, mode=MEDIAN, seed=None)
    central = report(
        run_all(program, [central_run], jobs=jobs)[0], program, central_run, paths, times, model=model
    )
    study = MonteCarlo(settings, paths, times, central)
    if central.stopped is not None:
        return replace(study, refused=f'the central run stops: {central.stopped}')
    work = partial(_sampled, paths, times, with_scales)
    samples = tuple(
        run_all(
            program,
            sampled(configuration, settings),
            work,
            jobs=jobs,
            progress=progress,
            cancel=cancel,
        )
    )
    study = replace(study, samples=samples)
    failed = [(k, sample) for k, sample in enumerate(samples) if sample.stopped is not None]
    if failed:
        return replace(
            study,
            refused='; '.join(
                f'sample {k} (seed {sample.seed}) stops: {sample.stopped}' for k, sample in failed
            ),
        )
    drawn = _drawn(samples)
    spreads = []
    for place, (path, value) in enumerate(zip(paths, central.values)):
        for when, t in enumerate(times):
            sampled_values = [sample.values[place][when] for sample in samples]
            summary = expectations.summary(sampled_values, value.values[when], confidence)
            drivers = _drivers(drawn, sampled_values) if summary.estimated else ()
            spreads.append(Spread(path, t, value.unit, value.label, summary, drivers))
    return replace(study, spreads=tuple(spreads))


def _drawn(samples):
    """{(site, owner): the value of each sample} of each draw that every sample made once, as a number
    or a yes/no."""
    found = None
    for sample in samples:
        seen = {}
        for site, owner, value in sample.draws:
            if isinstance(value, (bool, int, float)):
                seen.setdefault((site, owner), []).append(value)
        once = {draw: values[0] for draw, values in seen.items() if len(values) == 1}
        if found is None:
            found = {draw: [value] for draw, value in once.items()}
        else:
            for draw in found.keys() - once.keys():
                del found[draw]
            for draw, values in found.items():
                values.append(once[draw])
    return found or {}


def _drivers(drawn, values):
    """((site, owner, rank correlation), ...) of a value with each draw, from the strongest."""
    found = []
    for (site, owner), draws in drawn.items():
        rho = expectations.spearman(draws, values)
        if rho is not None:
            found.append((site, owner, rho))
    return tuple(sorted(found, key=lambda item: (-abs(item[2]), item[0], item[1])))
