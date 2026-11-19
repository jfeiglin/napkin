# E3: triggers on values that turn (PLAN "Changes after G0", item 20)

Brief: the coordinator's message, with `briefs/COMMON-B.md`. Owned: timeline/triggers.py,
component.py, sparse.py, engine/continuous/, new files in tests/engine/.

## Before (measured once; other agents' work in progress failed 51 engine tests then)
- bench.py 3000 48 12: run+record 55.8 s. Slowest: estimators 12.6 s, long_steps crossing 10.7,
  pulse 10.5, roundoff[6] 5.7, solvers tanks 5.6, checkpoints[tapering] 5.0 s.

## Design (docstrings hold it: continuous/dense.py, triggers.py "Values that turn")
- The bound is the dense output's own form (`dense.Motion`: value and rate at a piece's start,
  `spread` = most the rate moves, `change` = most the sum moves, `size` for roundoff, `margin` for
  what the run reads). A Radau step: its collocation cubic, exact (spread (2|c2|+3|c3|)/l, change
  |c1|+|c2|+|c3|). The closed form of compartments: y' = expm(A t) y'(s), |expm(A t)| <= exp(m t)
  (m = log norm), |expm(A t) - I| <= exp(|A| t) - 1, and a weighted sum through A^T w (a conserved
  sum, A^T w = 0, holds). Lines via `ways.linear`.
- ComponentWay and Sparse: `breaks(start, end)` (step ends), `motion(weights, start, end)`; and
  `level_at` past the present time with no segment made (a moment) follows `drift`, the present
  rate: "just after" reads (near-ties, rearm) were frozen on curves, which marked every crossing
  of a curve as a near-tie.
- triggers `_contact`: d = left - right, affine in what moves (`_weights`); its answer within its
  band b changes only where d crosses -b (ge, lt, eq, ne) or +b (le, gt, eq, ne). Per piece: skip
  if each edge is farther than change + 2 margin + roundoff (d at the piece start from the form,
  no read); else if the rate keeps its sign the ends decide, bisection to the crossing tolerance;
  else halve. A contact is at least the crossing tolerance after now. Removed: `_certified`,
  `_monotone`, `_signs`, `_search` (monotone-only, sampled).
- Refused by name: a rate of a set on a curve, a side not affine in what moves, a store of a way
  with no form (moving declared solver; not if alone and monotone), over 4096 halvings of a step.

## Done
- Code: continuous/dense.py (new), component.py, sparse.py, triggers.py, continuous/__init__.py.
- Tests: test_turning_values.py (12); updated (were refusals): test_monotone_crossing (crosses 60
  at 10 ln 5 h), test_continuous_domains (breach at the root of 10 t e^-t = 3).
- The reservoir runs: opens at 40 h (fires at 40 - 3.4e-8 h), water 0.4, spilled 0.5 at 120 h.

## For the owner of tests/model (not my files)
- tests/model/test_material.py::test_a_sum_of_stores_whose_total_moves_both_ways_is_not_certified
  now fails by design: item 20 certifies it. The books' total T = waiting + served has
  T - 1000 = 2000 (e^0.05t - 1) - t; the assertion fails at the root of T - 1000 = 0.001 + 1e-7
  (the band), 1.0102e-5 h (the run: 1.01042e-5 h, within the crossing tolerance). The comment
  above BOOKS names `_monotone`, which is gone.

## For E1
- declared.py `MovingDeclared`: give it `breaks(start, end)` (its OdeSolution's `ts` inside) and
  `motion(weights, start, end)` (`continuous.dense.of_step` on the interpolant of the piece), as
  `Sparse` has; until then a condition on its stores that turn is refused by name, unless it reads
  one store that only rises or only falls.
- Not from this change: a sparse set whose store decays toward 0 (the reservoir of
  test_turning_values on `sparse` to 1000 h, no trigger) raises numpy LinAlgError in
  selection._exact via network._general (after an overflow at selection.py:421), uncaught by the run.

## After (measured once)
- bench.py 3000 48 12: run+record 54.3 s (load 2.4-3.3): the same (its clocks are on lines).
- Slowest: estimators 11.3 s, long_steps pulse 10.1 s, crossing 9.7 s, checkpoints[tapering]
  7.1 s (no condition there: load), roundoff[6] 5.6 s, solvers tanks 5.2 s; new resume tests 5.7
  and 3.7 s. A curve's extra moments cost a new segment each (the rest of the window again).
- `-m deep tests/engine/test_occurrences.py`: 2000 passed (99 s).
- Final: core, program, reference, engine -n 2: 3456 passed (161 s). ruff clean.

## Status: done
