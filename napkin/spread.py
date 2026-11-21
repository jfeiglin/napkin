"""Spreads: one run of a model sampled many times (docs/engine.md, "The spread").

`spread(model, paths, times=None, *, run=None, edits=None, samples=200, seed=0, jobs=1, ...)` is the
Monte Carlo study (`napkin.engine.uncertainty.monte_carlo`) of one run of a model, as a command or a
script asks for it:

    from napkin.spread import spread

    found = spread('model.scn', ['tank.water'], [24], samples=200, seed=0, jobs=4)
    if found.refused is None:
        water = found.spread('tank.water', 24).summary

- `model`: the path of a model file or of a package's folder (`load_scenario`), or a model that the
  front end compiled (`napkin.model.compile.Compiled`).
- `run` names a run of the model (None for its default run), and `edits` is an edit document, checked
  whole first, in every run of the model (`Compiled.configure`): a problem raises `LanguageError`
  before any run starts.
- `paths` are the values that the study reads, and `times` the times in hours (by default the
  horizon of the run): the caller selects them (D10).
- `samples` and `seed` are the sampling settings (`SamplingSettings`); `jobs` the processes that run
  the samples (1: this process), `progress(done, total)` is called as samples finish, and `cancel`
  (an event, such as a `threading.Event`) stops the study between samples with `study.Cancelled`.

A pool starts its processes with `spawn`, and each imports the main module of the program that made
it: a script that uses more than one process calls `spread` under `if __name__ == '__main__':`.
"""

from __future__ import annotations

from .engine.sampling import SamplingSettings
from .engine.uncertainty import monte_carlo
from .model.compile import Compiled, load_scenario


def spread(
    model,
    paths,
    times=None,
    *,
    run=None,
    edits=None,
    samples=200,
    seed=0,
    jobs=1,
    progress=None,
    cancel=None,
):
    """The Monte Carlo study of a run of a model (see the module): a `MonteCarlo`."""
    settings = SamplingSettings(samples, seed)
    if not isinstance(model, Compiled):
        model = load_scenario(model)
    configuration = model.configure(run, edits)
    if times is None:
        times = (configuration.request.horizon,)
    return monte_carlo(
        model.program,
        configuration,
        paths,
        times,
        settings,
        model=model.table,
        jobs=jobs,
        progress=progress,
        cancel=cancel,
    )
