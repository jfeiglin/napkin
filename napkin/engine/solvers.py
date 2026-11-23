"""The interface of a solver of a stiff initial value problem, and its adapters.

The engine integrates `y' = f(t, y)` from one moment to the next. It owns the moments, the roots that
end a segment and the bounds; a solver owns the steps, the control of the error and the solution
between two accepted steps. An **adapter** gives a solver of a library this one interface, so that
the engine and the comparison of solvers read every solver in one way:

- `adapter.start(fun, t0, y0, t_end, ...)` gives a `Run`;
- `run.step()` makes one accepted step and gives it as a `Step`: the times `t_old` and `t`, the state
  `y` at `t`, and `dense`, the solution between the two (`dense(at)` for `t_old <= at <= t`);
- `run.finished` is true when a step has ended exactly at `t_end`; no step goes past it;
- `run.counts()` gives the calls of `fun` (every one, also those that a solver makes to find a
  Jacobian by differences), the Jacobians and the factorizations so far;
- a `Step` also has `rate`, the rate of change of `dense` (`rate(at)`): the engine compares it with
  the field inside a long step (docs/engine/methods.md, "Integration tolerances");
- `run.limit(max_step)` sets the longest step from the next step on, and `run.retake(max_step)`
  forgets the last step: the run is at the start of that step again, with that limit. The engine
  retakes a step whose solution is too far from the field between its ends.

What every adapter guarantees (`tests/engine/test_solver_adapters.py` checks each of them, against
closed forms):

- **Accepted steps only.** The steps join: `t_old` of a step is `t` of the step before, and the first
  starts at `t0`. A rejected trial is never given.
- **An exact end.** The last step ends at `t_end` itself, not near it.
- **A solution between the steps that outlives the solver.** `dense` reads nothing of the run after
  it is made; it can be kept, pickled and read in another process, and it gives the same numbers
  there. At the two ends of its step it gives the accepted states to roundoff.
- **The same run again.** The same problem with the same options gives the same steps, bit for bit.
- **A failure is an error.** A problem that the solver cannot solve to its tolerances raises
  `SolverFailure`, and its run never finishes. Where the solution is of moderate size, each state
  that the solver accepted before the failure is the solution. (At a pole of the solution a solver
  can accept a last step whose time is past the pole by a rounding of the time: SciPy's Radau does.
  The engine's bounds and its check of finite values see such a state.)
- **A restart.** A new run from the time and the state of any step is a valid run: the engine
  restarts at every moment.
- **The rate of the solution between the steps.** `rate(at)` is the derivative of `dense` at `at`,
  to roundoff, and it outlives the solver as `dense` does.
- **A step again.** After `retake(max_step)` the next step starts where the forgotten step started,
  from the same state, and is no longer than `max_step`; the steps still join, and the work of the
  forgotten step stays in the counts.

A solver that cannot meet one of these is no candidate, whatever its speed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.integrate import Radau


class SolverFailure(RuntimeError):
    """A solver could not make its next step within its tolerances."""


@dataclass(frozen=True)
class Step:
    """One accepted step: from `t_old` to `t`, the state `y` at `t`, and the solution between them."""

    t_old: float
    t: float
    y: np.ndarray
    dense: Callable
    rate: Callable


class Run:
    """One integration from a start to an end. An adapter makes it (`start`)."""

    finished = False

    def step(self):
        """Make one accepted step and give it. Raises SolverFailure when the solver cannot, and
        RuntimeError when the run has finished."""
        raise NotImplementedError

    def counts(self):
        """{'evaluations', 'jacobians', 'factorizations'} of the run so far."""
        raise NotImplementedError

    def limit(self, max_step):
        """Let no step from the next one on be longer than `max_step` (infinity: no limit)."""
        raise NotImplementedError

    def retake(self, max_step):
        """Forget the last step: the run is at the start of that step again, and no step from here
        on is longer than `max_step`. The work of the forgotten step stays in the counts."""
        raise NotImplementedError


def radau_rate(dense, at):
    """The rate of change of the solution of one step of SciPy's Radau at a time of the step. The
    solution is `y_old + Q @ (x, x², …)` with `x` the part of the step that has passed
    (`RadauDenseOutput` of scipy.integrate._ivp.radau), so its rate is `Q @ (1, 2x, …) / h`."""
    x = (at - dense.t_old) / dense.h
    powers = np.arange(1, dense.order + 2) * x ** np.arange(dense.order + 1)
    return dense.Q @ powers / dense.h


class RadauRate:
    """`radau_rate` of one step, as a function of the time: it holds the solution of the step, which
    holds numbers only."""

    def __init__(self, dense):
        self.dense = dense

    def __call__(self, at):
        return radau_rate(self.dense, at)


class _Counted:
    """A function with the number of its calls."""

    def __init__(self, fun):
        self.fun, self.calls = fun, 0

    def __call__(self, t, y):
        self.calls += 1
        return self.fun(t, y)


class _RadauRun(Run):
    def __init__(self, solver, fun):
        self.solver, self.fun = solver, fun

    def step(self):
        solver = self.solver
        if self.finished:
            raise RuntimeError('the run has finished')
        # What the solver holds before the step. A step replaces what it holds and changes nothing
        # in place, so this is the solver at the start of the step again (`retake`;
        # `scipy.integrate._ivp.radau.Radau._step_impl`).
        self.held = dict(vars(solver))
        message = solver.step()
        if solver.status == 'failed':
            raise SolverFailure(message or 'the solver failed')
        self.finished = solver.status == 'finished'
        dense = solver.dense_output()
        return Step(solver.t_old, solver.t, solver.y, dense, RadauRate(dense))

    def limit(self, max_step):
        self.solver.max_step = max_step

    def retake(self, max_step):
        solver = self.solver
        counts = {name: getattr(solver, name) for name in ('nfev', 'njev', 'nlu')}
        vars(solver).clear()
        vars(solver).update(self.held)
        vars(solver).update(counts)
        solver.max_step = max_step
        self.finished = False

    def counts(self):
        solver = self.solver
        return {'evaluations': self.fun.calls, 'jacobians': solver.njev, 'factorizations': solver.nlu}


class ScipyRadau:
    """SciPy's Radau IIA of order 5: an implicit Runge-Kutta method for stiff problems, with a
    solution of order 3 between its steps. It steps in Python."""

    name = 'scipy-radau'

    def start(self, fun, t0, y0, t_end, **options):
        """A run of `y' = fun(t, y)` from `y0` at `t0` to `t_end`. `options` are those of
        `scipy.integrate.Radau`: `rtol`, `atol`, `jac`, `jac_sparsity`, `first_step`, `max_step`."""
        counted = _Counted(fun)
        return _RadauRun(Radau(counted, float(t0), y0, float(t_end), vectorized=False, **options), counted)


class Polynomial:
    """The solution between two steps as the polynomial through its values at some times of the
    step: `times` rise from the start of the step to its end, and `values` has one row for each. It
    holds numbers only, so it outlives its solver and goes through pickle."""

    def __init__(self, times, values):
        self.times, self.values = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
        # The weights of the barycentric form of the polynomial through the points.
        differences = self.times[:, None] - self.times[None, :]
        np.fill_diagonal(differences, 1.0)
        self.weights = 1.0 / differences.prod(axis=1)
        self.slopes = None  # the derivative at each point, made when a rate is first asked for

    def __call__(self, at):
        return self._through(self.values, at)

    def _through(self, values, at):
        """The polynomial through `values` at the points, at a time."""
        gaps = at - self.times
        exact = np.flatnonzero(gaps == 0)
        if len(exact):
            return values[exact[0]].copy()
        with np.errstate(over='ignore'):
            terms = self.weights / gaps
        # A time so near a point that its term has no number: the time is the point.
        exact = np.flatnonzero(np.isinf(terms))
        if len(exact):
            return values[exact[0]].copy()
        return terms @ values / terms.sum()

    def rate(self, at):
        """The derivative of the polynomial at a time. The derivative is a polynomial of a lower
        degree, so it is the polynomial through its own values at the points, in the same
        barycentric form: that form is stable at each time, also next to a point, where the
        derivative of the form itself loses its digits."""
        if self.slopes is None:
            # At the point k the derivative is the sum over each other point j of
            # (w_j / w_k) (f_j - f_k) / (t_k - t_j): from differences of the values only.
            gaps = self.times[:, None] - self.times[None, :]
            np.fill_diagonal(gaps, 1.0)
            factors = self.weights[None, :] / self.weights[:, None] / gaps
            np.fill_diagonal(factors, 0.0)
            steps = self.values[None, :, :] - self.values[:, None, :]
            self.slopes = np.einsum('kj,kjn->kn', factors, steps)
        return self._through(self.slopes, at)


def _chebyshev(start, end, count):
    """`count` times from `start` to `end`, both with them, close together near the two ends: the
    polynomial through values at such times is well conditioned."""
    if count == 1:
        return np.array([end])
    places = 0.5 - 0.5 * np.cos(np.pi * np.arange(count) / (count - 1))
    times = start + (end - start) * places
    times[0], times[-1] = start, end
    return times


class _CvodeRun(Run):
    def __init__(self, fun, t0, y0, t_end, rtol, atol, jac, max_step, first_step):
        from sundials4py import core, cvodes

        self.core, self.cvodes = core, cvodes
        self.fun = _Counted(fun)
        self.t, self.t_end = float(t0), float(t_end)
        n = len(y0)
        _, self.context = core.SUNContext_Create(core.SUN_COMM_NULL)
        # Each vector of the solver is a view of an array here: the arrays must live as long as it.
        self.state = np.array(y0, dtype=float)
        self.vector = core.N_VMake_Serial(n, self.state, self.context)
        self.out = np.zeros(n)
        self.out_vector = core.N_VMake_Serial(n, self.out, self.context)
        self.atol = np.broadcast_to(np.asarray(atol, dtype=float), (n,)).copy()
        self.atol_vector = core.N_VMake_Serial(n, self.atol, self.context)
        self.view = cvodes.CVodeCreate(cvodes.CV_BDF, self.context)
        self.memory = memory = self.view.get()
        pointer = core.N_VGetArrayPointer

        def rhs(t, y, ydot, _):
            pointer(ydot)[:] = self.fun(t, pointer(y))
            return 0

        self.rhs = rhs
        self._ok(cvodes.CVodeInit(memory, rhs, self.t, self.vector), 'CVodeInit')
        self._ok(cvodes.CVodeSVtolerances(memory, float(rtol), self.atol_vector), 'CVodeSVtolerances')
        self.matrix = core.SUNDenseMatrix(n, n, self.context)
        self.linear = core.SUNLinSol_Dense(self.vector, self.matrix, self.context)
        self._ok(cvodes.CVodeSetLinearSolver(memory, self.linear, self.matrix), 'CVodeSetLinearSolver')
        if jac is not None:

            def jacobian(t, y, fy, matrix, *_):
                # The data of a dense matrix come as an array by [row, column].
                core.SUNDenseMatrix_Data(matrix)[...] = np.asarray(jac(t, pointer(y)), dtype=float)
                return 0

            self.jacobian = jacobian
            self._ok(cvodes.CVodeSetJacFn(memory, jacobian), 'CVodeSetJacFn')
        self._ok(cvodes.CVodeSetStopTime(memory, self.t_end), 'CVodeSetStopTime')
        if max_step is not None and np.isfinite(max_step):
            self._ok(cvodes.CVodeSetMaxStep(memory, float(max_step)), 'CVodeSetMaxStep')
        if first_step is not None:
            self._ok(cvodes.CVodeSetInitStep(memory, float(first_step)), 'CVodeSetInitStep')
        # The state at the end of the last step, the start of the last step (`retake`), and the
        # work that the solver counted before it was started again there.
        self.last, self.before, self.counted = self.state.copy(), None, {'jacobians': 0, 'factorizations': 0}

    @staticmethod
    def _ok(flag, what):
        if flag < 0:
            raise SolverFailure(f'{what} gave the flag {flag}')

    def step(self):
        cvodes = self.cvodes
        if self.finished:
            raise RuntimeError('the run has finished')
        self.before = (self.t, self.last)
        flag, t = cvodes.CVode(self.memory, self.t_end, self.out_vector, cvodes.CV_ONE_STEP)
        if flag < 0:
            raise SolverFailure(f'CVODE gave the flag {flag} at t = {t!r}')
        t_old, self.t = self.t, float(t)
        self.finished = flag == cvodes.CV_TSTOP_RETURN or self.t >= self.t_end
        y = self.out.copy()
        # The solution of the step is a polynomial of the order of the step. Its values at order + 1
        # times of the step give that polynomial again, as numbers that need the solver no more.
        _, order = cvodes.CVodeGetLastOrder(self.memory)
        # A step so short that two of the times are one float keeps each time once.
        times = np.unique(_chebyshev(t_old, self.t, order + 1))
        values = np.empty((len(times), len(y)))
        for place, at in enumerate(times[:-1]):
            self._ok(cvodes.CVodeGetDky(self.memory, float(at), 0, self.out_vector), 'CVodeGetDky')
            values[place] = self.out
        values[-1] = y
        self.last = y
        solution = Polynomial(times, values)
        return Step(t_old, self.t, y, solution, solution.rate)

    def counts(self):
        cvodes = self.cvodes
        _, jacobians = cvodes.CVodeGetNumJacEvals(self.memory)
        _, setups = cvodes.CVodeGetNumLinSolvSetups(self.memory)
        return {
            'evaluations': self.fun.calls,
            'jacobians': self.counted['jacobians'] + jacobians,
            'factorizations': self.counted['factorizations'] + setups,
        }

    def limit(self, max_step):
        # CVODE reads a longest step of 0 as no limit.
        longest = float(max_step) if np.isfinite(max_step) else 0.0
        self._ok(self.cvodes.CVodeSetMaxStep(self.memory, longest), 'CVodeSetMaxStep')

    def retake(self, max_step):
        cvodes = self.cvodes
        # CVODE keeps no step to go back to: it is started again at the start of the last step, with
        # its options. That resets its counts, so the work so far is kept here.
        done = self.counts()
        self.counted = {name: done[name] for name in self.counted}
        self.t, self.last = self.before
        self.state[:] = self.last
        self._ok(cvodes.CVodeReInit(self.memory, self.t, self.vector), 'CVodeReInit')
        self._ok(cvodes.CVodeSetStopTime(self.memory, self.t_end), 'CVodeSetStopTime')
        self.limit(max_step)
        self.finished = False


class SundialsBdf:
    """CVODE of SUNDIALS, through `sundials4py`: the backward differentiation formulas of orders 1
    to 5 with a variable step and order, for stiff problems, with a dense linear solver. It steps in
    C; the function of the problem is a call into Python at each evaluation. It is here only when the
    package `sundials4py` can be imported: it is a candidate of the comparison, and no dependency."""

    name = 'sundials-bdf'

    def start(
        self, fun, t0, y0, t_end, *, rtol, atol, jac=None, max_step=None, first_step=None, jac_sparsity=None
    ):
        """A run of `y' = fun(t, y)` from `y0` at `t0` to `t_end`. `jac_sparsity` is not used: the
        linear solver is dense."""
        return _CvodeRun(fun, t0, y0, t_end, rtol, atol, jac, max_step, first_step)


def _candidates():
    found = [ScipyRadau()]
    try:
        import sundials4py  # noqa: F401
    except ImportError:
        return found
    return [*found, SundialsBdf()]


# The adapters by name. The engine's solver is the first; the others are the candidates of the
# comparison of Stage B1, each here only when its library is.
ADAPTERS = {adapter.name: adapter for adapter in _candidates()}
DEFAULT = ADAPTERS['scipy-radau']
