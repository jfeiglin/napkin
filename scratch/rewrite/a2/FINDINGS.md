# A2 findings: reference semantics

## 1. Summary

- `ref/` is a small exact interpreter (about 2,700 lines). A model is plain data (`ref/model.py`), and
  `ref/run.py`, `ref/network.py` and `ref/select.py` run it. Arithmetic uses fractions. Levels between
  moments are exact polynomials. The selection order is brute force: LPs snapped to fractions, then an
  exact least-distance step.
- All 31 cases of the brief reproduce the numbers of the spec (73 tests in `cases/test_NN_*.py`).
- 23 rulings. Each is a switch of `Rules` (or of `Config`). Each has a test that runs the rule and the
  alternative on one example and asserts that they differ (`cases/test_rulings.py`, 23 tests).
- Whole suite: 96 tests. Best of three runs: 4.63 s at load 1.53 (`run_all.sh`).
- Three things in the earlier agent's code were wrong and are mended (section 3.2). The most important:
  setup was not really "round zero". Triggers got their first check only after the `after 0 h` stages of
  the setup starts had run.
- The interpreter raises `NotCovered`, with the reason, for what it does not cover (section 5). It never
  guesses.

## 2. What was done

| File | What it is |
| - | - |
| `ref/model.py` | The description: expression nodes `E`, fields, flows, events, triggers, solvers, `Model`, `Config`, `Rules` |
| `ref/evaluate.py` | One evaluator for instant values, report frames, solver unknowns as symbols, and "germ" mode (polynomials in time) |
| `ref/network.py` | Components, the assembly of one problem, settling with a cache, motion between moments |
| `ref/select.py` | The four ranks of the selection order |
| `ref/exact.py`, `ref/poly.py` | Linear algebra on fractions; exact polynomials in time |
| `ref/run.py` | Setup, moments, rounds, stages, occurrences, triggers, gates, ledger, record, reads, draws, choices |
| `cases/test_NN_*.py` | One file for each case of the brief, with the spec's numbers as assertions |
| `cases/test_rulings.py` | One test for each ruling: the rule and the alternative give different results |
| `conftest.py` | Puts `a2/` on `sys.path` |
| `run_all.sh` | Runs the suite three times and prints `uptime` |

To run: `cd /home/user/napkin && .venv/bin/python -m pytest scratch/rewrite/a2 -q -p no:cacheprovider
--rootdir scratch/rewrite/a2 -c /dev/null`, or `sh scratch/rewrite/a2/run_all.sh`.

## 3. Results

### 3.1 Coverage of the 31 cases

All 31 cases reproduce. The files are under `cases/`.

| # | Case | File | Result |
| -: | - | - | - |
| 1 | Grinder: 8 g + 50 g = 58 g at 0.5 h, `low_on_beans` false | `test_01_grinder.py` | reproduced |
| 2 | Tank and clinic: 3 L/h, empty at 8/3 h, then 0; capacity 5 and request 3 stay | `test_02_tank_clinic.py` | reproduced |
| 3 | Reversible route at -3: forward 0, backward 3; both 0 at zero | `test_03_reversible.py` | reproduced |
| 4 | Flows created during a run: table 0,1,1,2 / 0,1,0,1; A's frozen 2 L/h | `test_04_flows_during_run.py` | reproduced (the request is a formula; the pace changes to 5 after A ends) |
| 5 | Three requests 10/8/6: 10; a cap of 7 at any scope: shortfalls 3, 1, 0 | `test_05_three_requests.py` | reproduced, with the cap at each of the three scopes |
| 6 | Junction: 8 W through a store held at [0, 0] | `test_06_junction.py` | reproduced |
| 7 | Priority 8 and 2; proportional 4 and 6; empty at 2 h | `test_07_local_allocation.py` | reproduced |
| 8 | Common sink: 4 and 2 | `test_08_common_sink.py` | reproduced (also 4 and 6 for two separate claims) |
| 9 | Worked network: four rows; levels (8/3, -4/3, -4/3) and (3, -3, 0); 1 W and 3 W; kW; reordered tables | `test_09_worked_network.py` | reproduced, all six parts |
| 10 | Two bottlenecks: (2, 2, 3), 11 W; (4, 0, 5), 9 W | `test_10_two_bottlenecks.py` | reproduced |
| 11 | Staffing: 70/30, then 56/24 | `test_11_staffing.py` | reproduced |
| 12 | Pump: fill 2, clinic 2, town 0; 10 L: 6 and 6, no fill, no charge; withdrawn: idle | `test_12_pump.py` | reproduced |
| 13 | Provider: 6/2; 2/6; East full 0/6 | `test_13_provider.py` | reproduced, also with East filling during a run (full at 5/3 h) |
| 14 | `inspect` with 3 h: stages at 3 h and 5 h; the guard is read once | `test_14_inspect.py` | reproduced |
| 15 | Retirement: 20 L in, 12 L out: fails, names 8 L | `test_15_retirement.py` | reproduced |
| 16 | Horizon: 7.5 / 12.5 at 1 h; 20 and one completion at 2 h; falling ramp 6.25 L, gate waits | `test_16_horizon.py` | reproduced |
| 17 | 11 L at -1 L/h fires `<= 10` at 1 h | `test_17_threshold.py` | reproduced; `< 10` is refused by name |
| 18 | Trigger and manual start: 108 g | `test_18_grinder_trigger.py` | reproduced |
| 19 | Clock at 3, 6, 9 h; cooldown: eligible at 3 h, fires at 4 h, next at 7 h | `test_19_clock.py` | reproduced |
| 20 | The history table, each expression | `test_20_history.py` | reproduced, with two starts at one time |
| 21 | Legs: 0.5, 2 and 4; (0, 8) gives (0, 8) and 1; (0, 0) gives 0; crossing zero stops no run | `test_21_legs.py` | reproduced (the request crosses zero through writes in stages) |
| 22 | Reserving a delivery, both versions | `test_22_reserve.py` | reproduced |
| 23 | `move` 3 L: 5 and 3; 5 L fails and leaves 8 and 0 | `test_23_move.py` | reproduced |
| 24 | Inequalities: (2, 2), (3, 3); and (1/2, 1/2) | `test_24_inequalities.py` | reproduced |
| 25 | Membership: 2; 1.5 each; 2; nothing | `test_25_membership.py` | reproduced, and equal to a run with no cache |
| 26 | Delivery table: 10/10 and 2/2; 5/5 and 4/4; 10/0 and 3/4; totals 15/5, 20/10, 20/20 | `test_26_delivery_table.py` | reproduced |
| 27 | `x = 2` then `y = x` gives 2; a delay of `this.staffing.care` is 56 h | `test_27_stage_reads.py` | reproduced |
| 28 | `count(child.occurrences)`: 0 in the stage, 1 in the next delay | `test_28_child_count.py` | reproduced |
| 29 | 8 g to 12 g before the check: no firing | `test_29_beans_before_check.py` | reproduced (with one stage, and with two stages of one round) |
| 30 | A joining flow moves the crossing: fires at 10 h, not 6 h | `test_30_joining_flow_moves_crossing.py` | reproduced |
| 31 | Two writes in one round, one solve; a reaction, a second round and a second solve | `test_31_once_in_a_round.py` | reproduced (counts of `('solve', t)` in the trace) |

### 3.2 Mended work of the earlier agent

1. **Setup was not round zero.** The rule said that the setup statements commit, the rates settle, and
   then the triggers get their first check. The code ran the `after 0 h` stages of the setup starts first.
   Fixed in `ref/run.py:313`. Ruling R-A2-05 now gives different results for the two rules.
2. **Choices and chances could not run.** `Run.decide` and `Run.chance` took a node argument that the
   evaluator never passed. Also, a draw was keyed by the text of its expression, not by its site, so two
   identical `x.draw()` texts at two sites would have shared a key. Now `Ev.ref` passes the node of
   `call`, `choose` and `chance` (`ref/evaluate.py:236`).
3. **A far-off irrational contact stopped a run.** In case 16 the tank would reach its upper bound of
   100 L at an irrational time, long after the moments that matter. `Poly.first_root` now returns an
   `Irrational` stop. The run fails only when such a stop is the next moment (`ref/run.py:273`).
4. `Run.read` of a projected collection now gives the values of its members (case 25).

No case of the spec proved a settled rule of `STATE.md` wrong.

## 4. Rulings

Each rule is the default of one switch in `ref/model.py` (`Rules`, or `Config.max_active` for R-A2-13).
The example of each ruling is the test with the same number in `cases/test_rulings.py`, `test_NN_*`.

### R-A2-01: The order of simultaneous starts and of due stages  [owner]
Rule: Starts register in the order in which their `.start` statements ran: stages in commit order, then trigger firings by receiver and declaration. Stages due in one round commit by the age of their occurrence, the older first.
Alternative: Stages commit in the order in which they were scheduled.
Example: Occurrence A (older) has `after 1 h:` then `after 1 h: last = "A"`. Occurrence B (younger) has `after 2 h: last = "B"`. Both are due at 2 h. B's stage was scheduled first (at 0 h). Rule: A commits, then B, and `last` is "B". Alternative: B, then A, and `last` is "A".
Recommendation: Take age order. It depends only on the identities of the occurrences, not on how many waits each one went through.

### R-A2-02: The members of a start on a collection  [owner]
Rule: The members start in the key order of the collection as addressed. Equal keys start in creation order.
Alternative: Creation order, whatever key `by` gave.
Example: Machines m1 (rank 2) and m2 (rank 1), created in that order. `Machine.instances.by(rank).repair.start()`. Each repair writes `board.last = this` at 0 h. Rule: m2 starts first, so m1 commits last and `board.last` is m1. Alternative: `board.last` is m2.
Recommendation: Key order. An author who writes `by(rank)` expects the rank to matter, and creation order still breaks ties.

### R-A2-03: Conflicting writes from two stages of one round  [owner]
Rule: The stages of a round commit one after the other. A later stage reads what an earlier one wrote. The last `=` wins, and `+=` adds up.
Alternative: Every stage reads the state from the start of the round. Two different writes to one value fail the run.
Example: beans 20 g. At 1 h stage A sets `beans = 8 g` and stage B does `beans += 4 g`. Rule: 12 g (case 29). Alternative: the run fails with "conflicting writes to grinder.beans from two stages of one round at t = 1 h".
Recommendation: Sequential commits. With R-A2-01 the result is deterministic, and it matches the spec's rule that a stage sees earlier direct writes.

### R-A2-04: Reset cycles  [owner]
Rule: A trigger may fire again at the same time after its reset. A run allows a fixed number of rounds at one time (100). Beyond that the run fails and names the triggers that fired again and again.
Alternative: A second firing of one trigger at one time fails the run at once.
Example: `when this.n < 2: this.bump.start()` with `reset when true`. `bump` does `n += 1` after 0 h. Rule: two firings at 0 h, and n = 2. Alternative: fails with "pump.bump.when[0] fires a second time at t = 0 h". With `n < 10**6`, the rule fails after 100 rounds and names `pump.bump.when[0]`.
Recommendation: Take the budget. A finite chain of reactions at one time is legitimate, and the message names the cycle when there is one.

### R-A2-05: Setup order  [owner]
Rule: Setup is round zero. Starting values are computed in dependency order. The statements of the setup scope commit as one stage. Rates and solvers settle. Then triggers get their first check. The stages of setup starts that are due at 0 h run in round one.
Alternative: The starts of the setup scope run to rest before the first trigger check.
Example: beans 8 g, trigger `when beans <= 10 g`. Setup starts `prepare`, whose `after 0 h:` sets beans to 12 g. Rule: the trigger fires at 0 h. Alternative: no firing.
Recommendation: Round zero. The initial check then sees the starting values that the model wrote, as the trigger table of the spec says ("including the initial check").

### R-A2-06: `none` in arithmetic, in a comparison and in a reduction  [owner]
Rule: `none` propagates through arithmetic, ordering comparisons and reductions. `==` and `!=` test for absence. A decision that receives `none` (a condition, a guard, a selector or a delay) fails the run and names the value.
Alternative: Any arithmetic or ordering on `none` fails the run at once.
Example: `reading = none`, `shown = formula(reading + 1)`, `absent = formula(reading == none)`. Rule: `shown` is none, `reading <= 3` is none, and `absent` is true. Alternative: reading `shown` fails with "reading + 1 reads a value that is none". `absent` is true.
Recommendation: Propagate. A report can show an absent value, and the failure comes where the absence decides something.

### R-A2-07: `min` and `max` over nothing  [owner]
Rule: `none`. A scalar beside the collection takes part, so `max(0, c.x)` over nothing is 0.
Alternative: A run error where the expression is evaluated.
Example: a template `Pump` with no instances. Rule: `max(Pump.instances.rate)` is none. Alternative: fails with "is read over nothing". Both give `max(0, Pump.instances.rate) = 0`.
Recommendation: `none`, which fits R-A2-06. The author writes the scalar to get a number.

### R-A2-08: `elapsed` after several writes in one stage  [owner]
Rule: The clock restarts only when the committed value differs from the value before the stage.
Alternative: Every write that changes the value restarts the clock, also a change that the same stage undoes.
Example: `state = A`. At 2 h one stage writes `state = B`, then `state = A`. At 3 h, rule: `elapsed(state)` is 3 h. Alternative: 1 h.
Recommendation: Net change. Values inside a stage are invisible to everything else (spec: "temporary values written inside one atomic stage are invisible to the binding"), and the clock should agree.

### R-A2-09: A read with zero delay inside a stage  [owner]
Rule: `delayed(x, 0 h)` reads the committed value, not what the stage itself has written.
Alternative: It reads what `x` reads.
Example: x = 1. A stage does `x = 5`, then `y = delayed(x, 0 h)`. Rule: y = 1. Alternative: y = 5.
Recommendation: Read the committed value. Then `delayed(x, D)` is continuous as D falls to zero, and the stage's own writes stay what a plain `x` reads.

### R-A2-10: What stays readable on a finished occurrence  [owner]
Rule: Everything stays readable, frozen at the finish: arguments, locals, formulas (as values), `started`, `done`, `active`, and each flow's key, endpoints and last request. A local store reads its final amount, which the retirement rule makes zero.
Alternative: Only the built-in fields. Arguments, stores and formulas fail.
Example: `job(amount)` with `double = formula(amount * 2)`, started with 7, done at 1 h. At 2 h, rule: `occurrences.at(t)` gives amount 7, double 14, done true and active false. Alternative: done is true. Reading amount fails with "cannot be read after the occurrence has finished".
Recommendation: Freeze everything. The spec already freezes the flow's request, and one rule for all fields is simpler to explain.

### R-A2-11: A saved reference to an occurrence  [owner]
Rule: It pins the identity. A later start does not change what it names.
Alternative: It is the lookup, read again at each use.
Example: a parent starts `child` at 1 h, saves `saved = child.occurrences.at(t)`, and starts another child at 2 h. Rule: `saved.started` is 1 h. Alternative: 2 h.
Recommendation: Pin it. A saved value that changes by itself would be a formula, which the author can write.

### R-A2-12: A flow with legs that two endpoints rank differently  [owner]
Rule: A claim is decided after every claim that some endpoint ranks ahead of it, also through a chain. Claims whose ranks contradict each other share a tier.
Alternative: The claim takes the last position that any endpoint gives it.
Example: activity `r` has leg l1 on X (capacity 6) and leg l2 on Y (capacity 4). Each leg asks for 4. X has `priority(a, r.l1)`, and a asks for 2. Y has `priority(r.l2, b)`, and b asks for 4. Rule: the tiers are a, r, b. r is served in full (fraction 1), b gets 0 and a gets 2. Alternative: r and b share tier 2. r gets 0.5, b 2 and a 2. (The other alternative, the first position, gives 1, 0 and 2 here.)
Recommendation: Take the rule. Each endpoint's priority then holds: at Y, r.l2 is served before b, which the alternative breaks.

### R-A2-13: The budget for occurrences that never finish  [owner]
Rule: Waiting for ever is legal. The budget is on the occurrences of one bound event that run at once (1000). The message names the event, the count, the time and the gate of the oldest occurrence.
Alternative: No budget.
Example: `when t >= 0: ticket.start()` with `reset after 1 h`. Each ticket waits `until open`, which never holds. With a budget of 3: "budget: 3 occurrences of desk.ticket run at once at t = 3 h and one more starts (the limit is 3). The oldest, desk.ticket#1, started at 0 h and waits at step 1: until this.open." With no budget: 11 occurrences at 10 h and no error.
Recommendation: Take the budget, as a configuration limit. It stops runaway growth, and the message points at the gate.

### R-A2-14: Where a human choice pauses  [owner]
Rule: The run pauses inside the stage, before its commit. Nothing of the stage is visible while the run waits. The answer replays the stage.
Alternative: The stage commits what it did before the choice.
Example: at 1 h a stage starts `child`, sets `x = 1`, then asks for the choice `plan`. Rule: the run pauses with x = 0 and no child. Alternative: x = 1 and one child. When the answer `repair` is given, both give `plan = repair` and one child.
Recommendation: Pause before the commit. The stage stays atomic, and the answer cannot depend on half a stage.

### R-A2-15: Where an `assert` on state is checked  [owner]
Rule: After every round, just after every moment, and at each contact with its boundary between moments.
Alternative: After every round only.
Example: 10 L drains at 1 L/h with `assert water >= 5 L`. A stage refills to 10 L at 7 h. Rule: fails "just after t = 5 h". Alternative: passes, with 9 L at 8 h. The 3 L just before the refill at 7 h is never checked.
Recommendation: Take the rule. An assertion that misses a breach between stages promises a check that it does not make.

### R-A2-16: An invalid history read that a report asks for  [owner]
Rule: A report reads the record after the run. An invalid read shows as unavailable, with the reason.
Alternative: The read happens during the run and fails it.
Example: a report asks for `since(grinder.refill)` at 0 h, before any refill. Rule: the run reaches its 2 h horizon. The report shows "unavailable (since(grinder.refill) is read before the first occurrence)". Alternative: the run fails at 0 h.
Recommendation: Read the record. Adding a chart then cannot change the trajectory.

### R-A2-17: The key of each draw  [technical]
Rule: The key is the seed, the site of the draw in the model, and its owner: the occurrence, the firing or the entity.
Alternative: The position of the draw in one stream.
Example: a sampled run with seed 7. `late` draws `speeds` at 1 h. `early` draws at 0 h only when an input is true. Rule: `late` gets the same value with the input true or false. Alternative: the value of `late` changes with the input.
Recommendation: Keyed draws. Two policies then see the same weather wherever their histories agree.

### R-A2-18: An opening balance from outside  [owner]
Rule: What a store holds when it first becomes a store is recorded in the ledger as an opening balance from outside.
Alternative: A store of an occurrence must start empty.
Example: `receive(20 L)` with `remaining = amount` and a flow to the tank. Rule: the ledger shows an opening balance of 20 L, and the account balances (20 L held). Alternative: refused with "starts with 20 that no flow or move brought".
Recommendation: Record it. The spec's ramp example needs it, and the ledger keeps the two cases apart.

### R-A2-19: `move` on a `readonly` stock (open item #1)  [owner]
Rule: `move` may debit and credit a `readonly` stock, as the spec proposes. A direct assignment stays an error.
Alternative: `move` is refused on a `readonly` stock.
Example: move 3 L from a readonly stock of 8 L into an empty readonly store capped at 4 L. Rule: 5 L and 3 L. Alternative: refused with "move: a.water is readonly".
Recommendation: Allow it. A move is a recorded transfer like a flow, not an assignment.

### R-A2-20: Forward references of locals and flows (open item #23)  [owner]
Rule: Plain local initializers run in written order. A retained `formula(...)` local may name a later local. All the flows of an occurrence are made after all its locals, so a flow may name any local.
Alternative: Every local and flow may name only what is written above it.
Example: `pace = formula(base * 2)`, then `base = 3`, and a flow requesting `formula(pace)` for 1 h from 100 L. Rule: 94 L. Alternative: refused with "the formula names ['base'], declared below it".
Recommendation: Take the rule. A formula is read later, so its position does not matter. A captured value keeps the written order.

### R-A2-21: The retirement rule (open item #27)  [owner]
Rule: A store of an occurrence must be empty at normal completion. Otherwise the run fails and names the occurrence, the store, the amount and the time.
Alternative: The rest is disposed of and recorded in the ledger.
Example: a batch of 20 L delivers 12 L in 1 h, then the occurrence ends. Rule: fails with "plant.batch#1 cannot finish at t = 1 h: its store plant.batch#1.stock still holds 8". Alternative: 8 L is disposed of, and the account balances.
Recommendation: Fail, as the spec recommends. Material that leaves should go through a written flow to `SINK`.

### R-A2-22: A result read across stages of one round (found)  [owner]
Rule: A stage reads the last settled result even when another stage of the same round changed its inputs. Only a read in the stage that made the change is a dirty read, and gets a diagnostic.
Alternative: Such a read fails the run.
Example: staffing with 100 h. At 1 h stage A sets staff hours to 80. Stage B, in the same round, writes `seen = staffing.care`. Rule: seen = 70, and care is 56 after the round. Alternative: fails with "is read after another stage of this round changed its inputs".
Recommendation: Take the rule, with a warning. The result is the one published at the last settlement, and R-A2-01 makes it deterministic.

### R-A2-23: The reference scale of flows of two dimensions (found)  [technical]
Rule: The distance step divides each flow coordinate by one canonical unit of its dimension (`Model.scales`).
Alternative: Divide by one working unit, whatever the dimension.
Example: flows `fill` (L/h) and `motor` (W, working unit kW), with `fill + motor >= 4` and no requests. Rule: fill 4000000/1000001, motor 4/1000001. Alternative: (2, 2). Under the alternative the answer changes with the display unit, which the spec forbids.
Recommendation: A canonical unit for each dimension, fixed by the language. The spec should say so: it defines the scale only for flows of the same dimension.

## 5. Not covered

For each of these the interpreter raises `NotCovered` with a reason. None of the 31 cases meets one.

- **Units.** There is no unit algebra: a model is in one set of working units. `Model.scales` holds the
  canonical unit of each dimension, for the distance step only.
- **Continuous change.** A rate input that moves between two moments is followed only for the request of
  a directed flow that nothing limits (`ref/network.py:440`, `:459`). The interpreter refuses solver
  coefficients that move, levels of degree three or more, and a moving rate on a store at its bound
  (`ref/poly.py:108`, `ref/network.py:467`). It also refuses a contact at an irrational time when that
  contact is the next moment.
- **Solver numerics.** Ranks 2 and 3 use float LPs. Each optimum is snapped to the simplest fraction
  within 1e-9 (`ref/select.py:24`). A problem whose optimum is not such a fraction gives a wrong answer or
  a refusal. The distance step tries at most 50,000 sets of active rows (`ref/select.py:296`). The worked
  network is the largest case (1.2 s). This is an oracle for small models, not a measurement of scale.
- **Positive parts.** The interpreter refuses nested positive parts, more than 12 in one relation, and a
  request at an endpoint that has a reversible flow (`ref/select.py:97`, `:144`, `ref/network.py:334`).
- **Events.** There is no `at T`, no cancellation or interruption, and no `while`. A pause does not resume
  in place: a resumed run is a fresh run with the answer in `Config.choices`, and it replays the stage.
- **Draws.** Only `uniform` and `normal`. The normal quantile is a float, made exact to within 1e-9.
- **Not verified.** `switch`, `sees` and chance mechanisms have no case. The order of firings "by receiver
  and declaration" has no case of its own. The interpreter refuses a legs flow whose request moves
  between moments.
