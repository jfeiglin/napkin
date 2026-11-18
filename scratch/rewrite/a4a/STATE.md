# A4a state (updated at each milestone; last: tasks 1 and 3 measured, task 2 running)

## Done, and where
- **The transfer across rows IS shown**, three ways. (a) Present engine, each row written out (flat path, one component), with `01_id_column.patch` (links by `table.id`): depot 10 -> 2.5 L, clinic 30 -> 37.5 L, yard 20 L, same after the place rows are reordered. (b) Present table path: refused; with `02_table_path_probe.patch` (two refusals removed) a two-link move runs and is WRONG (10/20/30: debit and credit on one stock). So no small honest change exists. (c) Standalone layout `layout.py` + `lines.py`: same named results, both orders. Script: `t1_transfer.py` (tiny, probe, agree, check, scale, reorder).
- `layout.py` pools/links by id/stores/sparse network; `lines.py` third way (rates held between moments, timeline, stand-in sharing rule); `reference.py` slow second implementation; `model.py` the Place/Route model, CSV writer, old-language text; `record.py` histories as pieces + reductions; `t2_sets.py` (component, sets, sparse); `t3_record.py` (lag, scale, today); `measure.py` runs all and makes `results.md` (written, NOT yet run end to end).
- FINDINGS.md: started, with TODO marks.

## Copies of the package (temporary; `measure.py` makes them again in its OUT/copies)
`/tmp/claude-0/-home-user-napkin/e09158c7-7039-5d6d-be85-61b3a193adaf/scratchpad/a4a/`: `base` = git archive of /home/user/napkin-base; `pkg` = base + 01_id_column.patch; `probe` = base + 02_table_path_probe.patch; `out`, `out1` = JSON results so far.

## Decisions (one line each)
- No table-path fix: the model of representatives names both ends `places_1.stock` (hybrid.py:229-234, plan.py:496-509, 703-709, run.py:2064-2080); a link-aware reference form is the rewrite itself.
- Rows in memory in the order of their ids, not of the file: a reordered file gives the same bits.
- Sharing at a bound in `lines.py` is a stand-in (local proportional, largest fixed point); A3's solve library replaces `Lines.share` only.
- A set is of stores and flows, not of whole members; a tally (no reachable bound) does not join the flow into it.
- Record = pieces (t, y, rate) per stored value + trace; reductions can be made after the run from the record of everything.
- Old model for comparisons needs `size 1000 L` and a share limit that never binds; a limit of 1e6 L/h made the tolerance 0.03 L (size = limit x horizon) and froze a stock at 0.0246 L.

## Numbers so far (all: `/home/user/napkin/.venv/bin/python <script> <part> OUT ...`, load 1 to 6)
- `t1_transfer.py agree` (PYTHONPATH=pkg): layout vs present engine, ring-free networks 30/100/300 places: largest difference 1.1e-13 / 1.7e-13 / 5.7e-13 L; with rings (30 places) 143.6 L (the present engine solves an LP in a ring; the stand-in rule differs).
- `t1_transfer.py check`: lines vs reference with rings: 5.5e-11 L (300 places), 4.3e-11 L (3,000).
- `t1_transfer.py scale OUT 30000 35000`: build 0.12 s, start 0.075 s, run to 48 h 1.42 s, 50,302 moments (15,325 stocks empty, 34,977 moves), 28 microseconds a moment, total conserved to 0.0 L of 3,305,805 L, 156 MB peak, 3,384 connected sets (plain rule), largest 52,038 stores.
- `t1_transfer.py reorder OUT 30000 35000`: id order: 0 of 60,000 named values differ in any bit; file order: 2,929 differ, at most 1.35e-13 L.
- Today's table path, its own model (scratch/networks/baseline.py 30000 35000 35000 spread, PYTHONPATH=base): compile 2.0 s, plan 0.07 s, run 5.4 s for 35,000 events (153 microseconds a moment).
- `t2_sets.py component OUT KIND P` (PYTHONPATH=pkg; horizon 300 h): constant 30/100/300 places: run 0.08/0.86/12.3 s, 0.31/1.3/10.4 ms per evaluation of the rates, peak memory 119/157/864 MB; constant with rings, 30 places: 21 linear programs, 0.56 s of a 0.60 s run; 300 places with rings: no result after 10 min (still running). linear/saturating/target: 3 places 0.30-0.35 s, 10 places 0.37-0.47 s, 30 places 1.5-1.8 s, 100 places 8.2/10.7/16.8 s (17k-23k evaluations).
- `t2_sets.py sets OUT 30000 35000`: refined rule: 33,384 sets (32,948 a store alone, 435 small sets with 1,033 stores, 1 set of 26,019 stocks); plain rule 3,384 sets, largest 52,038 stores; cut 0.01-0.05 s.
- `t2_sets.py sparse OUT 3000 3500` (PYTHONPATH=base): smooth requests reading a stock, SciPy Radau with a sparse pattern: 303 steps, 2,604 evaluations, 12.9 s at load 6 (one evaluation 0.04 ms: the time is elsewhere; being profiled); one LP at a state with 1,548 resting stores 0.015 s; stand-in sharing 0.8 ms. 30,000 places NOT yet run.
- `t3_record.py scale OUT 30000 35000`: run 1.38 s with no record; +2.7 s with 8 reductions + 5 rows; +3.5 s with 10 reductions (87,569 pieces, 1.65 MB, 1.21 MB packed); +0.29 s with every store and flow (324,857 pieces, 6.05 MB, 2.70 MB packed). Reductions made after the run from the record of everything: ten at three times 27 ms; two whole sum histories 23 ms; agree to 2.5e-14. Recording changes no bit of the run.
- `t3_record.py today OUT` (PYTHONPATH=pkg): Trajectory pickle+zlib 58 KB / 573 KB / 8.0 MB at 30/100/300 places; table path `record=True` at 35,000 routes: run 5.37 -> 5.48 s, 175,000 + 35,000 log entries, 39 MB; report with a uniform lag at one time: 0.026 s (350 routes), 1.66 s (3,500), 35,000 still running.

## Taken over at 18:15 (second agent)
- `batch1.sh` stopped by hand at 18:15: the component of 300 places with rings had run 13 min with no result (the finding). The moving kinds at 300 and constant at 1000 were not run (not needed for a ruling).
- `today` finished: lag report at one time on the table path, 35,000 routes: 202 s (350: 0.026 s, 3,500: 1.66 s): grows about as the square.
- `t2_sets.py sparse OUT 30000 35000` (PYTHONPATH=base, load 1.5-3.5): integration 36.0 s (best of 3), 302 steps, 2,784 evaluations at 0.52 ms (1.4 s of it), 35 Jacobians, 72 factorizations, 368 MB; at its rest state 15,311 resting stores, stand-in sharing 40 ms, one LP 0.23 s; estimates with a sharing at each evaluation 111 s, with an LP 0.18 h. JSON in out/sparse_30000_35000.json.
- Cause of 12.9 s at 3,000: threaded BLAS on the small n-by-3 products of Radau's collocation step, slowed by other load (profile: `ndarray.dot` 2.0 s of 4.0 s). With OPENBLAS_NUM_THREADS=1: 1.65 s total. A one-thread run at 30,000 writes out3/.
- measure.py: NOT run end to end (main session runs it). Step 2 = check that it starts.

## Remaining, in order
1. Finish task 2 numbers (components at 300 places for the three moving kinds, constant 1000, sparse at 30,000).
2. Run `measure.py OUT` once end to end (about an hour); copy `OUT/results.md` and the JSON files into this folder (`results.md`, `results/`).
3. Complete FINDINGS.md: results tables, rulings (layout; connected sets; limits and messages; record; reuse of a stored run; order of rows; rings), layout note, not covered.
4. Final message to the main session (300 words).

## Facts in no file yet
- The flat structure refuses a list over more than 150 instances (`output:/held: the expression has more than 150 operations one inside the other`), so `sum(Place.stock)` cannot be an output above 150 rows; the old model uses `places.1.stock`.
- Naming one row in the file (`places.1.stock`) makes that row a class of one in the hybrid core and changes the probe; the probe uses `sum(Place.stock)` with 3 places.
- The trial patch of scratch/networks gives `KeyError 'places_2.stock'` on a two-link move.
- `Extreme` (max/min history) needs a `bound` for a least value that sits on the lower bound, else two passes over the rows at each depletion.
- Maintaining reductions in the run costs more in this Python prototype than recording everything; an hourly reading that changes every row would make the record of everything large (rows x moments), so a budget in pieces is the proposed rule.
