# Brief P1: other solvers for the last steps of the selection order (a prototype)

Read `briefs/COMMON-B.md` for the rules of every agent (what wins, no git command that changes the
repository, style, usage), except where this file says otherwise. This is a prototype: its code is
not linted, not tested by the suite, and deleted with `scratch/`. Nothing of it enters `napkin/`,
`tests/`, the shared `.venv`, `requirements.lock` or `pyproject.toml`; adopting anything is a separate
step that needs the owner's approval.

## Why

The solve library (`napkin/engine/solve/`, `b1/solve/STATE.md`) gives the selection order of a
declared solver. At A3's network of 30,000 places its two last steps are slow: fair sharing solves
one linear program for each level (459 programs at normal need, 1,287 at need x1.45, 1,779 at x1.7,
150 to 590 s), and the distance step ("nearest the requests") took 350 s and 439 of its 500 Newton
steps at normal need, while its QP fallback (HiGHS) does not finish at that size. The engine's
benchmark at that size did not finish within 45 minutes. The owner's priorities are defensibility,
then speed, then precision (`PLAN.md`, "Changes after G0", 10 and 11): the same run is
deterministic; other settings agree within the stated tolerances.

## What to try

1. **The distance step** with Clarabel, PIQP, and OSQP through `qpsolvers`, against the library's
   method (`distance.py`): the same problem, the least weighted squared distance of the flows to
   their targets on the face that the earlier ranks leave (their rows, bounds and pins), then the
   other unknowns nearest their references. Export that problem from the library at the point
   where `distance` starts, rather than build it again.
2. **Fewer fair-sharing programs** (`fair.py`): split the problem into independent pieces
   (connected parts of the claims and rows) and solve each alone; fix more claims per program (all
   that a program's duals show can rise no more, or a level found by a parametric or bisection
   step); re-solve by the dual simplex after each fixing through `highspy` (HiGHS's own Python
   package, with its model edits), against the library's warm start on SciPy's HiGHS. Each variant
   must give the same fair levels, the selection order of the spec: a change in who is served is a
   change to the language, never a result.

## Problems and checks

- A3's network at 3,000 and 30,000 places (`scratch/rewrite/b1/solve/bench.py`, `--share 0.1` and
  `1.0`; `scratch/rewrite/a3/network.py`), in A3's scenarios: normal, need x1.45, damaged, x1.7.
- The problem that the engine forms. The engine's benchmark (`scratch/rewrite/b1/s5-engine/bench.py`,
  30,000 places) was stopped after 45 minutes still in its first solve, at 0 h and normal supply,
  inside the distance step (`distance.py`, `nearest`, a SuperLU factorization), while the library's
  bench gives the whole order at normal need in about 8 minutes: the engine's problem is harder.
  Export the `Problem` that the engine gives `Solver.solve` at its first solve (the bench wraps that
  call), at 3,000 and 30,000 places, and use it beside the library bench's. Say what makes it harder.
- Correctness first: each method on the spec's cases and on small random cases against the exact
  references of `tests/engine/solve/` (`exact.py`, `cases.py`). Then, at 3,000 and 30,000 places:
  the largest violation of a row or a bound, the change of each kept optimum and fair level, and the
  largest difference of the answer from the library's (flows and levels), each relative to its size.
- Determinism: the same method twice on the same problem with the same thread settings gives the
  same answer. Say for each library whether it is so, and what it needs (threads, options).

## Where and how

- Code and notes in `scratch/rewrite/p1/`; no file over 1 MB there (keep exported problems in
  `/home/user/p1-data/`). State file `scratch/rewrite/p1/STATE.md` (60 lines at most).
- A separate environment outside the checkout: `python3 -m venv /home/user/venvs/p1`, with
  `clarabel`, `piqp`, `osqp`, `qpsolvers`, `highspy`, and numpy and scipy at the versions of
  `requirements.lock`; import the library from the checkout with `PYTHONPATH=/home/user/napkin`.
  Record each package's version, license and the platforms it has wheels for.
- Other agents and test runs share the machine. Set `OPENBLAS_NUM_THREADS=1` and each solver's
  threads to one unless the comparison is about threads; record the load (`uptime`) with each
  timing; take the best of three at 3,000 places; run one 30,000-place case at a time, and stop a
  case at 15 minutes as "did not finish in 15 min".

## Exit

`scratch/rewrite/p1/FINDINGS.md`: a table for each step (method, problem, time, programs or
iterations, largest violation, largest difference from the library and from the exact reference,
deterministic or not), and a recommendation weighed by defensibility, then speed, then precision:
what to adopt, what it would change in the library, its new dependency and license, and what
stays open. Your last message gives the table and the recommendation, 400 words at most.
