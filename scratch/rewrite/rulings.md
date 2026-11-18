# Rulings for gate G0

Sources: `a1/`, `a2/`, `a4a/`, `a4b/`, `a5/` FINDINGS.md, `g0-notes.md`, `open-items.md`. All six prototypes have reported. Ruling ids are R-<prototype>-<nn>.

## Part 0. How to read this

1. Part 1: give your word on each decision (take the rule, or the alternative).
2. Parts 2 and 3: approve together, or name the ids you want to discuss. Part 3 stands unless you object.
3. Part 4: confirm what the first version leaves out, and the message a model gets.
4. Part 5: approve the proposed resolution of each disagreement, or pick the other side.
5. Parts 6 to 8 need no answer. Part 9 asks you to confirm the changes to the plan.

What was not verified:
- A1: no type checker ran; types were applied to 13 models by hand. 16 refusals belong to a checker
  that does not exist (R-A1-04, 05, 09, 12, 15, 17, 19, 20, 21, 23, 24, 26, 29, 30, 31, 32).
- A5: nothing was executed; no new compiler exists. A4b: R-A4b-07 rests on two runs and no checker.
- A4a: `measure.py` was not run end to end; 150 stores and 10,000,000 pieces are not tuned.
  A2: `switch`, `sees` and chance have no case in its interpreter.

## Part 1. Decisions that need your word (most weight first)

### D0. What the solver does at a size that it cannot solve in time
Question: two ranks of the spec's selection order are costly on a large network that is short of
supply: inherited fair sharing, and the last distance step after it. What does the first version do
there?
Measured (A3, `a3/FINDINGS.md`):
- Fair sharing, exact method. At 3,000 places: 50 to 172 programs and 1.1 to 4.4 s, by the degree
  of shortage (552 to 1,880 claims below 100%). At 30,000 places, base case (4,315 claims below
  100%): 467 programs and 128 s. At 30,000 places with need x1.45: it failed part way (a later
  program was infeasible). 10,000 places was not measured.
- The distance step after a fair rank: A3's own method does not converge at 3,000 places. The QP of
  HiGHS is exact there and takes 38 s.
- The distance step with no fair rank before it: 0.5 s at 3,000 places; at 30,000 places it did not
  finish in 590 s. Note (main session): an earlier and narrower method, for equalities and bounds
  only, took 0.1 to 2.7 s at 30,000 places (`scratch/networks/nearest.py`, other code and another
  run). The general method is far slower; the solver slice should keep the narrow one for a problem
  that has no inequality row.
- A solve in which no claim is short leaves the fair rank nothing to do (by construction; not timed).
- Members that join and leave: a go. At 30,000 places, 300 flows join in 0.90 s on the kept
  instance, against 6.12 s for a problem formed fresh, with equal optima.
- Inequality rows in the distance step are right on 200 random problems against an exact
  calculation (7e-9).
Rule (R-A3-04, R-A3-05): keep the selection order as the spec has it. Each of the two ranks has a
budget. A solve that passes it stops the run by name (`fair-sharing budget exceeded (N levels)`,
`distance step: no answer within budget`). The engine never gives another answer.
Alternative A: change the language for a large solver: it must write objectives that leave nothing
to inherited fair sharing, and the compiler refuses one that does not.
Alternative B: hold the solver slice until a faster exact method exists.
Example: the worked network with 30,000 places. Supply meets every request: it runs under the rule.
Supply is short: under the rule it runs up to about 3,000 places and about 170 levels, at seconds
to about 40 s for each solve, and stops by name above that.
Cost if changed later: none for model text under the rule; a faster method later only moves the
limit. Alternative A changes what an author must write. Ids: R-A3-04, R-A3-05.
Note (main session): this is the network use that started the rewrite. The rule keeps every answer
right, and it is honest about the limit. A faster exact method is a research task for the solver
slice; A3 left a method of groups with a proof sketch and two counterexamples (`a3/STATE.md`).

### D1. The spelling of chance and choice
Question: how does an author write an outcome picked by chance, or by an actor?
Rule (R-A5-08): one `switch` whose selector is a producer: `switch chance(A: p, B: else):`,
`switch choice(OPEN: 1, WAIT: else):`, or a condition `switch (A if C1 else B if C2 else E):`. The case
labels give the selector its enum type.
Alternative (R-A1-18, R-A1-22): a value draw, `switch categorical(A: p, B: q).draw():`, with no
`chance` or `choice` word.
Example:
```
switch chance(FIXED: 0.7, FAILED: else):            # rule: remainder 0.3; median run picks FIXED
switch categorical(FIXED: 0.7, FAILED: 0.3).draw():  # alternative: both written; no `choice` form
```
Cost if changed later: the 75 events with several outcomes are translated by hand (A5); a change
after migration rewrites each of them. Ids: R-A5-08, R-A1-18, R-A1-22. See Part 5, C1.
Note: in a median run `.draw()` returns the median (spec:164), and a categorical has none; the
spec's chance rule (the most likely eligible outcome) fits `chance(...)`, not `.draw()`.

### D2. An override that is a distribution
Question: can a run's override replace a drawn input's distribution?
Rule (R-A1-19): no. An override is a number in v1, inside the input's range. A distribution edit
belongs to the wrapper of an experiment (spec:803).
Alternative: admit a distribution-valued override, which replaces the descriptor before any draw.
Example:
```
input repair_time = uniform(1 h, 3 h).draw()
override 5 h               -> refused under both: outside [1 h, 3 h]
override uniform(2 h, 4 h) -> rule: refused ("an override is a number"); alternative: accepted
```
Cost if changed later: none for model text (additive). But today's uncertainty studies give
distributions through an edit document (`napkin/model/runs.py:20`, `:343`); under the rule they
lose that path until the wrapper carries it. Ids: R-A1-19. See Part 5, C6.

### D3. What the engine refuses at scale
Question: may a rate read a value that moves between moments in a large connected set?
Rule (R-A4a-05, R-A4a-06): yes up to 150 stores (one component); above that it is refused before the
run, with a message that names the flow, the value, the size of the set and the flows that join it.
Alternative: allow it at any size, and let the run be slow (sparse integrator).
Example: 30,000 places whose routes ask `rate * stock / (stock + half)`.
- Rule: refused with message 1 (Part 4).
- Alternative: 31 to 36 s while no stock rests; an estimated 1.5 to 10 min once stocks rest (T2.3).
Cost if changed later: low. Allowing later breaks no model. Ids: R-A4a-05, R-A4a-06.

### D4. `none` in arithmetic, comparisons and reductions
Question: does `none` spread, or fail at once?
Rule (R-A2-06, R-A2-07): it spreads through arithmetic, ordering and reductions; `==`/`!=` test for
it; a decision that receives it (condition, guard, selector, delay) fails the run. `min`/`max`
over nothing is `none`, and `max(0, c.x)` over nothing is 0.
Alternative: any arithmetic or ordering on `none` fails the run at once; `min`/`max` over nothing fail.
Example:
```
reading = none
shown = formula(reading + 1)   # rule: none (a report shows it); alternative: the read fails the run
when shown > 3: ...            # rule: fails here, naming the value
```
Cost if changed later: from spread to fail breaks reports that show absent values. Ids: R-A2-06, R-A2-07.

### D5. Two stages of one round that touch one value
Question: when two stages of one round write or read one value, what happens?
Rule (R-A2-03, R-A2-22): stages commit one after another; a later stage reads what an earlier one
wrote; the last `=` wins and `+=` adds up. A solver result read after another stage changed its
inputs gives the last settled result, with a warning.
Alternative: every stage reads the state at the start of the round; two different writes to one
value fail the run, and so does such a read.
Example:
```
beans = 20 g; at 1 h stage A: beans = 8 g; stage B: beans += 4 g
rule: 12 g          alternative: fails, "conflicting writes to grinder.beans ... at t = 1 h"
```
Cost if changed later: high. Models that depend on the order (R-A2-01) would fail. Ids: R-A2-03, R-A2-22 (with R-A2-01).

### D6. Budgets for occurrences and rounds
Question: which budgets stop a runaway run, and at what defaults?
Rule (R-A4b-03): three budgets: `max_occurrences` 1,000,000 starts of one event; `max_active`
100,000 alive at once; `max_rounds` 1,000 rounds of one moment. The `max_active` message names the
oldest occurrence, the step it waits at, and how many wait there.
Alternative (R-A2-13, R-A2-04): two budgets: 1,000 occurrences of one event alive at once, and 100
rounds at one time.
Example: an hourly clock starts `inspect`, which waits `until this.cleared` for ever.
- Both stop it with the gate named; they differ only in when: A2 at 1,000 alive, A4b at 100,000.
- A model with more than 1,000 legitimate live occurrences of one event runs under A4b and stops under A2.
Cost if changed later: low. These are configuration limits. Ids: R-A4b-03, R-A2-13, R-A2-04. See C4.
Note: A4b measured a load of 1,000 alive at once; A2's default would stop at that size plus one.

### D7. What stays readable on a finished occurrence
Question: can a report read a finished occurrence's formulas?
Rule (R-A2-10): everything stays readable, frozen at the finish, formulas as values.
Alternative (R-A4b-02): the same, except a retained local formula is not readable after the finish.
Example:
```
job(amount) with double = formula(amount * 2), started with 7, done at 1 h
at 2 h: job.occurrences.at(t).double   # A2: 14     A4b: an error
```
Cost if changed later: low. Loosening later is additive. Ids: R-A2-10, R-A4b-02. See Part 5, C5.

### D8. A range with one bound, and the scale hint word
Question: may a range leave one side open, and is `size` renamed `scale`?
Rule (R-A5-11): `in [0, none]` means "at least 0, no upper bound". The migration writes it on each
old stock that has no range, because today such a stock cannot go below zero. In the new language a
store with no range has no bound, as the spec says. `size S` becomes `scale S`.
Alternative: keep `size`; allow no open side, so each migrated stock gets a large finite upper bound.
Example:
```
due: tunings = this.need in [0, none] scale 20000 tunings
store of 2 L, a drain of 1 L/h, read at 3 h: rule 0 L (the flow stops at 2 h); unbounded: -1 L
```
Cost if changed later: high. It changes the meaning of every store migrated without a range.
Ids: R-A5-11, R-A1-08. See Part 5, C2 and C3. Note: "the flow stops at 2 h" follows the spec's
rule at a lower bound (A2 case 2); A5 ran nothing. Note (main session): the example shows why the
migration must write the bound; it is no default of the language.

### D9. Where comparisons of runs live
Question: now that `versus` goes, where is a pair of runs to compare written?
Rule (R-A5-06): named runs stay in the model; pairs go into `brief.toml` as `[[comparison]]` with
`run` and `against`; `featured` names one. A study call takes a list of runs.
Alternative A: an `experiments.toml` that the core reads. Alternative B: a `comparisons:` block in the model.
Example: `delayed_human = "Delayed" + "Human team"` stays in the model; `brief.toml` gets
`[[comparison]]`, `run="delayed_human"`, `against="delayed_refuses"`.
Cost if changed later: low. Only 11 lines move. Ids: R-A5-06.

### D10. Report selection
Question: how does a package choose what a report shows by default?
Rule (R-A5-09): an `output` becomes a named value, `name: formula(u) = formula(E) in [0, none]` (no
range if it was `signed`). A package `report:` block lists the default selection, one
`path [cumulative] [lag D]` per line. Each `cumulative` is a claim the compiler must prove.
Alternative: a report flag on each declaration.
Example: `report:` / `tunings_done cumulative`.
Cost if changed later: every migrated output moves again. Ids: R-A5-09.

### D11. No `if` in a stage
Question: does a stage have an `if` block?
Rule (R-A1-22): no. A single condition is the stage guard `after D when C:` or a `switch` with
`true:`/`false:` cases.
Alternative: add `if C:` and `else:` in stages.
Example: `if this.low:` in a stage is refused ("a stage has no `if` line"); the alternative accepts it.
Cost if changed later: none. `if` can be added later without breaking a model. Ids: R-A1-22.

### D12. Spaces around units
Question: is `48 h/2` half of 48 hours?
Rule (R-A1-01): a unit is one word after its number and one space; `-` multiplies inside a unit;
an operator that touches a unit is refused with a message to add spaces.
Alternative: read the unit as an operand, so `48 h/2` means `(48 h)/2`, and use `*` for a product of units.
Example: `48 h/2`: rule refuses ("write `48 h / 2`"); alternative 24 h. `3 person-years`: one
unit under the rule.
Cost if changed later: the alternative breaks the 19 declared units and 125 uses that hold `-`. Ids: R-A1-01.

### D13. Parameters that are stocks
Question: can an event take one stored field by reference?
Rule (R-A1-21): a parameter with a unit type is a copy of a value; one with a template type is a
reference to the entity, whose fields a flow or `move` can use. No reference to a single field in v1.
Alternative: `source: stock L` passes one stored field by reference.
Example: `fill = event(level: L)` with `move 2 L from level to this.store`: refused ("level is a
copy and holds no stock"); the alternative accepts it.
Cost if changed later: none. The alternative can be added later. Ids: R-A1-21.

### D14. A declared flow's property that reads a later local
Question: may a flow's plain property initializer read a local declared below it?
Rule (R-A1-23): no. Plain initializers, including a flow's property initializer, read only names
above them; a retained `formula(...)` may read later locals.
Alternative (R-A2-20): all flows of an occurrence are made after all its locals, so a flow may name any local.
Example:
```
flow delivery: batch -> this.customer.water
    request = left / (2 h)        # A1: refused, "left is declared below"; A2: accepted
left: L = amount
```
Cost if changed later: low. Loosening is additive. Ids: R-A1-23, R-A2-20. See Part 5, C8.

### D15. A flow may take more than its request
Question: may a flow be given more than it asked when that helps an earlier objective?
Rule (R-A3-07, the spec's wording): yes. An author forbids it with `capacity = this.request`.
Alternative: a request is also a cap on every flow, in the language.
Example (`a3/explore/bridge.py`): places J (supply 10), X (asks 0.1), Y (asks 0), B (asks 10), five
routes, and `minimize(sum(unmet))`. Under the rule X takes 4.65, which lowers its level, and B gets
5.35: unmet 4.65. With a cap at each request X takes 0.1 and B gets 0.8: unmet 9.20.
Cost if changed later: every allocation under a route law can change. Ids: R-A3-07.
Note (main session): the rule can surprise: a place "uses" 46 times what it asked. The example
belongs in the docs, with the one line that forbids it.

### D16. What to retire and not port
Question: which parts of today's code are not carried into the new engine? (Sizes and users: `g0-notes.md`.)
Rule (main session), each with what takes its place:
- The second reading of the rules (`reading='every'`, `timeline.check`): retire. One test file uses it.
- Whole-run pickles in the run store: retire. The record of a run takes their place (R-A4a-07).
- `Partition` checks: retire. `assert a + b in [T - tol, T + tol]` says the same (R-A5-10).
- `tools/compare.py` (1,689 lines): rewrite small, over the record: names, values, trace.
- The pruning of parts that cannot act under a set of start-state options (`lower/starts.py`, 621
  lines): retire. The evidence trail of a report then says what a run exercised, from its record.
Alternative: port each as it is.
Example: with the option "plant closed", today's report leaves out the records of the plant's
events before the run, by a proof that they cannot fire. Under the rule the report leaves them out
because they did not fire in that run; a part that could fire and did not is no longer told apart.
Cost if changed later: low. Each can be built again on the record. Ids: P8.

### D17. One error in the spec
Question: is the `unserved_volume` example corrected?
Rule: yes. In the water model the unserved rate falls to zero when service returns, and the
unserved volume accumulates that rate and never falls (`water.scn:264`, `:374`, `:701`). The spec's
example calls the volume a current one that "can fall when service returns".
Alternative: keep the example and rename its quantity to a present shortfall.
Example: after service returns at 5 h, the report at 6 h shows the volume lost up to 5 h (rule), or
0 (a present shortfall). A5's check refuses a translation that turns the first into the second.
Cost if changed later: none for the engine; the docs follow the spec. Ids: row 71, R-A5-15.

## Part 2. Rulings that follow the spec's proposal or today's behaviour

### 2a. The spec's own proposal, the plan's, or today's behaviour
- R-A1-02: `<...>` opens a collection where a value starts; after a value `<` compares; one-way chains.
- R-A1-03: after a declaration's `=`, a trailing `in [lo, hi]` is the range; in an assignment it is refused unbracketed (spec:66).
- R-A1-05: `bool` is its own type; `1 if ready else 0` for a number (spec:54).
- R-A1-11: `this` is always the owning entity; bare names are the invocation's own.
- R-A1-15: a writable `formula(T)` binding takes only another formula (spec:109).
- R-A1-16: `.request` and `.capacity` take a rate or `formula(rate)`; only built-ins have this type (spec:109).
- R-A1-18: constructors are today's families with today's positional order; `.mean`, `.std`, `.lower`, `.upper` consume no draw; `.draw()` not in a formula. (Its `categorical` is in D1.)
- R-A1-20: a leg in `priority(...)` is `link.forward` or `link.backward`; a bare reversible link is an error (spec:191).
- R-A1-26: a flow with legs holds named `flow leg: a -> b` lines; the parent has only `.served_fraction` (spec:657).
  Note: the parser's message for a property under the parent is weak; A1 asks for a better one.
- R-A1-28: a row is named by its `id` cell, `sites.clinic`; no name by position (spec:795).
- R-A2-05: setup is round zero; triggers get their first check after setup settles (the spec's trigger table).
- R-A2-18: what a store holds when it becomes a store is an opening balance from outside in the ledger (the spec's ramp example).
- R-A2-19: `move` may debit and credit a `readonly` stock; a direct assignment stays an error (spec's proposal).
- R-A2-21: an occurrence's store must be empty at normal completion, or the run fails naming it (spec's recommendation).
- R-A5-01: keep `scenario "T"` with its lines under it; `resolution` keeps its old meaning (0 lines change).
- R-A5-02: `record n: kind "text"`, the ID on the line under it, then `claims:` and `datum:`; `notes:` unchanged (spec's candidate).
- R-A5-03: precedence: external edit, option, `change`, variant instance line, template; conflicts are errors (old compiler's order).
- R-A5-04: keep `options` and `runs:` with full paths; only an `input` can be set by an option.
- R-A5-05: a number or yes/no set by an option or `change` needs a record (spec:799); breaks no model (104 of 108 have one).
- R-A5-07: an instance replaces a template formula with `m = formula(E)`; a scalar is refused.
- R-A5-12: the author names each leg; a migration tool may default to the target store's name.
- R-A4a-07: the record is the trace plus one history of pieces for each recorded value; everything is recorded under 10,000,000 pieces, else what the request names (the plan's proposal).
- R-A3-08: a solver-local unknown with no initializer has the reference zero in its unit, with its declared scale, else its width, else one canonical unit (the spec's proposal).
- R-A4a-08: the key of a stored run covers program (no labels), configuration, mode, seed, choices, numerical settings and code; a manifest says what it serves (the plan's proposal).

### 2b. New rules where only one answer is sensible (tagged `owner` by their prototype)
- R-A1-04: a capital first letter means a template or an enum member; a bare member needs an expected type.
- R-A1-06: the type rules of `a1/types.md`; enums compare only within one enum; text has only `==`, `!=`.
- R-A1-07: `#` ends a row; texts wrap on deeper rows; only `\"` and `\\` escape; expressions wrap only inside brackets.
- R-A1-08: the reserved list of `parser.py:43`; Python's keywords are not reserved. See Part 5, C2 and C7.
- R-A1-09: no shadowing; a name equal to a built-in member of its owner's type is an error. See C7.
- R-A1-10: `.start(...)` is a statement and gives no handle.
- R-A1-12: no `run` path in source; a model cannot read its mode or seed.
- R-A1-13: value arguments of a constructor take the declared unit when it is the whole initializer.
- R-A1-14: `after D` with no colon waits and does nothing.
- R-A1-17: no operator copies a formula; `formula(x)` follows later replacements of `x`.
- R-A1-19 (except overrides, D2): a draw's range is its support; a transformed draw takes the declared range; correlations are out (Part 4).
- R-A1-24: a stage declares no name (Part 4).
- R-A1-25: a trigger has no name; an event may have several; a trigger starts only its own event.
- R-A1-27: one `move amount from source to destination` form; the call form is refused.
- R-A1-29: a key is given where used, `c.by(field)`; a duplicate member in a literal is a setup error.
- R-A1-30: links are fixed during the run; no stage assigns a link.
- R-A1-31: an occurrence's fields are written only by its own invocation.
- R-A1-32: `assert this.primary != this.backup` asserts distinct links; setup checks it once.
- R-A2-01: starts register in the order their `.start` ran; stages due in one round commit oldest occurrence first.
- R-A2-02: a start on a collection runs members in key order, ties in creation order.
- R-A2-08: `elapsed` restarts only when the committed value differs from the value before the stage.
- R-A2-09: `delayed(x, 0 h)` reads the committed value, not the stage's own write.
- R-A2-11: a saved reference to an occurrence pins its identity.
- R-A2-12: a claim is decided after every claim that any endpoint ranks ahead of it; contradictions share a tier.
- R-A2-14: a human choice pauses inside the stage, before its commit; the answer replays the stage.
- R-A2-15: an `assert` on state is checked after every round, after every moment, and at each contact between moments.
- R-A2-16: a report reads the record after the run; an invalid read shows "unavailable" with the reason.
- R-A4b-06: the engine certifies `q >= v`, `q <= v`, `t >= X` and conjunctions with one crossing; a tolerance of 1e-10 times the store's size or 1e-8 h; strict `>`/`<` on a moving value is a setup diagnostic.
- R-A4b-07: proofs ("never falls", "one way", zero face) cover every writer site, of entities and of events.
  Note: rests on the rule and two runs; `spike/proofs.py` is not written.
- R-A5-13: members are read as `this.x`, `this.link.x`, `Template.instances.x`; members may be named `status`, `start`, `capacity`, `size`. See C7.
- R-A5-14: `sees thing.field` is written under the actor.

## Part 3. Technical rulings (they stand unless you object)

- R-A2-17: the key of each draw is the seed, the site of the draw, and its owner.
- R-A2-23: the distance step divides each flow by one canonical unit of its dimension. The spec should say so.
- R-A3-01: an attained optimum is kept by pinning from the duals, not by a row; the final answer is checked against each optimum, and a failed check is a failure by name.
- R-A3-02: all numerics in working units; duals are zero below 1e-9; optima are kept to 1e-7 relative; a fair level is known to 1e-7; a formula that reads an enforced equality compares to 1e-7 relative.
- R-A3-03: dual simplex cold and then warm on one kept instance; fair sharing tier by tier with the exact sequential method; the two distance steps, flows first.
- R-A3-06: one kept instance for each run; a flow that joins is a new column, a flow that leaves deletes one, and the basis is carried.
- R-A3-09: two closed forms of today's allocation stay as fast paths (a proportional group alone; a priority order with no ties); a flow in two binding groups, ties in a priority order, and flows with legs go to the solve library.
- R-A4a-01: each template is a pool of rows; links are int32 columns of row numbers; one store vector; a sparse incidence.
- R-A4a-02: rows are kept in the order of their ids; reports still list them in file order.
- R-A4a-03: connected sets are cut over stores and flows by the refined rule (a store that cannot hold a flow back joins nothing).
- R-A4a-04: arrays for a store alone or with one flow; one component up to 150 stores; lines above; rings go to lines.
- R-A4b-01: one pool of frames for each (template, event); a row is one occurrence for good, never reused.
- R-A4b-04: a join or a leave is a write of the membership name; the reader graph is built over templates.
- R-A4b-05: each endpoint keeps an exact sum of its members' requests, so rates match a freshly formed problem bit for bit.
- R-A4b-08: `Run` is cut into ten mixin modules by moves (`LAYOUT.md`); already accepted.
- R-A5-15: a migration passes only with no difference in any group of the check; it lists every output proved cumulative.

## Part 4. Not in the first version

| Thing | Message a model gets | Id |
| --- | --- | --- |
| Correlated draws | "draws are independent: share one stored draw to tie two values" | R-A1-19 |
| A distribution-valued override | "an override is a number" (see D2) | R-A1-19 |
| Short-lived names in a stage | "a stage declares no value: declare a local at the start of the event, before its timing steps, and assign to it here" | R-A1-24 |
| A handle from `.start(...)` | "starts an occurrence and gives no value" | R-A1-10 |
| `if` in a stage | "a stage has no `if` line" (see D11) | R-A1-22 |
| A reference to a single stored field | "level is a copy and holds no stock" (see D13) | R-A1-21 |
| A `run` path | none written: the resolver refuses `run` as an unknown name | R-A1-12 |
| A row named by position | none written | R-A1-28 |
| A model-declared `rate \| formula(rate)` type | none written | R-A1-16 |
| `{item}/h` units | none written (0 uses in the catalogue) | R-A1-01 |
| A moving rate in a set of more than 150 stores | "`<flow>`: its request reads `<value>`, which changes between moments. The flow is in a connected set of `<n>` stores (more than 150), whose rates are held between moments. Make the request read a value that changes only at moments (an input, a reading, a value set by an event), or cut the set: `<at most five flows>`." | R-A4a-05 |
| The same, with a ring | message above, plus "the set holds a ring of stocks that feed one another: `<a> -> <b> -> ... -> <a>`" | R-A4a-05 |
| A record over its budget | "the request names about `<n>` pieces (...); the budget is 10,000,000. Name fewer rows, a reduction over the table, or a coarser reading." | R-A4a-05 |
| The history of a finished occurrence's local store | "`batch` of a finished `deliver` reads 0 L; its history is not kept" | R-A4b-02 |
| Strict `>`/`<`, two crossings, or a crossing with no closed form, on a moving value | "`water > 16 L`: a condition on a value that moves between moments must compare it by >= or <=; use `>= 16 L` or schedule an inspection" (only the strict case has a written message) | R-A4b-06 |
| Copies `* k` and `copy` | "write the instances or use a table" | R-A5-10 |
| `while` on an event header | "use `after D when C:`" | R-A5-10 |
| `count(e.outcome)`, `since(e.outcome)` | "start an event in that case and read it" | R-A5-10 |
| Status lines and `output m` in an instance | none written | R-A5-10 |
| `assert C within TOL` | "write `x in [lo, hi]`" | R-A5-10 |

Rows that `open-items.md` marks "scope". The main session wrote these; no prototype did:

| Thing | Message a model gets, or what an author writes | Row |
| --- | --- | --- |
| A list of plain values | "a collection holds entities, flows or occurrences: put the value on a member and reduce the field" (the spec's own rule) | 10 |
| Interruption, cancellation, joining, a limit on concurrency | No form exists, so there is nothing to refuse. An occurrence runs to its end; an author stops its work with a guard on each later stage, or with `until` | 25 |
| An absolute `at T:` | Refused by A1's parser with its own message (`a1/corpus/refused.txt`); write `after D:` or a trigger `when t >= T` | 26 |
| A read of an occurrence at an earlier time; a member by position | "a member is read with `.at(key)`: a collection has no positions" | 30 |
| A resource that is held and released | No form. A store with a flow out and a flow back, or a flow with legs, models it | 32 |
| `formula.diff(...)` | "`.diff` is not in the first version" | 35 |
| `assert initially` | Refused by A1's parser with its own message; an `assert` over inputs is checked once at setup (R-A2-15) | 36 |
| A change of a flow's ends during a run; a formula set by configuration other than R-A5-07 | "the ends of a flow are fixed"; links are fixed too (R-A1-30) | 45 |
| A nonlinear route law, a yes-or-no unknown | Refused by the solver by name; the message is A3's | 55 |
| A type that tells two substances of one dimension apart | No form. Two fields with one unit can be joined by a flow; the author keeps them apart | 55 |

Four rulings that no prototype gave, proposed by the main session:

- **Row 38, a citation for a column or a cell.** A column cites its record in its header, as today
  (`level: m @survey`). A citation for one cell is not in the first version; rows from two sources
  go in two tables, or the table gets a column for each source's values. [owner]
- **Row 39, what the engine infers for a scale.** As today: the size of a quantity comes from its
  bounds, its start and the stores that it is joined to; `scale S` replaces it (R-A5-11). [technical]
- **Row 47, evidence for an event argument.** None is asked. An argument is a value that the model
  computed; the record is on the declaration that it came from. [owner]
- **Row 63, status displays in a report.** A report shows the status display of every entity that
  declares one, as today. The `report:` block selects values only (R-A5-09). [owner]

## Part 5. Where two prototypes disagree

**C1. Chance producer.** A5 (R-A5-08): `switch chance(A: p, B: else):` and `switch choice(...)`. A1
(R-A1-18, R-A1-22): `categorical(A: p, B: q)` with `.draw()`, and one `switch` form.
Proposed: take both, each in its place. `chance(...)` and `choice(...)` are selectors that stand
only after `switch`, inside A1's one `switch` form; `categorical(...).draw()` stays for a drawn value.
Reason: the spec gives a chance its own median rule and eligibility (spec:164, :672), which a
`.draw()` does not have; `choice` has no form in A1. Note: today a categorical is written with
keywords, `categorical(low=0.7, high=0.3)` (`napkin/model/uncertain.py`); A1 writes `A: p`.

**C2. A clause word after a bare number.** A5 (R-A5-11) turns `size S` into `scale S`. A1 (R-A1-08):
such a word must be reserved, or the tokenizer reads it as a unit (83 present lines).
Proposed: add `scale` to the reserved list and drop `size`, which then stays free as a member name
(R-A5-13). Reason: both rulings then hold, and `= 0.6 scale 1` tokenizes as a clause.

**C3. A store with one bound.** A5 writes `in [0, none]`. The spec says v1 intervals are closed
(spec:66). A1's range is `in` and two expressions (`parser.py:1658`), so `none` parses as a bound;
whether a checker accepts it is not verified.
Proposed: allow `none` only as a bound of a declared range, meaning "no bound on this side"; the
finite side stays closed. Say so in the spec. Reason: R-A2-06 makes `x <= none` give `none`, so
`none` as a bound needs its own stated meaning.

**C4. Budgets.** A2: 100 rounds at one time (R-A2-04), 1,000 alive of one event (R-A2-13). A4b
(R-A4b-03): `max_occurrences` 1,000,000, `max_active` 100,000, `max_rounds` 1,000.
Proposed: A4b's three budgets and defaults, with A2's gate message (both name the oldest
occurrence and its gate). Reason: A4b's set contains A2's two; A4b ran 1,000 alive as a normal load.
Neither default was tuned.

**C5. A finished occurrence.** A2 (R-A2-10): everything frozen, formulas as values. A4b (R-A4b-02):
the same, but a retained local formula is not readable; it adds both forms of a parameter, the
flow's last `capacity`, `actual_rate` 0, no `.flows` membership, and the history message.
Proposed: A2's rule on formulas with A4b's details. Reason: one rule for all fields; A4b gives no
reason for the exception, and its row stays anyway (R-A4b-01). (D7.)

**C6. An override that is a distribution.** A1 (R-A1-19): a number only. Today: an edit document
gives inputs distributions for uncertainty studies (`napkin/model/runs.py:20`, `:343`).
Proposed: keep R-A1-19 in model text and in a run's override; let the experiment wrapper (spec:803)
accept a distribution edit, as today's edit document does. Reason: today's studies keep a home, and
the model's contract of one trajectory per configuration holds. (D2.)

**C7. Names.** A5 (R-A5-13): members may be `status`, `start`, `capacity`, `size`; `from`, `to`
reserved; a top-level thing is readable by its bare name everywhere. A1 (R-A1-08): the reserved list,
which reserves neither those four nor `scale`; (R-A1-09): no shadowing, built-in member names clash
only on an owner that has them; (R-A1-11): bare names are the invocation's own.
They agree on the four member names. They conflict on bare names: A5 lets a bare name be a
top-level thing, A1 says a bare name is the invocation's own.
Proposed: a bare name is first the invocation's own; an invocation name equal to a top-level thing
is an error (A1-09's no shadowing, extended). Reason: no line then changes meaning when a top-level
thing is added. Not verified against the catalogue: no census of such clashes exists.

**C8. Forward references.** A1 (R-A1-23): a flow's plain property initializer reads only names
above it. A2 (R-A2-20): all flows are made after all locals, so a flow may name any local. Both
allow a retained `formula(...)` to read later locals.
Proposed: A1's rule. Reason: one written order for every plain initializer; an author who needs a
later local writes `formula(...)`. (D14.)

**C9. The retirement message.** A2 (R-A2-21) names occurrence, store, amount, time. A4b adds advice:
"Wait until it is empty, move the rest to a stock, or send it to SINK."
Proposed: A2's content with A4b's advice. Reason: no conflict of rule, only of text.

## Part 6. Coverage

No row is without a ruling now. The prototypes left rows 10, 25, 26, 30, 32, 35, 36, 38, 39, 45,
47, 55, 63, 71, P6 and P8 open, in whole or in part; the main session closed them (Part 1, D16 and
D17; Part 4; Part 9). The rows of A3 are pending.

| # | Item | Prototype | Ruling |
| --- | --- | --- | --- |
| 1 | `move` on a `readonly` stock | A2 | R-A2-19 |
| 2 | Boolean type | A1 | R-A1-05 |
| 3 | Complete type specification | A1 | R-A1-06 (`a1/types.md`) |
| 4 | A `run` path | A1 | R-A1-12 |
| 5 | `this` | A1 | R-A1-11 |
| 6 | Distribution argument units | A1 | R-A1-13 |
| 7 | Unit arithmetic | A1 | R-A1-01 |
| 8 | Wrapped clauses, escapes, comments | A1 | R-A1-07 |
| 9 | `min`/`max` over nothing | A2 | R-A2-07 |
| 10 | General lists of scalars | scope | not in the first version (Part 4) |
| 11 | Writable `formula(T)` binding | A1 | R-A1-15, R-A5-07 |
| 12 | Rate or formula property; copy of a formula | A1 | R-A1-16, R-A1-17 |
| 13 | Default selection in `report:` | A5 | R-A5-09 |
| 14 | Distribution constructors | A1 | R-A1-18 (C1) |
| 15 | Unbounded draws, overrides, correlations | A1 | R-A1-19 (D2) |
| 16 | A leg in `priority(...)` | A1 | R-A1-20 |
| 17 | Rounding of an enforced equality | A3 | R-A3-02 |
| 18 | Distance step convention | A3 | R-A3-02, R-A3-05, R-A2-23 |
| 19 | Affine inequalities in the distance step | A3 | R-A3-05 (D0) |
| 20 | Object parameters | A1 | R-A1-21 |
| 21 | `switch`; Boolean shorthand | A1 | R-A1-22, R-A5-08 |
| 22 | Order of a start on a collection | A2 | R-A2-02 |
| 23 | Forward references | A1, A2 | R-A1-23, R-A2-20 (C8) |
| 24 | Short-lived names in a stage | A1 | R-A1-24: not in the first version |
| 25 | Interruption, cancellation, joining, concurrency | scope | not in the first version (Part 4) |
| 26 | Absolute `at T:` | scope | not in the first version (Part 4) |
| 27 | Retirement rule | A2 | R-A2-21 |
| 28 | Contact tolerances, certified predicates | A4b | R-A4b-06 |
| 29 | Triggers: names, number, targets | A1 | R-A1-25 |
| 30 | Earlier reads of an occurrence; positional indexing | scope | not in the first version (R-A4b-02; Part 4) |
| 31 | Syntax and reads of a flow with legs | A1 | R-A1-26, R-A5-12 |
| 32 | A held-and-released resource | scope | not in the first version (Part 4) |
| 33 | Choice and chance spelling | A5 | R-A5-08 (D1, C1) |
| 34 | Opening balance from outside | A2 | R-A2-18 |
| 35 | `formula.diff(...)` | scope | not in the first version (Part 4) |
| 36 | Where an `assert` is checked; `assert initially` | A2 | R-A2-15; `assert initially`: not in the first version (Part 4) |
| 37 | Record syntax | A5 | R-A5-02 |
| 38 | Citation for a column or a cell | A5 | main session (Part 4): a column, as today; a cell: not in the first version |
| 39 | Scale hints | A5, A4a | R-A5-11; what the engine infers: main session (Part 4) |
| 40 | `resolution` | A4a | R-A5-01: it keeps its old meaning, the longest step of a numerical segment |
| 41 | `elapsed`; zero-delay read | A2 | R-A2-08, R-A2-09 |
| 42 | `move(...)` shorthand | A1 | R-A1-27 |
| 43 | Reserved words | A1 | R-A1-08 (C2, C7) |
| 44 | Row by position; `id` | A1 | R-A1-28 |
| 45 | Formula configuration, structural changes, reference contracts | scope | R-A1-30, R-A5-07; the rest: not in the first version (Part 4) |
| 46 | `use`, `variant`, `change`, options | A5 | R-A5-03 |
| 47 | Evidence for overrides; for event arguments | A5 | R-A5-05; event arguments: main session (Part 4) |
| 48 | Where comparisons live | A5 | R-A5-06 |
| 49 | Shadowing; enum names; formula replacement | A1 | R-A1-09, R-A1-04, R-A1-17 |
| 50 | Reusable key; duplicates in a literal | A1 | R-A1-29 |
| 51 | Order of simultaneous starts | A2 | R-A2-01 |
| 52 | Readable fields of a finished occurrence | A2, A4b | R-A2-10, R-A4b-02 (D7, C5) |
| 53 | A stable handle | A1 | R-A1-10: not in the first version |
| 54 | Tolerances for ranked optima | A3 | R-A3-01, R-A3-02 |
| 55 | Nonlinear route laws; two substances | scope | not in the first version (Part 4) |
| 56 | Conflicting writes | A2 | R-A2-03, R-A2-22 (D5) |
| 57 | Reset cycles | A2 | R-A2-04 |
| 58 | Setup order | A2 | R-A2-05 |
| 59 | Precedence, model identity, evidence | A5 | R-A5-03, R-A4a-08, R-A5-05 |
| 60 | Another spelling of units | A3 | R-A3-02, R-A3-08, R-A2-23 (the worked network in kW agrees to 4.4e-16 W; not checked at scale) |
| 61 | Zero reference of a solver unknown | A3 | R-A3-08 |
| 62 | Scale of moving coefficients; thresholds on solver results | A4a, A3 | R-A4a-05, R-A4a-06; thresholds: main session: a solver result changes only at moments, so a condition on it is read at moments, as for a discrete value |
| 63 | Status display references; unavailable history in a report | A5, A2 | R-A2-16; status displays: main session (Part 4) |
| 64 | Distinct links | A1 | R-A1-32 |
| 65 | Where a human choice pauses | A2 | R-A2-14 |
| 66 | Invalid history read; pinning | A2 | R-A2-16, R-A2-11 |
| 67 | `none` | A2 | R-A2-06 (D4) |
| 68 | Legs ranked differently | A2 | R-A2-12 |
| 69 | Budget for unfinished occurrences | A2, A4b | R-A2-13, R-A4b-03 (D6, C4) |
| 70 | Cost of fair sharing | A3 | R-A3-04 (D0) |
| 71 | `unserved_volume` error | owner | D17 |
| P1 | What a run records; when a stored run serves | A4a | R-A4a-07, R-A4a-08 |
| P2 | Connected sets; limit of each way | A4a | R-A4a-03, R-A4a-04 |
| P3 | Fallback of each numerical no-go | A3 | R-A3-04, R-A3-05 (D0); R-A4a-05 for moving rates |
| P4 | Links and flows across tables | A4a | R-A4a-01, R-A4a-02 |
| P5 | Pool of occurrences; proofs over templates | A4b | R-A4b-01, R-A4b-07 |
| P6 | Module layout; staging | A4b, main | R-A4b-08; staging: Part 9 |
| P7 | Named runs, scenario line, notes, `sees`, report | A5 | R-A5-01, R-A5-02, R-A5-04, R-A5-06, R-A5-09, R-A5-14 |
| P8 | Candidates to retire | main | D16 |

## Part 7. What changes against today's engine

From `g0-notes.md`:
1. A flow with legs where one leg asks nothing: today an error; now that leg moves nothing (S3; also `timeline/run.py:1289`).
2. Two outflows of one stock with no share: today a compile error; now `proportional()` (S2).
3. Two legged flows sharing an empty stock: today "upstream first", 0.5, 0.25, 0.25; max-min would give 1/3 each. Not run. R-A3-09 sends flows with legs to the solve library, so the test of S3 decides the number.
4. Events due at one moment: today in file order; now the order of R-A2-01 (S4).
5. `event start`: today an initiating event with its own rules; now an ordinary event named `start` with `when t >= 0 h` (R-A5-13; `a5/migration-table.md:79`). Its special rules at build go.
6. Outcome rules and `sight`: eligibility stays; the chances become `switch chance(...)` (R-A5-08; D1).
7. What an actor does not see: today refused in its choices; now `sees` only picks what a player is shown (R-A5-14). No ruling keeps the refusals.

From the findings:
8. `48 h/2` and `48 h / 2` no longer differ in silence: the first is refused (R-A1-01).
9. A bool is no number (R-A1-05). Python's keywords are no longer reserved (R-A1-08).
10. `|` between named states becomes `enum[A, B]` (40 lines); a flow with one end left out names `SOURCE` or `SINK` (24 lines) (A1).
11. A row is named by `id`, not position (`machines.2` goes) (R-A1-28). Rows are kept in id order (R-A4a-02).
12. An unbounded 2-argument `normal` is allowed; today it is refused (R-A1-18).
13. A join or a leave is a write: today a due prediction holds without a look at the value (`timeline/run.py:2447`), and the alarm of A4b's case fires at 6 h, not 10 h (R-A4b-04).
14. Proofs count event flows as writers: a store that an event can drain no longer "never falls" (R-A4b-07).
15. A stored run is keyed without labels: today a label edit gives a new run (read in code, not run) (R-A4a-08).
16. A run records histories of pieces, not a whole-state `Trajectory` (R-A4a-07). Today's limit of 150 nested operations goes (R-A4a-05).
17. An option that sets a number needs a record; today options are exempt (R-A5-05).
18. `versus` goes; pairs move to `brief.toml` (R-A5-06). `copy`, `* k`, `while`, `since(e.outcome)`, `assert within` go (R-A5-10).
19. `size` becomes `scale`; a store with no range gets `[0, none]` (R-A5-11).
20. Strict `>`/`<` on a moving value is a setup diagnostic (R-A4b-06). The catalogue uses only `<=`/`>=` (g0-notes).

## Part 8. For the plan

- Limits measured (A4a): one component is acceptable up to about 150 stores; 600 stores took 12.3 s and 864 MB; a ring at 600 stores gave no result in 13 min. Arrays and lines ran 60,000 stores and 65,000 flows in 1.4 s, 156 MB. Refused at scale: a moving rate in a set above 150 stores, and a record above 10,000,000 pieces (R-A4a-05).
- Record (R-A4a-07, -08): pieces for every value under the budget; at 30,000 rows that is 324,857 pieces, 6 MB, +0.1 to 0.3 s. S0 builds the record and the manifest, not readings.
- Pool (R-A4b-01): one row per occurrence for good, 341 bytes each, 34 MB per 100,000; spill finished rows in blocks if needed. A start costs about 80 µs, a finish about 18 µs (Python spike).
- Migration (A5): 96.1% of lines by machine (6,691 of 6,960); by hand: 172 flows with several pairs, 75 events with several outcomes, 11 `versus`, 11 `since(e.outcome)`. Nothing ran; M needs the new compiler.
- Go or no-go (A3): membership that changes: go. Inequality rows in the distance step: go for correctness. Fair sharing at 30,000 places: no-go for the exact method; go at 3,000. The distance step after a fair rank: no-go for cost, 38 s at 3,000 places with the QP of HiGHS. See D0.
- Order: the component limit of 150 must be measured again once A3's solve replaces the allocation (R-A4a-04), so S2 and S5 should not fix it before A3 ends.
- Content: a type checker should come early (S0 or S1): 16 A1 refusals depend on it. A writer-site proof checker belongs in S4 (R-A4b-07). Run A5's migration check at G0 and add a comparison of switch conditions (R-A5-15).
- Content: `a4a/measure.py` should run end to end, alone, with `OPENBLAS_NUM_THREADS=1`, before its numbers are cited as limits.

## Part 9. Changes to the plan (main session; confirm, or say what to change)

The staging of `PLAN.md` holds: contract first, then slices S0 to S6, consumers, catalogue, finish.
The findings change the content of some stages, not their order:

1. **B1, the contract.** The record of a run is histories of pieces with a budget, and a stored run
   has a manifest of what it serves (R-A4a-07, R-A4a-08). Rows live in pools in the order of their
   ids, with links as columns of row numbers (R-A4a-01, R-A4a-02).
2. **S0, the front end.** The type rules of `a1/types.md` are checked from the first slice on: 16
   rulings of A1 are refusals that only a checker can make. The expression parser is A1's.
3. **S0 to S2, the planner.** Three ways to run a connected set, cut by the refined rule (R-A4a-03,
   R-A4a-04). The limit of one component (about 150 stores) is measured again in S2, when the solve
   library has replaced the allocation inside a component.
4. **S4, occurrences.** A join or a leave is a write (R-A4b-04). Each endpoint keeps an exact sum
   (R-A4b-05). One pool row for each occurrence, for good (R-A4b-01). The proofs over writer sites
   get a checker here, because none ran in the prototype (R-A4b-07).
5. **The oracle.** A2's interpreter becomes `tests/reference/` in B1, as planned. It has no units,
   no `switch`, no `sees`, no chance cases, and its pause replays. Each is added in the slice that
   brings the construct.
6. **M, the catalogue.** A5's translator does the mechanical lines (96%) and its check guards each
   package. The work by hand is the 172 flows with several pairs and the 75 events with several
   outcomes. `iv_fluid_shortage` and 15 variants were not translated by hand in the prototype.
7. **Before S2.** `a4a/measure.py` runs end to end, alone, so that its limits can be cited.
8. **Still open in the keel.** The one last run of the old test suite.
9. **Agents** run on the `opus` model from now on, to save usage.

All six prototypes have reported, and every ruling is in this document.
