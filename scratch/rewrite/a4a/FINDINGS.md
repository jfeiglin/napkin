# A4a findings: the engine at scale

Brief: `briefs/a4a.md`. The state of the work, and every number with its command: `STATE.md`. The
tables of the measured files: `results.md` (made from `results/*.json`).

## 1. Summary

1. A real transfer across rows is shown. One route row moves 2 L/h and a lot of 1.5 L from the
   stock of its origin row to the stock of its destination row. The right two stocks change (depot
   10 to 2.5 L, clinic 30 to 37.5 L, yard stays 20 L). The results are the same after the place
   rows are reordered (T1.1).
2. The present engine runs this only with each row written out (one component). The table path
   cannot run it after a small honest change. With two refusals removed it runs a move between two
   linked stocks and moves nothing (T1.2). So the layout of this folder is the proposal.
3. The layout (pools of rows, links as columns of row numbers, one sparse network) runs 30,000
   places and 35,000 routes. It takes 0.12 s to build and 1.4 s for 50,302 moments. The total is
   conserved exactly. Rows kept in the order of their ids give the same bits after a reorder (T1.5, T1.6).
4. The refined rule for connected sets puts 32,948 of 60,000 stores on arrays. The plain rule puts
   none there (T2.1).
5. One component of the present general tier is acceptable up to about 150 stores. At 600 stores it
   takes 12 s and 864 MB with constant requests. With a ring it gives no result in 13 minutes (T2.2).
6. A request that reads a moving stock costs 8 to 17 s at 200 stores in a component. In a set of
   60,000 stores the sparse integration takes 31 to 36 s, and only while no stock rests on its
   bound. With a sharing at each evaluation it takes 1.5 min (stand-in rule) to 10 min (one linear
   program). The first version refuses it (R-A4a-05).
7. A record of histories (pieces) for every store and flow of the 30,000-row run is 6 MB and adds
   0.1 to 0.3 s. Ten reductions made later from that record take 27 ms. Today, a lagged report on
   the table path takes 202 s at 35,000 routes (T3.2, T3.3).

## 2. What was done

All commands use `/home/user/napkin/.venv/bin/python` from any folder. `OUT` is a folder of your
choice. Each part writes `OUT/<part>….json`, and each JSON file holds the load of the machine.

| File | What it is | How to run |
| --- | --- | --- |
| `01_id_column.patch` | Copy of the package: a table cell `places.depot` links by the column `id` (spec:795). Needed so that the present engine can run the tiny model with the rows reordered | applied by `measure.py`; or `patch -p1` in a copy |
| `02_table_path_probe.patch` | Removes two refusals of the table path (`plan.py:493-501`, `run.py:2080`). It is a probe, not a fix | the same |
| `layout.py` | Pools, links by id, stores, sparse network (layout note, §3.4) | library |
| `lines.py` | The third way: rates found at each moment and held between moments, a timeline of moments, local updates. The sharing at a bound is a stand-in | library |
| `reference.py` | A slow second implementation of `lines.py`, for checks | library |
| `record.py` | Histories as pieces, reductions kept in the run, the recorder | library |
| `model.py` | The place-and-route model: new-language text (a comment), CSV writer, old-language text for the present engine, random networks | library |
| `t1_transfer.py` | Task 1: `tiny`, `probe OUT`, `agree`, `check`, `scale OUT P R`, `reorder OUT P R` | `PYTHONPATH=<copy with 01> … t1_transfer.py tiny OUT` (see its head) |
| `t2_sets.py` | Task 2: `component OUT KIND P [rings] [runs]`, `sets OUT P R`, `sparse OUT P R` | `component` needs the copy with 01, `sparse` the base |
| `t3_record.py` | Task 3: `lag OUT`, `scale OUT P R`, `today OUT [quick]` | `today` needs the copy with 01 |
| `measure.py` | Runs every part and writes `OUT/results.md` | see below |
| `results/`, `results.md` | The JSON files of this work, and their tables | `measure.py results --tables` makes `results.md` again |

**How to run `measure.py`.** Run it alone on the machine:

    cd /home/user/napkin/scratch/rewrite/a4a
    /home/user/napkin/.venv/bin/python measure.py /some/new/folder          # everything
    /home/user/napkin/.venv/bin/python measure.py /some/new/folder --quick  # leaves out the slow cases
    /home/user/napkin/.venv/bin/python measure.py /some/new/folder --only t2-sparse
    /home/user/napkin/.venv/bin/python measure.py /some/new/folder --tables # tables from the JSON only

It makes three copies of the package in `OUT/copies` (`git archive` of `/home/user/napkin-base`,
which changes nothing), applies the two patches, and runs 14 steps plus 23 component cases, each
in its own process with a time limit. I checked only that it starts: `--only t1-tiny --only
t1-probe` made the copies and ran both parts in 4 s with the right results. I did not run it end to
end.

How long it takes, estimated from the single parts: the steps other than the components take about
10 minutes (the 30,000-place sparse run is 1 min 40 s to 2 min for its three runs, and the lag of
today's table path at 35,000 routes is about 3.5 min). The components up to 100 places take a few
minutes. Five cases can each run up to their limit of 1,500 s: constant with rings at 300 places,
constant at 1,000 places, and the three moving kinds at 300 places. So a whole run takes from about
one hour to about 2.5 hours. `--quick` leaves out those five and the 300,000-place run; I estimate
10 to 15 minutes for it, but I did not time it. Set `OPENBLAS_NUM_THREADS=1` for the run: under load,
threaded BLAS made the 3,000-place sparse run 12.9 s in place of 1.4 to 1.7 s (§3.2).

## 3. Results

Times are the best of three runs unless a table says one run. The machine has 4 cores and other
agents used it. The load is in each JSON file (1 to 6).

### 3.1 Task 1: the transfer across rows

**T1.1** The tiny model (`t1_transfer.py tiny`, copy with 01). Places depot 10 L, yard 20 L,
clinic 30 L. One route `depot_clinic`, 2 L/h, and a lot of 1.5 L at 1 h.

| rows of places.csv | t (h) | depot | yard | clinic | present engine (rows written out) | layout |
| --- | --: | --: | --: | --: | --- | --- |
| file order | 0 / 1 / 3 | 10 / 6.5 / 2.5 | 20 / 20 / 20 | 30 / 33.5 / 37.5 | same | same |
| clinic, depot, yard | 0 / 1 / 3 | 10 / 6.5 / 2.5 | 20 / 20 / 20 | 30 / 33.5 / 37.5 | same | same |

**T1.2** The table path of the present engine (`t1_transfer.py probe`): stocks of three places at 3 h (L).

| case | expected (= rows written out) | table path, base | table path, with the probe patch |
| --- | --- | --- | --- |
| one link, a flow out of the linked stock | 4, 20, 27 | refused: "the flow routes_1.carried, which joins two spaces" | refused, the same |
| one link, a move out of the linked stock | 8.5, 20, 27.5 | refused: "flows or transfers that connect quantities of two families" | right |
| two links, a move between the linked stocks | 11, 17.5, 31.5 | refused: "two links of routes_1 into one class" | **WRONG: 10, 20, 30** |
| two links, a flow between the linked stocks | 7, 17, 36 | refused: "Competing withdrawals require one explicit allocation policy" | refused, the same |

What blocks it: the model of representatives gives a template one representative row. Both ends of
a two-link move are then named `places_1.stock`, so the debit and the credit fall on one stock
(`model/hybrid.py:229-234`, `timeline/plan.py:496-509`, `:703-709`, `timeline/run.py:2064-2080`).
A reference form that knows links is the rewrite itself, not a small change.

**T1.3 and T1.4** Two checks on random networks:
- Layout against the present engine (one component, `agree`). Without rings, at 30, 100 and 300
  places, the largest difference of a store is 1.1e-13, 1.7e-13 and 5.7e-13 L. The present engine
  takes 14.1 s at 300 places. With rings (30 places) the difference is 144 L. The present engine
  solves a linear program in a ring, and the stand-in rule of `lines.py` gives other rates. That is
  a difference of rules: A3 sets the rule, not this layout.
- Layout against `reference.py` with rings (`check`): 5.5e-11 L at 300 places and 4.3e-11 L at
  3,000 places.

**T1.5** At scale (`scale OUT 30000 35000`, no package): 60,000 stores and 65,000 flows; tables
2.6 MB; build 0.12 s; start 0.075 s; run to 48 h 1.42 s; 50,302 moments (15,325 stocks empty,
34,977 moves, 143,921 lines start again); 28 µs per moment; total at 48 h less total at 0 h is
0.0 L out of 3,305,805 L; peak 156 MB. Today's table path on its own model of the same size
(`scratch/networks/baseline.py 30000 35000 35000 spread`): compile 2.0 s, plan 0.07 s, run 5.4 s
for 35,000 events (153 µs per moment). It cannot run the transfer (T1.2).

**T1.6** Both files with their rows in another order, 60,000 named values compared bit for bit:

| order of the rows in memory | values with other bits | largest difference (L) |
| --- | --: | --: |
| the order of the ids | 0 | 0 |
| the order of the file | 2,929 | 1.35e-13 |

### 3.2 Task 2: connected sets and the three ways

**T2.1** The cut of the 30,000-place model (`sets OUT 30000 35000`). A component has at most 150
stores. The cut takes 0.01 to 0.05 s.

| case | sets | largest set (stores) | arrays | one component | lines | refused |
| --- | --: | --: | --- | --- | --- | --- |
| refined rule, no rate reads a moving value | 33,384 | 26,019 | 32,948 sets / 32,948 stores | 435 / 1,033 | 1 / 26,019 | 0 |
| plain rule (a flow always joins both ends) | 3,384 | 52,038 | 0 | 3,383 / 7,962 | 1 / 52,038 | 0 |
| each route's request reads its origin's stock | 33,384 | 26,019 | 32,948 / 32,948 | 435 / 1,033 | 0 | 1 / 26,019 |
| each route's request reads a third place's stock | 30,948 | 29,045 | 30,943 / 30,943 | 4 / 12 | 0 | 1 / 29,045 |
| one solver sets the rate of every route | 32,949 | 27,052 | 32,948 / 32,948 | 0 | 1 / 27,052 | 0 |

**T2.2** One set as one component of the present general tier (`component`, copy with 01, horizon
300 h). There are two stores per place (the stock and the tally `used`).

| request of a route | places | stores | run (s) | evaluations | ms per evaluation | of it in the allocation | linear programs | peak MB |
| --- | --: | --: | --: | --: | --: | --: | --: | --: |
| constant | 30 | 60 | 0.078 | 87 | 0.31 | 88% | 0 | 119 |
| constant | 100 | 200 | 0.86 | 243 | 1.3 | 94% | 0 | 157 |
| constant | 300 | 600 | 12.3 (1 run) | 702 | 10.4 | 99% | 0 | 864 |
| constant, rings | 30 | 60 | 0.60 | 78 | 7.6 | 99% | 21 (0.56 s) | 120 |
| constant, rings | 100 | 200 | 0.99 (1 run) | 258 | 1.5 | 94% | 0 (no ring rested) | 160 |
| constant, rings | 300 | 600 | **no result after 13 min** (stopped) | | | | | 880 |
| linear, saturating, target | 3 | 6 | 0.30 to 0.35 | | | | | |
| the same | 10 | 20 | 0.37 to 0.47 | | | | | |
| the same | 30 | 60 | 1.5 to 1.8 | | | | | |
| the same | 100 | 200 | 8.2 / 10.7 / 16.8 | 17k to 23k | | | | |

The moving kinds (`linear`: `pull * origin.stock`; `saturating`: `rate * stock / (stock + half)`;
`target`: `max(0 L, goal - destination.stock) / lag`) come from exploratory runs (one run each,
`work/try11.py` in the temporary folder, PYTHONPATH = copy with 01). They have no JSON file;
`measure.py` makes them again. I did not run the moving kinds at 300 places or the constant at
1,000 places. The dense matrix is built at `continuous/system.py:152`. At 60,000 stores it would be
28.8 GB.

**T2.3** A large set whose requests read a stock (`sparse OUT 30000 35000`, base). Each request is
`rate * stock / (stock + half)`, and no stock reaches its bound. SciPy Radau with the sparse
pattern of the Jacobian:

| | 3,000 places | 30,000 places | 30,000 places, one BLAS thread |
| --- | --: | --: | --: |
| stores / Jacobian nonzeros | 6,000 / 9,500 | 60,000 / 94,998 | the same |
| one evaluation of the rates | 0.042 ms | 0.52 ms | 0.59 ms |
| integration to 48 h | 1.38 s | 36.0 s | 30.7 s (1 run) |
| steps / evaluations / Jacobians / factorizations | 303 / 2,604 / 32 / 68 | 302 / 2,784 / 35 / 72 | the same |
| stores at rest at 48 h on lines (the state of the next rows) | 1,548 | 15,311 | |
| one sharing at that state, stand-in rule | 0.83 ms | 40 ms | 33 ms |
| one linear program at that state, HiGHS | 0.015 s | 0.23 s | 0.20 s |
| estimate: a sharing at each evaluation | 2.2 s | 111 s | 92 s |
| estimate: a linear program at each evaluation | 37 s | 0.18 h | 0.16 h |
| peak memory | 137 MB | 368 MB | 359 MB |

The 12.9 s recorded earlier at 3,000 places (STATE.md) has a found cause. Threaded BLAS ran the
small n-by-3 products of Radau's collocation step on a loaded machine. In the profile `ndarray.dot`
took 2.0 of 4.0 s. With `OPENBLAS_NUM_THREADS=1` the run takes 1.65 s (`work/prof1.py`). At 30,000
places one thread gains only 15%. The rest of the time is in the sparse factorizations and solves;
I did not profile it at that size.

### 3.3 Task 3: what a run records

**What the present engine holds.** `Trajectory` (`engine/runtime.py:79-91`) holds the dense
segments of the solution and a copy of the whole state before and after each step
(`_snapshots`, `_steps`). A report reads any named value at any time from it. The table path keeps
an undo log of old values and old lines when it runs with `record=True` (`timeline/reports.py:10`,
`:50`). A report then reads a value at a time by replaying it.

**T3.3** The size of what is kept today (`today OUT`, copy with 01):

| | 30 places | 100 places | 300 places |
| --- | --: | --: | --: |
| `Trajectory`, pickle with zlib | 58 KB | 573 KB | 8.0 MB |
| copies of the state | 100 | 314 | 935 |

The size grows about as the square of the rows. At 30,000 places that would be about 80 GB. This is
an extrapolation, not a run. The table path with 35,000 routes: the run takes 5.37 s, or 5.48 s with
`record=True`. The record has 175,000 old values and 35,000 old lines (39 MB), plus a 28 MB trace. A
report of one output at three times, without a lag, takes 0.03 s. **The same output with a uniform
lag, at one time: 0.026 s at 350 routes, 1.66 s at 3,500, 202 s at 35,000.** That also grows about
as the square.

**T3.1** Readings are not enough (`lag OUT`). A tank gets 8 L at 7 h in one history and at 9 h in
the other. Read at 0, 6 and 12 h, both histories give 0, 0 and 8 L. Their means over the window from
6 to 10 h are 6 L and 2 L. A lag over a window must read the history, not the readings
(`engine/report.py:164`).

**T3.2** The record of the 30,000-row run (`t3_record.py scale OUT 30000 35000`; one run at load
5.4. STATE.md has an earlier run at a lower load with +2.7, +3.5 and +0.29 s.)

| what the run records | run to 48 h (s) | added (s) | pieces | bytes as arrays | bytes packed (zlib) |
| --- | --: | --: | --: | --: | --: |
| nothing | 1.54 | | | | |
| 8 reductions (no greatest, no least) and 5 rows | 3.99 | 2.45 | 87,538 | 1,651,120 | 1,209,778 |
| 10 reductions and 5 rows | 4.90 | 3.36 | 87,569 | 1,651,864 | 1,211,058 |
| every store and every flow | 1.64 | 0.095 | 324,857 | 6,050,512 | 2,702,960 |

- Recording changes no bit of the run.
- Made after the run from the record of everything, the ten reductions at three times take 27 ms
  and the whole histories of two sums take 23 ms. They agree with the reductions kept in the run to
  2.5e-14 (relative).
- A report from the histories kept in the run (ten values and one lag, at three times) takes 2.7 ms.
- The greatest and the least need a `bound` hint, or they make passes over the rows: 29 passes for
  the greatest and 414 for the least.

## 3.4 Layout note: the arrays, the indexes, and the planner

**Arrays** (`layout.py`):
- `Pool`, one for each template: `n` rows, the `ids`, `row_of` (id to row), the creation number of
  each row (its place in the file). Each field is a column over the rows. A number column is
  float64 in canonical units. A link field is an int32 column of row numbers in the target pool,
  found once from the ids. A missing or repeated id is a setup error that names the table, the row
  and the cell (spec:795).
- Rows are in the order of their ids (`layout.py:105`). A table with no `id` column keeps the
  order of its file.
- `Stores`: every stored quantity of the model is one place in one float64 vector `y`. The field
  `f` of row `k` of pool `p` is at `offset[p, f] + k`. Next to it are the vectors of the lower and
  upper bounds and of the size (the tolerance is 1e-10 times the size).
- `Network`: for each flow `f`, `src[f]` and `dst[f]` are store places, or -1 for SOURCE or SINK.
  Each flow also has its owner (pool, row). A flow template over a pool gives one flow per row, so
  its places are `offset[p_origin, stock] + origin_column`, a gather through the link column.

**Indexes:**
- `B`: sparse incidence, stores by flows, -1 at the source and +1 at the sink.
- `out_of` and `into`: the same by store (CSR). They answer "the flows out of this store".
- For each link column, its reverse as CSR: the rows that link to a row.
- For each flow, the store places that its request, capacity or factors read. This comes from the
  expression, evaluated as columns over the rows of the pool (`layout.request_values`).

**From a model to the three ways:**
1. Read each table into a pool, resolve the links, and build `Stores` and `Network`. This takes
   0.12 s at 30,000 rows.
2. Mark each value that a rate reads as *moving* or not. A stored value with a possible nonzero
   rate between moments is moving. An input, a start value, or a keyed reading that changes at
   known times is not.
3. Cut the stores and flows into connected sets with the refined rule (R-A4a-03). This is one call
   of `scipy.sparse.csgraph.connected_components` over stores and flows, 0.01 to 0.05 s.
4. Give each set a way (R-A4a-04):
   - **arrays**: a store alone, or with one flow. Like rows run together as columns. Each row is a
     line between moments.
   - **one component** of the continuous engine: a set of at most 150 stores. Its rates are
     evaluated at trial states (spec:489), with the dense matrix and the allocation inside.
   - **lines**: a larger set in which no rate reads a moving value. The rates come from the sparse
     solver at each moment and are held between moments. A moment updates only what the change
     reaches (`lines.py`).
   - **refused**: a larger set in which a rate reads a moving value (R-A4a-05).
5. Attach the recorder to each set (R-A4a-07). All sets share one timeline of moments. A moment of
   one set does not touch another set.

## 4. Rulings

### R-A4a-01: The layout of links and flows across tables  [technical]
Rule: each template is a pool of rows. A link is an int32 column of row numbers, resolved once from
the `id` column. Every store is one place of one vector. A flow names its two ends by those places
(-1 for the outside). The incidence is a sparse matrix, with CSR indexes by store and the reverse
of each link. Requests are evaluated as columns over the rows, through gathers on the link columns.
Alternative: today's model of representatives, in which one row stands for its template and a flow
between tables joins classes (`model/hybrid.py:229-234`). Or every row written out as its own
member, the flat path.
Example: places depot 10 L, yard 20 L, clinic 30 L; one route depot -> clinic at 2 L/h, with a lot
of 1.5 L at 1 h, and in T1.2 a move between the two linked stocks of one route row.
- Rule: the debit and the credit fall on the two linked rows (T1.1: depot 2.5 L, clinic 37.5 L at
  3 h). 30,000 places run in 1.4 s.
- Alternative (representatives): both ends are `places_1.stock`. It refuses the case, or, with the
  probe patch, gives 10 / 20 / 30 L in place of 11 / 17.5 / 31.5 L (T1.2).
- Alternative (flat): the right numbers, but one component. It takes 14 s at 300 places and cannot
  hold 30,000.
Recommendation: adopt this layout for the new engine. Do not port the table path's machinery of
families and classes.

### R-A4a-02: The order of rows in memory  [technical]
Rule: the rows of a pool are kept in the order of their ids. A table without an `id` column keeps
the order of its file. Reports and messages still name rows by id and list them in the order of
the file.
Alternative: keep the order of the file in memory.
Example: the 30,000-place model, with both files written again with their rows shuffled.
- Rule: 0 of 60,000 named values differ in any bit (T1.6).
- Alternative: 2,929 values differ, by at most 1.35e-13 L. The sums and the sharing add in another
  order. A test such as `stock <= 0 L`, or the time at which a stock empties, can then fall on the
  other side of a moment.
Recommendation: order by id. Moving the rows of a table is then not a change of the model, and a
stored run stays valid (R-A4a-08).

### R-A4a-03: What joins two members into one connected set  [technical]
Rule: a set is made of stores and flows, not of whole members. These join:
- (a) a flow and the store at an end that can hold it back: the store has a bound that it can reach
  on that side (a lower bound at the source, an upper bound at the sink), or the endpoint scope has
  a `capacity`, a `request` or an `allocation`. An endpoint that shares joins all the flows at it.
- (b) a flow and every stored value that its request, capacity or factor reads, when that value
  moves between moments. This holds also when the value is on another member.
- (c) all the flows whose rates one solver sets (`solve_for`).
- (d) all the legs of one flow with legs.
- (e) both ends of a reversible flow, always, since both ends must be stocks (spec:184).
A store that cannot hold a flow back, such as a tally with no reachable bound and no endpoint
limit, does not join the flow into it. It only integrates the rate that it is given. A read of a
value that does not move (an input, a keyed reading at known times) joins nothing.
Alternative: the plain rule. A flow always joins both its ends, and any read joins.
Example: each place has a stock and a tally `used`, with `flow use: this.stock -> this.used` and a
route network between the stocks (30,000 places, 35,000 routes, T2.1).
- Rule: 33,384 sets. 32,948 stores run alone on arrays, 435 small sets (1,033 stores) run as
  components, and one set of 26,019 stocks runs on lines.
- Plain rule: 3,384 sets. The largest has 52,038 stores, and no store runs on arrays.
- If each route's request reads its origin's stock, the large set is refused under both rules.
- If one solver sets every route, the rule gives one set of 27,052 stores, on lines.
Recommendation: adopt the refined rule. It costs nothing (the cut takes 0.05 s) and keeps tallies,
counters and spent totals out of the coupled sets.

### R-A4a-04: Which way a set runs, and the measured limit of each  [technical]
Rule: a store alone, or with one flow, runs on **arrays**. A set of at most 150 stores runs as **one
component** of the continuous engine. A larger set runs on **lines** when no rate in it reads a
moving value, and is refused otherwise (R-A4a-05). A set with a ring of stocks that can rest on
their bound runs on lines whenever nothing in it moves, whatever its size. It runs as a component
only when a rate moves, and only up to 150 stores.
Measured limits:
- Arrays and lines: 60,000 stores and 65,000 flows take 1.4 s for 50,302 moments, 28 µs a moment,
  156 MB (T1.5). The 300,000-place case is in `measure.py`, not run.
- One component with constant requests: 60, 200 and 600 stores take 0.08, 0.86 and 12.3 s, at
  0.31, 1.3 and 10.4 ms per evaluation. The allocation takes 88 to 99% of it. 600 stores take
  864 MB.
- One component with moving requests: 200 stores take 8 to 17 s for 300 h.
- What a ring costs in a component: while a ring rests, each evaluation solves a linear program.
  At 60 stores that is 21 programs, 0.56 s of a 0.60 s run, and 7.6 ms per evaluation in place of
  0.31 ms. At 600 stores there was no result in 13 min. On lines a ring is solved once a moment
  (3,000 places with rings agree with `reference.py` to 4.3e-11 L).
Alternative: put every set that fits in memory on the component, as the general tier does today.
Example: 300 places in rings, with constant requests (600 stores). The rule runs it on lines, as
`check` did at 300 places with rings. That part of `check` was not timed alone; a lines run of 100
times as many rows takes 1.4 s. The alternative gives no result in 13 min (T2.2).
Recommendation: set the limit at 150 stores, keep it as one constant of the planner, and send rings
to lines. Measure again on the new component once A3's solve replaces the allocation.

### R-A4a-05: What the engine refuses at scale, and the message for each  [owner]
Rule: in the first version, the engine refuses these before the run:
1. **A rate that reads a moving value, in a set of more than 150 stores.** Message:
   `routes.r00031.carried: its request reads places.p00007.stock, which changes between moments.
   The flow is in a connected set of 26,019 stores (more than 150), whose rates are held between
   moments. Make the request read a value that changes only at moments (an input, a reading, a
   value set by an event), or cut the set: <the flows that join it, at most five>.`
2. **A ring that must run as a component above 150 stores** (a ring in a set with a moving rate).
   This is refusal 1, and the message adds:
   `the set holds a ring of stocks that feed one another: places.p00012.stock -> places.p00040.stock
   -> … -> places.p00012.stock`.
3. **A record beyond its budget**: the request names more pieces than the budget allows
   (R-A4a-07). Message: `the request names about 263,000,000 pieces (30,000 rows read every hour
   for a year); the budget is 10,000,000. Name fewer rows, a reduction over the table, or a coarser
   reading.`
Nothing else is refused at 30,000 rows. A sum over a table is a reduction over a column. So the
present limit of 150 nested operations (`output: the expression has more than 150 operations one
inside the other`) does not exist in the new engine.
Alternative: run a moving request in a large set with the sparse integrator.
Example: 30,000 places whose routes ask `rate * stock / (stock + half)` (T2.3).
- Rule: refused, with message 1.
- Alternative: 31 to 36 s while no stock rests, which is 25 times the run on lines. Once stocks
  rest, the run needs a sharing at each evaluation: an estimated 1.5 min with the stand-in rule,
  and 10 min with one linear program for each evaluation. A3's ranked solve costs more than that.
Recommendation: refuse in the first version, with these messages. The sparse integrator is a
measured candidate for a later version, only for sets in which no store rests on a bound.

### R-A4a-06: A request that moves continuously, small set against large  [owner]
Rule: in a set of at most 150 stores, a rate may read any moving value, and the set runs as one
component. Above that size it is refused (R-A4a-05). This closes the spec's open item
"Continuously changing inputs" (spec:819) with these numbers. A keyed hourly reading is not moving:
it changes at known moments and runs on lines.
Alternative: allow moving values at any size and let the run be slow.
Example: the `target` request `max(0 L, goal - destination.stock) / lag`.
- At 30 places (60 stores) it runs in 1.8 s, and at 100 places in 16.8 s (T2.2). Both are allowed.
- At 30,000 places the rule refuses it. The alternative runs for at least 31 s with no stock at its
  bound, and about 1.5 to 10 min with stocks at their bound.
Recommendation: adopt the rule. The language guide should say that a request that reads a
draining stock couples the stores, and that a held value avoids that.

### R-A4a-07: What a run records, and the budget in pieces  [owner]
Rule: the record of a run is the trace (the moments: time, kind, part) and one history for each
recorded value. A history is a list of pieces. A piece of a store is `(t, y, rate)`: the value is
`y + rate * (t' - t)` until the next piece. A piece of a flow is `(t, rate)`. A constant has the
rate 0. A jump is a new piece at the same `t`. A numeric segment of a component holds `t` and the
factors of its step polynomial in place of `rate`. As arrays, each kind of value has the columns
`t`, `y` and `rate`, sorted by value and then by time, and `first`, the index of the first piece of
each value (`record.py:397-427`).
What is recorded:
- Every store and every flow, while the record stays under a budget of 10,000,000 pieces (about
  190 MB as arrays). Reductions and lags are made from it after the run.
- When the planner's estimate (moments times the values that change at each) passes the budget,
  the run keeps only what the request names, with the reductions kept in the run. If that is also
  over the budget, the run is refused (R-A4a-05, message 3).
Alternative: record readings at the times that the request names, as the table path does today. Or
record the whole state at each step, as `Trajectory` does.
Example: a tank gets 8 L at 7 h in one run and at 9 h in another (T3.1).
- Readings at 0, 6 and 12 h give 0, 0 and 8 in both runs. A lag as the mean from 6 to 10 h cannot
  be computed from them.
- Pieces give 6 L and 2 L, exactly.
- At 30,000 rows the record of everything is 324,857 pieces, 6 MB, and adds 0.1 to 0.3 s. Ten
  reductions made from it later take 27 ms. A whole-state `Trajectory` would be about 80 GB
  (extrapolated), and a lagged report on today's table path takes 202 s (T3.3).
Recommendation: adopt the pieces and the budget. Record everything under the budget: in this
prototype that costs +0.1 s, against +2.5 to 3.4 s for keeping the reductions in the run.

### R-A4a-08: When a stored run serves a request, and what its key covers  [owner]
Rule: the key of a stored run is a hash of:
- the program, without labels, texts, notes or evidence;
- the effective configuration: inputs, start values, options;
- the mode (`median` or `sampled`), the seed and the controller choices;
- the numerical settings;
- the digest of the engine code and the environment (Python, numpy, scipy, the machine), as
  `store.key` has them today (`napkin/store.py:391-416`).
The key covers no label and no report request. Rows are ordered by id (R-A4a-02), so the key does
not cover the order of the rows in a file either. A stored run has a manifest: the horizon, and the
values that have histories ("everything", or a list). It serves a request when every value that
the request reads has a history in the manifest, over every time and window that the request asks,
inside the horizon. Otherwise the engine runs again, with the union of the old and the new request.
Alternative: today's key, which hashes the whole resolved run. From `store.py:405-411` and the
`label` fields of `model/structure.py:258`, a label edit then gives a new key and a new run. I read
this in the code and did not verify it with a run. A second alternative puts the request in the key.
Example: two edits of a small model and one request on a large model.
- Rename the label of `places.depot` from "Depot" to "Main depot". The rule serves the stored run;
  today's key runs again.
- Ask for the mean of `sum(Place.stock)` from 6 to 10 h on a small model, which recorded
  everything. The rule serves it from the pieces, in milliseconds (T3.2: two whole sum histories
  from 30,000 rows took 23 ms). A key that holds the request runs again.
- On the 30,000-row model, which recorded five rows and ten reductions, ask for `places.p00042.stock`.
  The rule runs again, since the row is not in the manifest.
- Change the seed. Both rules run again.
Recommendation: adopt the rule. With the manifest, "serves" is a check of set inclusion. With the
budget of R-A4a-07, most small models record everything.

## 5. Not covered

- I did not run `measure.py` end to end. Its tables in `results.md` come from the part runs of this
  work (§2). The components with moving requests have no JSON file.
- Not run: components of 300 places with moving requests, of 1,000 places with constant requests,
  and the network of 300,000 places.
- Upper bounds of stores in `lines.py`: only lower bounds are run.
- The real sharing rules (ranks, max-min fractions, declared solvers) are A3's work. `Lines.share`
  is a stand-in, and the 144 L difference with rings (T1.3) is a difference of rules.
- Numeric segments in the record: no component wrote its pieces, and the record holds no unknowns
  of a solver.
- The budget of 10,000,000 pieces and the limit of 150 stores are proposals from these numbers.
  They are not tuned.
- Members that come and go, and the map of the engine code: brief A4b.
- Not profiled: where the 30 s of the sparse integration at 30,000 places go.
