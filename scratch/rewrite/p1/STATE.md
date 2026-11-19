# P1 state: other solvers for fair sharing and the distance step (60 lines at most)

Brief `briefs/p1-solvers.md` (+ COMMON-B rules). Prototype: code here, data in /home/user/p1-data
(pickled faces, answers, `*.jsonl` records, `logs/`), environment /home/user/venvs/p1 (numpy 2.5.3,
scipy 1.18.1 as the lock; clarabel 0.11.1, piqp 0.7.0, osqp 1.1.3, qpsolvers 4.13.0, highspy 1.16.0,
qdldl 0.1.9.post1, pytest 9.2.0 to import the tests' helpers). Library measured: `napkin/engine/solve`
of cb6661d (check of each answer, renewal), unchanged since (hash 922afd1210e6 in every record).
FINDINGS.md is refused to a subagent: its text goes in the last message (PLAN.md, "cut off").

## Files
- `lab.py`: problems (bench; the engine's first-solve Problem), `prefix`, `export` (state after the
  objective and at the distance start), `measures` (rows, bounds, optima, levels, invariants, and the
  same after the engine's `polished`).
- `qp.py`: distance candidates through qpsolvers (`-box`: 2nd stage holds flows within 1e-8).
- `ldl.py`: the library's method with qdldl LDL' (pattern analysed once, 2 refinement steps).
- `fairs.py`: fair variants on highspy (`highs-primal`, `highs-dual`, `pieces`); `library` with
  `--tol --fix --updates` patched into `fair`.
- `correct.py`: a method in the library's place on test_spec_answers + test_random + deep sweep
  (827 cases), errors against each test's tolerance (`correct.jsonl`).
- `hybrid.py` (IPM start for the Newton method), `polish.py` (IPM then OSQP's polish): negatives at
  scale. `harder.py`: the engine's form. `same.py`: determinism across processes. `table.py`.
- `exports.sh`, `queue.sh` (+ /home/user/p1-data/queue.txt): 30,000-place runs, one at a time.

## Findings (numbers in the records; see the last message for the tables)
- Engine's form: a store held at [0,0] is two `<=` rows: 30,000 Newton system 316k vs 233k,
  SuperLU 2.79 s vs 0.69 s per factorization; library distance did not finish in 15 min.
- qdldl in the library's method: 827/827 exact cases; 3,000: 1.3-5x faster; 30,000 normal 75 s vs
  342 s (446 vs 447 steps), answers within 6e-7. Best candidate: exact rule, no answer change.
- IPMs: 30,000 normal Clarabel 4.4 s, flows within 9e-6; but sqrt(tol) error at bounds held with no
  multiplier (5e-4 on exact cases, spec pump 6.00017), and non-solved statuses on these faces
  (Clarabel 2nd stage AlmostPrimalInfeasible; engine form fails; PIQP max iterations). OSQP out.
- Engine's polish makes books, equal shares and bounds exact (1e-15) for any answer within 1e-6.
- Fair: highspy = SciPy's HiGHS; dual simplex 2x slower; pieces exact (damaged 3,000: 71 -> 9
  programs); tol 1e-7 keeps levels (<= 3e-11), one of 60 networks stops by name; FIX must stay
  1e-7 (FIX 1e-6 shifts later levels up to 1.5e-3); per-program cost is simplex iterations.
- All methods bitwise deterministic with one thread (PIQP: build chosen by CPU).
- 30,000: engine form, merged rows: library 377 s (455+3), qdldl 81 s; unmerged both DNF 15 min.
  x1.7: every distance variant stops by name (500 or 2,000 Newton steps, then HiGHS's QP says
  infeasible; the face is feasible at 1e-9, "infeasible" to HiGHS at 1e-7). Clarabel fails x1.45,
  x1.7 and the engine's problem (merged too); PIQP ends at its iteration cap everywhere at 30,000.
- Fair 30,000: parts on damaged 693 -> 22 programs, 174 -> 67 s, levels 5e-11; tol 1e-7: renewals
  x1.45 29 -> 0, engine 16 -> 0 (tight 3 -> 0), levels within 7e-8, no claim moved > 1e-6.
- qdldl regularized at -1e-10 (refined against K): SuperLU's answers on bench faces at 3,000, but
  fails the engine's 3,000 face and does not finish 30,000 normal in 15 min: not adopted.

## Remains
- `queue2.txt` (log `logs/queue2.log`): qdldl x1.45 and damaged, highspy normal, fair x1.7 at 1e-7.
- Last message: the summary (400 words) and the FINDINGS.md text.
