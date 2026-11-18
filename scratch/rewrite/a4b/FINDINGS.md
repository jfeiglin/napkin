# FINDINGS of prototype A4b: members that come and go

Two agents worked on this prototype. The first wrote `LAYOUT.md`, `split_run.py` and the spike (`spike/*.py`). The second made the spike run, measured it and wrote this file (see `STATE.md`).

## 1. Summary

- `LAYOUT.md` and `split_run.py` are done and accepted: `Run` is cut into ten mixin modules by pure moves. This file is about the second deliverable.
- A standalone spike in plain numpy (`spike/engine.py`) runs occurrences that start and finish. Their own flows and stores join and leave a shared network. Every case of `spike/cases.py` gives the number that the spec gives: the flows table (0, 1, 0, 1), the frozen request, the shared limit (2; 1.5 + 1.5; 2; none), the 10 h alarm, the grinder (108 g), the clock (3, 6, 9 h), `inspect(3 h)`, the three delivery rows, the retirement rule, a starved flow.
- The key rule: **a join or a leave is a write.** It writes the membership of the endpoint and the rates there, and every prediction that reads them is made again. Without it the alarm of the test case fires at 6 h with 12 L instead of 10 h with 16 L (run).
- The sum of the requests at an endpoint is kept **exactly** (an expansion, as in `math.fsum`). The rates then equal those of an endpoint formed fresh from its present members, bit for bit (59 of 59 random times). A running float total differs from the exact sum after 9,451 of 10,000 changes.
- Cost (section 3.2): a start costs about 80 µs and a finish about 18 µs in Python. Under a binding shared limit each join and leave makes about 1,650 predictions again. That work is a few array operations and one timeline entry for each pool, not one heap entry for each prediction.
- Proofs over templates: the writer sites of a value are all the flow declarations, of entities **and of events**, that can touch it. A store that any event can drain never counts as "never falls".

## 2. What was done

All scripts are in `spike/`. Run them from that folder with `/home/user/napkin/.venv/bin/python`.

| Script | What it is | How to run |
| --- | --- | --- |
| `engine.py` | The spike engine: pools of frames; stores and edges as columns; endpoints that members join and leave; one sharing pass a round; predictions as columns; the reader graph; triggers with three resets; `after`, `until`, moves; the retirement rule; the budgets | imported |
| `exact.py` | `ExactSum`: an exact sum that members join and leave | imported |
| `expr.py`, `program.py` | Expressions, and the records of a small program | imported |
| `cases.py` | Every case of section 3.1, printed | `python cases.py` (a few seconds) |
| `measure.py` | The cost table of section 3.2 | `python measure.py` (about 10 min alone); `--scale` adds 10 to 10,000 alive |

Fixes that the second agent made to `engine.py` (the first agent's code had not run):

1. `Columns.capacity` was overwritten by the edge column `capacity`. It is renamed `Columns.room`.
2. The moment at which a prediction came due (`reached`, `reset_reached`, `gate_reached`) started at 0, and the setup is moment 0. Every crossing counted as reached at setup, and the alarm fired at 0 h. These columns now start at -1.
3. `set_level`: a move could lift a store off the bound it rested on and land it on its other bound. The store then stayed marked as resting on its lower bound, so the batch of `retirement` did not drain.
4. `network`: a sink that rests on its upper bound and has no limit of its own was taken for "a flow limited at both ends", and `deliveries` stopped. Its limited sources now decide, held to what the sink lets out.
5. `network`: the bulk restart was all or nothing. One store at its bound among many made all of them restart one by one, with one heap entry each: 156,789 timeline entries for 1,000 starts at 200 alive, binding. After the fix there are 7,306.
6. `Cond.holds`: a crossing now holds within the tolerance of its store (R-A4b-06).

## 3. Results

### 3.1 The cases (`python cases.py`)

| Case | The spec, or a closed form | The spike |
| --- | --- | --- |
| Flows table: `count(occurrences)`, `count(flows)`, `sum(request)`, `actual_rate` | 0,0,0,0; 1,1,2,2; 1,0,0,0; 2,1,2,2 | the same |
| `deliver.occurrences.at(t).pipe.request` between A and B, then after B starts | A's 2 L/h (rate 0, not active), then B's | 2.0 (rate 0.0, started 1 h, none active); 2.0 (rate 2.0, started 3 h) |
| The same with `request = 2 * this.factor`, `factor` 1 -> 3 at 2.5 h | frozen at A's finish | 2.0 at 2.75 h; B asks 6.0 |
| Shared limit 3 L/h, 2 L/h each, A 0-2 h, B 1-3 h | 2; 1.5 + 1.5; 2; none | [2.0]; [1.5, 1.5]; [2.0]; [] |
| The same rates against an endpoint formed fresh (300 starts, random requests, limit 7.3 L/h, shuffled order) | equal bit for bit | 0 of 59 differ |
| A running float total (`+=` at a join, `-=` at a leave), 10,000 changes | equal to the exact sum | differs 9,451 times, by up to 4.0e-13 |
| Tank 10 L, fill 1 L/h, drain 2 L/h from 2 to 4 h, alarm `>= 16 L` | 10 h with 16 L (Euler steps: 10.000 h) | 10 h with 16 L |
| The same with `forget_membership` | the fault: 6 h with 12 L | 6 h with 12 L |
| Contact: tank held at 16 - 1e-12 L, alarm `>= 16 L` | fires at once (inside the tolerance of 1.6e-9 L) | 0.0 h |
| Contact: tank held at 16 - 1e-6 L | never | never |
| `> 16 L` on a store that moves | a diagnostic | stops: "a condition on a value that moves between moments must compare one store with a value by >= or <=" |
| Grinder at 8 g, its trigger and a manual start | 108 g, 2 refills | 108.0 g, 2 |
| `when t >= 3 h`, `reset after 3 h` | 3, 6, 9 h | 3 inspections by 10 h |
| `inspect(3 h)`, clearance at 7 h | stages at 3 and 5 h; gate passes at 7 h | 3.0, 5.0, 7.0 |
| Deliveries: separate / shared 10 L/h / B at 1 h | 10/10, 2/2 h; 5/5, 4/4 h; 10/0, 3/4 h, then 15/5, 20/10, 20/20 | the same |
| Retirement with `until batch <= 0 L` | finishes at 5 h | 5.0 h |
| Retirement without the gate | fails at 2 h with 12 L | "site.deliver#0 cannot finish at t = 2 h: its store batch still holds 12. Wait until it is empty, move the rest to a stock, or send it to SINK." |
| Starved flow: 3 L, 2 L/h for 4 h, 5 L more at 2 h | empty at 1.5 h; stays connected; runs again | 1 L, 1 flow, 2 L/h; 0 L, 1 flow, 0 L/h; 3 L, 1 flow, 2 L/h |
| Budgets: an hourly clock starts inspections that wait for ever | a stop with a message | see R-A4b-03 |
| Two starts at 1 h (20 L, 5 L) | 2 occurrences; `.at(t)` gives the later | 2, 2 done, newest 5.0, delivered 25.0, since 1.0 |

### 3.2 The cost (`python measure.py`)

1,000 lanes each repeat a delivery 100 times. That gives 100,000 starts and 100,000 finishes, with 1,000 alive at a time.

Each delivery owns a batch and one flow from the one shared supply, at 1 L/h. It waits until the batch is full, moves the batch to the tally of its lane, and starts the next delivery.

The supply has a limit on its outflow:
- Not binding: 1,000,000 L/h.
- Binding: 500 L/h. Every join and every leave then changes all 1,000 rates.

Every run checks that each lane received exactly its 100 batches. The table gives the best of three runs. The load was 3.4 at the start and 7.5 at the end, so the binding row ran on a busy machine.

| Case | Run | A start | A finish | Sharing and restarts | Gates | Predictions made again | Rates made again | Moments | Timeline entries |
| - | -: | -: | -: | -: | -: | -: | -: | -: | -: |
| Limit not binding | 52.8 s | 75.6 µs | 17.3 µs | 23.9 s | 12.4 s | 699,994 (3.5 per change) | 200,000 | 100,998 | 600,994 |
| Limit binding | 118.3 s | 84.6 µs | 19.4 µs | 48.3 s | 48.2 s | 330,634,670 (1,653 per change) | 165,186,026 | 190,024 | 743,652 |

How to read the table:
- "A start" is the time spent in `Engine.start`: the frame, the batch, the flow joining both endpoints, and one reading of the gate.
- "A finish" is the time spent in `Engine.finish`: the flow leaving, the retirement check, and the row kept as a record.
- Neither includes the sharing pass. That pass is in "Sharing and restarts": 120 µs per change when not binding, 242 µs per change when binding.
- "Predictions made again" counts each row of a prediction column that was written: when each batch reaches its bound, and when each gate can pass.
- Under the binding limit, the 330 million predictions cost about 0.5 µs each, because they are made in arrays. There are 3.7 timeline entries per change, not 1,653.

Memory:
- Each occurrence costs 341 bytes, kept for the whole run: pool row 124, store row 94, edge row 81, prediction columns 34, gate mark 8.
- 100,000 occurrences hold 34 MB.
- The live part is bounded by the 1,000 occurrences alive: the active list, the member lists of the endpoints, and the exact sums.

Not verified:
- The cost with numeric blocks, with an edge limited at both ends (the solve library of S2), or with ranks.
- The spike is Python, so the engine's numbers will differ. The shape of the cost, meaning what grows with the number alive, should hold.

## 4. Rulings

### R-A4b-01: The pool of frames  [technical]
Rule: There is one pool for each (template, event). It is a set of columns that grow together:
- receiver, `started`, `finished`, `done`, `active`, step pointer, version, `before`;
- each parameter, as given and as a live copy;
- the locals;
- the ids of the local stores and flows.

A row is one occurrence for good. It is never moved and never reused, so the row number is its identity and its creation order. A compact list of the active rows sits beside the pool (swap-remove, `place[row]`). Each receiver keeps `newest`, `started_count`, `done_count` and `active_count`. `before[row]` chains a receiver's occurrences. Vector work reads `column[active]`.
Alternative: a pool bounded by the active count. Slots are reused after a finish, and finished occurrences are copied out to the record.
Example: `frozen_request` (run). A runs 1-2 h and B starts at 3 h. Under the rule, at 2.5 h `deliver.occurrences.at(t).pipe.request` reads row 0: 2 L/h, rate 0, not active. At 3.5 h it reads row 1. A stale timeline entry of A names row 0 and cannot touch B. With slot reuse, B takes slot 0. A's stale entry must then be told apart by a version, `deliver#0` names two occurrences in the trace, and `.at(t)` needs a map from slot to creation order. Under the rule, `count`, `count(.done)`, `any(active)`, `since` and `.at(t)` are O(1) from the receiver counts.
Recommendation: Take the rule. It costs 341 bytes for each occurrence for the whole run, 34 MB for 100,000. If that matters, spill finished rows to the record (A4a) in blocks, and keep the row number as the identity.

### R-A4b-02: What stays readable on a finished occurrence and its flows (item 52, with A2)  [owner]
Rule: A finished occurrence keeps, read-only:
- `started`, `finished`, `done` and its receiver;
- its parameters: the live copy at the finish, and the argument as given, for provenance;
- its locals at the finish;
- each of its flows.

A finished flow keeps its key, its two endpoints, and its last evaluated `request` and `capacity`. These are frozen: a formula is no longer evaluated. The flow reads `actual_rate` as 0 L/h and is in no `.flows` collection. A local store of a finished occurrence reads 0 in its unit, because the retirement rule emptied it. Its earlier levels are a history read, "not in the first version", with the message: "`batch` of a finished `deliver` reads 0 L; its history is not kept". A retained local formula is not readable after the finish.
Alternative: a finished occurrence exposes only `started`, `finished` and `done`. A read of its flows or its locals is an error.
Example: `frozen_formula` (run). `pipe.request = 2 * this.factor`. A runs 1-2 h, and `factor` goes from 1 to 3 at 2.5 h. At 2.75 h, `deliver.occurrences.at(t).pipe.request` gives 2 L/h under the rule, the spec's frozen value. Evaluated live it would give 6 L/h; under the alternative it is an error. Once B starts at 3 h, it gives B's 6 L/h.
Recommendation: Take the rule. The spec's flows table already promises it, and it costs nothing because the row stays (R-A4b-01).

### R-A4b-03: Budgets for occurrences, and their messages (item 69, with A2)  [owner]
Rule: Three budgets stop a run with a message:
- `max_occurrences`: starts of one event over the run, default 1,000,000.
- `max_active`: occurrences of one event alive at once, default 100,000.
- `max_rounds`: rounds of one moment, default 1,000.

The message names the event, the time and the counts. For `max_active` it also names the oldest occurrence and the step it waits at, and says how many wait at that step.
Alternative: one budget on the total count of starts, with a message that gives only the count.
Example: `budgets` (run). An hourly clock starts an `inspect` that waits `until this.cleared`, which never comes.
- With `max_active = 5`: "The run stops at t = 6 h: 5 occurrences of Plant.inspect are active at once (max_active). The oldest, plant.inspect#0, started at t = 1 h and waits at `until (this.cleared >= 1)`; 5 of them wait at that step."
- With `max_occurrences = 5`: "Plant.inspect has started 5 occurrences (max_occurrences). 0 have finished and 5 are active."

The alternative stops at the same time but gives only the count. It also cannot stop a model whose occurrences pile up slowly while most of them finish.
Recommendation: Take the three budgets. The active budget finds the usual bug, a gate that never opens, and its message points at that gate.

### R-A4b-04: The reader graph for a join and a leave  [technical]
Rule: The reader graph is made at the level of templates, never as one list for each member.

The membership of a collection is a written name: `('occ', template, event)` for the occurrences of an event, and `('flows', template, store)` for the flows at an endpoint. A join or a leave is a write of that name. The sharing pass that follows writes the rates and the line of every store at that endpoint.

A write finds its reader rows in one of four ways:
- SAME: the same member.
- LINK: a reverse index of a link.
- FRAME: the same occurrence.
- RECEIVER: the active occurrences of a member.

A round runs in this order:
1. The due stages and the starts commit.
2. The requests that read a written name are made again.
3. One sharing pass runs.
4. Each store whose rate changed restarts its line and its bound prediction.
5. The triggers and gates that read a written name are read and predicted again.

Alternative: the present engine's fixed readers. A line that restarts marks the rules in `plan.parts[name]` (`plan.py:690-709`, `run.py:2202-2205` and `2306`). These lists are made before the run, so a new flow appears in none of them.
Example: `crossing` (run). A tank at 10 L fills at 1 L/h. A `drain` occurrence takes 2 L/h from 2 to 4 h, and an alarm watches `>= 16 L`. Under the rule, the join at 2 h and the leave at 4 h each make the alarm's prediction again (4 trigger readings), and it fires at 10 h with 16 L. With the join not a write (`forget_membership=True`, 2 readings), the 6 h prediction made at 0 h stays. At 6 h it comes due, and, as today (`run.py:2447`, D-65), a crossing whose prediction came due holds without a look at the value. The alarm fires at 6 h with 12 L.
Recommendation: Take the rule. Keep a version on each prediction row, as the spike does: a prediction made before its store's latest restart is then stale when it comes due.

### R-A4b-05: The totals of an endpoint, and fresh formation  [technical]
Rule: Each endpoint keeps:
- an unordered member list, with O(1) join and leave;
- the count of its members;
- the exact sum of the requests of its present members, as an expansion of non-overlapping doubles (`exact.py`).

Rates are computed from these totals. `actual_rate` is the correctly rounded sum of the present rates. The published rates then equal those of a problem formed fresh from the present members, bit for bit, whatever the order and the history of joins and leaves.
Alternative: a running float total (`+= x` at a join, `-= x` at a leave), or a pairwise tree over slots (`trees.py`), which depends on the slot each member got.
Example: `fresh_formation` and `running_total_drift` (run). 300 occurrences with random requests join and leave a 7.3 L/h limit. At 59 random times, the rates equal those of a fresh `share` over the shuffled present members: none differ. A running total differs from the exact sum after 9,451 of 10,000 joins and leaves, by up to 4e-13 L/h. With it, the same members would get other rates, and a run would depend on its history.
Recommendation: Take the rule. An `ExactSum` add costs a few float operations, and the spec's demand to "match a freshly formed problem" needs it.

### R-A4b-06: Contact tolerances and the predicates that the engine can certify (item 28)  [owner]
Rule: The engine certifies the first contact of these predicates:
- `q >= v` and `q <= v`, where `q` is one stored quantity that moves between moments on a piece the engine can solve in closed form (a line in the spike; a block's solution in the engine), and `v` changes only at moments;
- clocks `t >= X`;
- conjunctions of these with gates on values that change only at moments, with at most one crossing in a condition (as `structure.classify`, `structure.py:181-202`).

A crossing holds in either of two cases:
- `q` is within the tolerance of its store of `v`. The tolerance is 1e-10 times the size of the store, as `Run.sizes` sets it.
- Its predicted time is within `EVENT_TIME_TOLERANCE_H` of the moment: 1e-8 h, `ir.py:24` (D-65, `run.py:2385-2399`).

The prediction is made again after every write that the reader graph (R-A4b-04) sends to it.

Three things are a diagnostic at setup: a strict `>` or `<` on a moving value; two crossings in one condition; a crossing of a value that no closed form gives. The message: "`water > 16 L`: a condition on a value that moves between moments must compare it by >= or <=; use `>= 16 L` or schedule an inspection".
Alternative: compare exactly, with no band, and accept strict thresholds, read at the first step at or after the crossing.
Example: `contact` (run). A tank is held at 16 - 1e-12 L, at rate 0 and inside its tolerance of 1.6e-9 L, with an alarm on `>= 16 L`. The rule fires at 0 h. The exact comparison never fires, though the level differs from the mark by less than the roundoff of one restart. At 16 - 1e-6 L, neither fires. `> 16 L` on the same store stops at setup with the message above; under the alternative it would fire at a time that the step size sets.
Recommendation: Take the rule. The band is the one the engine already uses for every quantity, so a model sees one tolerance, not two.

### R-A4b-07: The proofs, stated over the templates of events  [owner]
Rule: A proof about a value (template, field) covers its **writer sites**:
- every flow declaration, of an entity or of an event, whose endpoint can be that value, by static type and path (`this.x` or `this.link.x`);
- every stage statement (`=`, `+=`, `-=`, `move`) of any event that can write it.

Each occurrence that can exist is an instance of one of these sites, so a proof over the sites covers them all. Each proof is then stated this way:
- **Never falls** (a tally, a reporting lag): every flow site points into the value, and every stage site adds zero or more (`+=` of a proved nonnegative value, or `move ... to` it). A store that any event can drain, by a flow or by a move out, does not qualify.
- **One way between moments** (a crossing of a value that moves one way, `monotone_quantity`, `values.py:247`): every flow site, of entities and of events, points the same way. A join or a leave happens at a moment, where every condition is read, so it cannot hide a reversal.
- **A proved zero face** (`stock_zero_crossing`, `values.py:173`): the closure includes the stores that event flow sites touch. No request or capacity of a site reads a value that moves between moments; the spike refuses such a site (`engine.py:646-650`). So the rates are constant between moments, whatever the membership.
- **Reductions:** those over `.flows` or over `active`, and `any(active)`, are never monotone, because members leave. `count(occurrences)`, `count(.done)` and `since` are monotone.

Alternative: today's proofs, over the flows that the structure lists before the run (`index.flows_at`, the fixed structure of `values.py:716` and after).
Example: `crossing` (run). The tank's own flows are one fill into `water`, so the fixed-structure proof says `water` never falls. The `drain` event declares a flow out of `this.water`, so the rule says it can fall, and the run shows it: the line of `water` is +1 L/h from 0 h, -1 L/h from 2 h (12 L), and +1 L/h from 4 h (10 L). A lag or a one-way crossing that the alternative grants would be wrong.

A second run shows the other side. The tally `delivered` of a lane has one writer site, `move got ... to this.delivered` of `deliver`. Under the rule it never falls, and every run of `measure.py` agrees: each lane ends with exactly its 100 batches.
Recommendation: Take the rule. It is a static pass over the program records (`program.py`) and needs no run. `spike/proofs.py` was planned to check it against random runs and is not written.

### R-A4b-08: The module layout  [technical]
Rule: as in `LAYOUT.md` sections 7 and 10. `Run` is cut into ten mixin modules by moves: `state`, `lists`, `sharing`, `segments`, `readers`, `checks`, `rules`, `steps`, `choices`, `trace`. In S4 the pool of frames goes to `occurrences.py`, the edges that join and leave go to `network.py`, and the membership readers go to `readers.py`.
Alternative: functions that take the run.
Example: `value` has 32 callers. A mixin move changes no body: 143 functions keep their bytecode (`split_run.py --check`). The alternative rewrites every call.
Recommendation: Already accepted as deliverable 1.

## 5. Not covered

- `spike/proofs.py` (the writer-site pass, checked against random runs) and `spike/test_spike.py` (pytest over the cases) are not written, because usage was short. R-A4b-07 rests on the rule and on two runs, not on a checker.
- `measure.py --scale` (10 to 10,000 alive) was not run.
- The spike has no numeric blocks, no edge limited at both ends, no ranks in a run, no flows with legs, no reversible flows, and no draws or choices. A request that reads a value moving between moments is refused, not supported.
- The links and flows across tables, the connected sets and the record of a run belong to brief A4a.
