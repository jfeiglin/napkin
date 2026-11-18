# LAYOUT: the map of `timeline/run.py` and `timeline/plan.py`, and the split by moves

Prototype A4b, first deliverable. All line numbers are those of the base commit
(`/home/user/napkin-base`, 8488047). After step B0-5 the lines shift; the names do not. The split
is keyed on names.

## 1. Summary

- `run.py` has 3,490 lines: 6 helper functions, 10 small classes, and the class `Run` (lines 619
  to 3490, 104 methods). 14 methods are whole-run derivative code and go in B0-5. 90 stay for the
  split.
- **Cut `Run` into mixin classes, one for each module.** `Run` in `run.py` inherits from all of
  them. A method is cut and pasted, and no body changes, because `self.x(...)` still finds `x`.
  The other way (functions that take the run) is no pure move: it rewrites every `self.` and every
  call. `value` alone has 32 callers.
- **Ten new modules**, and `run.py` keeps about 490 lines: `state`, `lists`, `sharing`, `segments`,
  `readers`, `checks`, `rules`, `steps`, `choices`, `trace`. The plan's list had four; the code
  asks for six more, each a part that one later slice deletes whole (section 7).
- **`split_run.py` does the moves** (this folder). It was run on a copy of the base package, in
  one pass and module by module. Each time, all 143 functions kept their bytecode, `Run` kept its
  103 attributes, ruff was clean under the project's settings, and three models gave the same
  results as the base, bit for bit (section 9).
- `plan.py` is not split. Every method of it reads the old structure, and S0 rebuilds it over the
  program. Its table (section 5) says which logic survives, and where.

## 2. How to read the tables

| Fate | Meaning |
| --- | --- |
| **kept** | The code stays. A slice in brackets changes it: `kept (S2)`. |
| **replaced Sx** | The slice Sx lands a new module, and this code is deleted then. |
| **deleted B0-5** | Whole-run derivative code. It goes before the split. |
| **retire? G0** | A candidate that gate G0 decides (`PLAN.md`, "candidates to retire"). |

"To" is the module of the split that takes the part. "D" in the fate column means that B0-5 also
removes lines inside a kept part; section 6 lists them.

## 3. `run.py`, top level (lines 1 to 616)

| Lines | Name | What it does | Fate | To |
| --- | --- | --- | --- | --- |
| 1–37 | module text | The two tiers, lines, blocks, the timeline, the tangents | kept; 31–36 deleted B0-5 | `run` |
| 39–71 | imports | | kept; 67 (`smooth`) and 69 (`places`) deleted B0-5 | each module |
| 73–81 | constants | `ROOT_TOLERANCE`, `CHANCE_TOLERANCE`, `TRIGGER, FIRE`, the kinds of a time on the timeline (`RULE, BOUND, ROOT, LIMIT, FLOOR, END`), `ONE`, `NEGATIVE`, `POSITIVE`, `SEEN` | kept; `TRIGGER, FIRE, RULE` and `CHANCE_TOLERANCE` go with S4 | `state` |
| 84–92 | `_basis_ref` | The identity of a basis in a trace entry | replaced S0 (the record) | `trace` |
| 95–109 | `shares` | The chance with which a sample takes each outcome | replaced S4 (`choices.py`, the chance producer) | `steps` |
| 112–123 | `_one`, `_spread` | A result of `arrays.values` as one value, or as one value for each instance | kept | `state` |
| 126–135 | `_span` | The time that `y' = a y + c` takes to reach a bound | kept | `segments` |
| 138–139 | `_pairwise` | A pairwise sum (`trees.Pairwise`) | kept | `state` |
| 142–149 | `Trial` | The state of a numeric block that a solver tries | kept, D (the field `tangents`) | `state` |
| 152–176 | `Env` | What the parts of one space read at one time, with a memo | kept (S1: the members of a pool; S4: a frame) | `state` |
| 179–198 | `Seen` | An `Env` of one instance as a mapping | kept | `state` |
| 201–228 | `View` | What the resolver of a decision reads | replaced S4 | `choices` |
| 231–232 | `Unknown` | An output with no estimate was read | kept (S1: it becomes `none`) | `state` |
| 235–236 | `Pause` | A decision waits for a pick | replaced S4 (the new `choices.py` has its own) | `choices` |
| 239–250 | `Past` | An `Env` at a time of the past, from the record | kept (S0: the record; S4: history) | `state` |
| 253–264 | `RuleState` | For each rule and row: `armed`, `triggered`, `pending`, `version`, `ready`, `own`, `reached`, `window` | replaced S4 (`triggers.py` and `occurrences.py`), D (`cause`, `pending_dt`) | `rules` |
| 267–516 | `Solution` | A numeric block from its last restart: `start`, `tolerances`, `advance` (a step longer than the cap is read inside), `settle`, `at`, `first_root` | kept, D (305, 433–434) | `segments` |
| 519–616 | `Result` | What a run gives: trace, outputs, counts, the decision; `entries`, `final`, `trajectory` | replaced S0 (the record). `trajectory` (563–616) dies with the flat form in S0. D (`tangents`, `notes`, `margins`) | `trace` |

## 4. The class `Run` (lines 619 to 3490)

### 4.1 `Run.__init__` (620–807) stays whole in `run.py`

A constructor cannot be cut by a pure move: its parts share locals. This table says which lines
each later step deletes.

| Lines | What it sets | Fate |
| --- | --- | --- |
| 641–645 | `plan`, `reading` | kept; `reading` retire? G0 |
| 646–647 | `resolved` | replaced S0 (the run configuration) |
| 648–657 | `luck`, `streams`, `outcomes`, `firings` | replaced S4 (draws keyed by site and occurrence) |
| 658–663 | `record`, `undo`, `line_log`, `block_log`, `restart_numeric`, `flag_changes` | kept (S0: the record of a run) |
| 664–673 | `components`, `moved`, `flowing`, `now`, `past_kept`, `ended` | kept |
| 674–686 | play: `control`, `picks`, `decision_resolver`, `decision_events`, `settled`, `picked`, `picking`, `decision`, `controllers`, `continuations` | replaced S4 (`choices.py`) |
| 687–690 | `block_checks`, `block_programs`, `block_made`, `wrote`, `log`, `written_entries` | kept; `log` and `written_entries` replaced S0 |
| 691–699 | `keep`, `snapshots`, `after_steps`, `pieces` | replaced S0 (the record) |
| 700–711 | refusals of a run with derivatives | deleted B0-5 |
| 712–715 | `cfg`, `adapter`, `registry`, `horizon`, `tolerance` | kept |
| 716–717 | `directions`, `K` | deleted B0-5 |
| 718–737 | `v` (the columns), `inputs`, `given` | kept (S0: the run configuration) |
| 738–747 | `max_step`, `timescales`, `solver_step` | kept |
| 748–762 | `dv`, `dnow`, `notes`, `subjects`, `noting`, `jump_signs`, `margins`, `stepped` | deleted B0-5 |
| 763–768 | `monotone_crossings` | kept (S4: the proofs come from the program) |
| 769, 773 | `y0`, `t0`, `rate`, `lversion`, `atol`, `slack` | kept |
| 770–772 | `D`, `dt0`, `drate` | deleted B0-5 |
| 774–787 | `rules` (one `RuleState` each), `order` | replaced S4 |
| 788–794 | `times`, `entries` (the timeline), `ready`, `dirty`, `moment`, `steps`, `trace`, `terms`, `whole`, `single`, `starting` | kept; `ready`, `dirty` replaced S4; `terms` replaced S1 |
| 795–807 | `counts` | kept |

### 4.2 The methods

| Lines | Method | What it does | Fate | To |
| --- | --- | --- | --- | --- |
| 811–819 | `index` | The places, in the space of a name, of the instances J of a reader | kept (S1: link columns by reference path, two links into one table) | `state` |
| 821–846 | `read` | The value of a name now: a value, a line (`y0 + rate * (t - t0)`), a trial state, or a numeric block | kept (S0: the names of the program) | `state` |
| 848–886 | `read_past` | The value of a name at an earlier time, from the record | kept (S0) | `state` |
| 888–920 | `past_states` | The state of every instance of a block at an earlier time, closed forms in one call | kept | `state` |
| 922–928 | `segment` | The segment of a block that holds a time | kept | `state` |
| 930–955 | `extras` | Gives a firing its drawn values and its values of the past | replaced S4 (draws by site and occurrence; `delayed`) | `steps` |
| 957–970 | `numeric` | The values of a numeric quantity at some places | kept, D (the argument `part`) | `state` |
| 972–981 | `column` | A name for each instance at a time; a formula is its expression | kept | `state` |
| 983–984 | `value` | Evaluates a node in an environment (`arrays.values`). 32 callers | kept | `state` |
| 988–1129 | `tangent`, `note`, `about`, `done`, `ties`, `name_tangent`, `slope` | The tangents and the notes of a derivative | deleted B0-5 | — |
| 1133–1145 | `aggregate` | The value of a list from what it keeps of each member | replaced S1 (`collections.py`) | `lists` |
| 1147–1170 | `combined`, `reduced` (static) | The six reductions: a sum tree, counts, an extreme | replaced S1 | `lists` |
| 1172–1191 | `update_term` | Brings one member of a list up to date for some instances | replaced S1 (S4 adds members that join and leave) | `lists` |
| 1195–1216 | `rate_of` | The rate of a quantity: its signed parts, with what each flow delivers | replaced S2 (`network.py`) | `sharing` |
| 1218–1241 | `see_flows`, `flows_at_end`, `negative_flow` | Marks the flows that moved material (`flowing`); the refusal of a negative flow | replaced S2; the evidence trail reads the record in C | `sharing` |
| 1243–1276 | `delivered`, `alone` | What a flow delivers: its request, its share of a group, or what comes into a resting source | replaced S2 | `sharing` |
| 1278–1298 | `fraction` | The one fraction of flows that move together | replaced S3 (flows with legs; the rule at 1289–1290 is reversed) | `sharing` |
| 1300–1316 | `supply` | What comes into a quantity that rests on its bound | replaced S2 | `sharing` |
| 1318–1355 | `rationed` | A group with a limit: proportional, or in priority order | replaced S2 (the new sharing rules; fast paths from A3), D (1344–1345) | `sharing` |
| 1357–1439 | `rate_tangent`, `block_ties`, `jumps` | Tangents of a rate; ties and jumps of a block | deleted B0-5 | — |
| 1441–1471 | `field` | The rates of a numeric block at a state; counts the evaluations | kept, D (the tangent rows) | `segments` |
| 1473–1540 | `matrices` | The matrix of a linear block, and whether no flow can ask less than zero | kept (S2: groups and floors become facts of the network) | `segments` |
| 1542–1547 | `flows_from` | Marks the flows that deliver at the start of a closed form | kept (S2) | `segments` |
| 1549–1581 | `asked_alone` | Whether a flow of a linear block gets what it asks | kept (S2) | `segments` |
| 1583–1626 | `block_program`, `block_values` | One generated program for a linear block, and its values | kept | `segments` |
| 1628–1654 | `group_terms` | What the flows of a group ask together, as `alpha + beta y` | kept (S2) | `segments` |
| 1656–1734 | `decide` | Closed form or solver for a segment; puts the time of a bound or a limit on the timeline | kept, D (1680) | `segments` |
| 1736–1744 | `within_bounds` | A state of a block is within its bounds, or the space leaves the fast tier | kept | `segments` |
| 1748–1858 | `start` | Start values in the order of their reads, sizes and tolerances, the first lines and blocks, the first reading of the rules | kept (S0: the program; S1: initializers across members), D (the tangents of the starts) | `run` |
| 1862–1929 | `restart_line`, `_restart_line` | A line starts again; the time at which it reaches a bound goes on the timeline | kept, D (the wrapper 1862–1868 exists for the notes) | `segments` |
| 1931–1974 | `rest` | Whether a quantity rests on its lower bound; `flag_changes` | kept (S2: asks the network), D (1959–1960) | `segments` |
| 1976–1980 | `cut` | The solution of one instance starts again from where it is. `component.py` calls it | kept | `segments` |
| 1982–1994 | `check_readers` | The checks that read a component hold at a time. `component.py` calls it | kept (S4: `assert` on state) | `checks` |
| 1996–2001 | `segment_end` | A segment of a component ends: a time on the timeline. `component.py` calls it | kept | `segments` |
| 2003–2028 | `ends` | At the end of a segment: arms the rules whose condition was false inside, reads checks, marks rules | replaced S4 (`moment.py` handles `END`) | `rules` |
| 2030–2032 | `crossing_due` | A watched crossing of a component reached its value. `component.py` calls it | replaced S4 (`triggers.py`) | `rules` |
| 2034–2040 | `static` | One value for one instance, for a component | kept | `state` |
| 2042–2112 | `sizes` | The size of each quantity, which sets its tolerance. It repeats `System.sizes_of` | kept (S2: the connected stores come from the network) | `state` |
| 2114–2117 | `rule_free_name` | The flat name of a part of one instance | replaced S1 (the ids of members) | `state` |
| 2119–2157 | `restart_block` | The solutions of a block start again; keeps the old segment in the record | kept, D (the jump of the tangents) | `segments` |
| 2161–2187 | `targets`, `merge` (static) | The instances that read some instances of a name; the union of two sets of instances | kept (S1: the reverse index) | `readers` |
| 2189–2220 | `closure` | Every part that reads, by any path, what a step wrote | kept (S4: members that join and leave) | `readers` |
| 2222–2310 | `apply` | Makes the writes of a step and brings the readers up to date, in a fixed order | kept (S4), D (the tangents of a write). 2308–2310 retire? G0 | `readers` |
| 2312–2316 | `holds_at_start` | A check of the inputs, for each instance | kept (S1: `assert` on inputs) | `checks` |
| 2318–2334 | `check` | A check of the state holds, or the run stops | kept (S4: where an `assert` on state is checked) | `checks` |
| 2336–2368 | `partition` | The parts add up to the total, or the run stops | replaced S4 (an `assert` with an interval) or retired at G0 | `checks` |
| 2370–2374 | `check_all` | Every check and partition | kept (S4) | `checks` |
| 2376–2381 | `mark` | A rule is read again for some instances (`dirty`) | replaced S4 | `rules` |
| 2385–2404 | `holds` | Whether the condition of a rule holds; a crossing holds when reached or past its value | replaced S4. 2399–2401 retire? G0 | `rules` |
| 2406–2429 | `window`, `spent` | The window of `each W` | replaced S4 (deleted with the feature) | `rules` |
| 2431–2437 | `later` | Puts a time of a rule on the timeline, with the version of the rule | replaced S4 | `rules` |
| 2439–2495 | `read_rule` | Reads a rule for some instances: cancel on `while`, due firings, triggers, re-arming | replaced S4, D (2485–2495) | `rules` |
| 2497–2555 | `watch` | Predicts when a condition can hold: a clock, the crossing of a line, the root of a block | replaced S4 (the same crossing classes, in `triggers.py`) | `rules` |
| 2557–2608 | `own_tangent` | The tangent of the time of a rule | deleted B0-5 | — |
| 2612–2616 | `rule_name` | The flat name of a rule of one instance. `reports.py` calls it | replaced S1 (ids) | `state` |
| 2618–2630 | `count_step` | The budget of the steps of one moment | replaced S4 (the budget of a round) | `steps` |
| 2632–2642 | `place` | The place of the instance that a step reads or writes through a link | kept (S1) | `state` |
| 2644–2650 | `emitted` | Counts an event and keeps its time | replaced S4 (an occurrence is the count) | `steps` |
| 2652–2693 | `trigger`, `_trigger` | A rule triggers: memory, window, delay, pending firing | replaced S4, D (the wrapper 2652–2659; 2686–2687) | `steps` |
| 2695–2757 | `chosen` | The outcome that a firing takes: chances, availability, pick, given, central or drawn | replaced S4 (`choices.py`) | `steps` |
| 2759–2779 | `taken` | The outcome of a firing of a run with given outcomes | replaced S4, D (the slopes) | `steps` |
| 2781–2818 | `chance_slopes`, `outcome_noted` | Derivatives of chances | deleted B0-5 | — |
| 2820–2997 | `fire`, `_fire` | One step: sets, moves with their bound and roundoff rules, events, the events that the step names | replaced S4. The bound and roundoff rules of a set and of a move (2876–2971) are carried into `moment.py`. D (the wrapper 2820–2827; the tangents of each value) | `steps` |
| 3001–3006 | `can_trigger` | A rule can trigger unless it is `once` and done, or it waits | replaced S4 | `rules` |
| 3008–3010 | `flat_entity` | The flat name of the thing of a rule | replaced S1 (ids) | `state` |
| 3012–3034 | `controller`, `controlled` | Who picks the outcomes of a rule | replaced S4 | `choices` |
| 3036–3073 | `pick` | The outcome of a played decision; the resolver; the pause | replaced S4 | `choices` |
| 3075–3132 | `happened`, `ask` | What a decision that waits shows its actor | replaced S4 | `choices` |
| 3134–3184 | `entry`, `entry_at` | One step of the trace, written out when a reader asks | replaced S0 (the record), then S4 (the entries of occurrences) | `trace` |
| 3188–3208 | `state_now`, `store_now`, `snapshot` | The state and the store for a `Trajectory`. `component.py` calls `store_now` | replaced S0 | `trace` |
| 3210–3296 | `settle` | One moment: takes the due times, then reads and steps the rules until none is due | replaced S4 (`moment.py`). 3247–3249 retire? G0. D (3217, 3286–3288) | `run` |
| 3298–3318 | `step_noted` | The order of two steps and the derivatives | deleted B0-5 | — |
| 3320–3362 | `next_settled` | The next step of a moment that settles the independent work first | replaced S4 | `choices` |
| 3364–3369 | `run` | The run; a pause gives a paused result | kept (S4) | `run` |
| 3371–3419 | `input_failures`, `admit` | The failing checks of the inputs for every row; the proofs made again for given values | kept (S1); the proofs move to `napkin/program/` | `checks` |
| 3421–3439 | `played` | The loop: start, then moment after moment to the horizon; components go first | replaced S4 (`moment.py`) | `run` |
| 3441–3447 | `stale` | Whether a time on the timeline is of an old version | kept (S4: the versions of triggers and of frames take the place of `rules[i].version`) | `run` |
| 3449–3490 | `result` | Checks at the horizon, the outputs, the `Result` | replaced S0, D (the tangents) | `trace` |

Counts at the base, by module: `state` 14 methods, `lists` 4, `sharing` 9, `segments` 15,
`readers` 4, `checks` 7, `rules` 10, `steps` 9, `choices` 6, `trace` 6, `run` 6, and 14 deleted.

## 5. `plan.py` (1,411 lines)

`plan.py` reads the hybrid core and the old structure (`s.quantities`, `s.rules`, `s.flows`). S0
deletes both and gives the planner a program. So the fate of almost every row is "rebuilt S0":
the row then says which logic is carried over, and to which module.

| Lines | Name | What it does | Fate |
| --- | --- | --- | --- |
| 44–46 | `SCALARS`, `LISTS`, `SAME, ALL, LINK` | The space of one instance; the reductions; how a part reads a name | kept (S1: `LINK` takes a reference path) |
| 49–52 | `_no_text` | A text in the place of a node is an error | kept |
| 55–64 | `Outside` | "The engine does not run this part": a message, and `space` or `tier` for the retry in another tier | kept as the refusal by name. `space` and `tier` replaced S0 (`islands.py` chooses the way for each connected set) |
| 67–78 | `Space` | One set of instances, with `links` and `linked_from` | replaced S1 (`spaces.py`: pools, link columns, the reverse index) |
| 81–96 | `Term`, `Aggregate` | A member of a list; a reduction, `moving` or not | replaced S1 (`collections.py`) |
| 99–110 | `Outcome` | Sets, moves, fires, emits, chance | replaced S4 (the stages of an event in the program) |
| 113–136 | `Check`, `Partition` | An `assert` on the state; a sum that holds | kept as records of the program (S1, S4); `Partition` retire? G0 |
| 139–151 | `Extra` | A drawn value or a value of the past, for a firing | replaced S4 |
| 154–182 | `Rule` | One event: its kind, gate, clocks, crossing, delay, outcomes | replaced S4 (events and triggers of the program) |
| 185–195 | `Fact` | What an actor sees at a decision | replaced S4 (`sees`) |
| 198–210 | `Quantity` | Name, space, form (`value`, `line`, `numeric`), start, bounds, size, `monotone` | kept (S0: a store of the program) |
| 213–228 | `Block` | Quantities whose rates read one another: `whole`, `linear`, `net` | kept |
| 231–242 | `Group` | Flows that share one limit, with a policy | replaced S2 (the scopes of an endpoint) |
| 245–257 | `Floor` | A line that can rest on its lower bound | kept (S2) |
| 260–280 | `_number`, `_children_changed` | A bound as a number; a node with its children changed | kept |
| 286–321 | `Plan.of` | The plan of a run of a hybrid core; the retry with the things outside the tables in the fast tier | replaced S0 (`Plan.of(program)`) |
| 323–337 | `Plan.flat` | The plan of a flat structure | deleted S0 |
| 339–364 | `Plan.made`, `wider` | Makes the plan again with one more space in the general tier | replaced S0 (`islands.py`). `plan.optional` (354) deleted B0-5 |
| 366–373 | `Plan.fast` | The plan with the scalars in the fast tier, for a run with derivatives | deleted B0-5 |
| 375–470 | `__init__` | Calls the passes in order; builds checks and partitions | rebuilt S0 |
| 474–503 | `_spaces` | Spaces and links. Refuses a link into two classes (490) and two links into one class (497) | replaced S1 (`spaces.py`) |
| 505–541 | `space_of`, `check_space`, `check_name`, `how` | The space of a name from the prefix of its flat name; SAME, ALL or LINK | replaced S1 (`napkin/program/refs.py` gives the template, the field and the path) |
| 545–576 | `_names` | The start columns: inputs, modes with their entry times, the count and the time of each event | rebuilt S0; the event counters replaced S4 |
| 580–619 | `node`, `plain` | An expression as one node for the fast tier, or as the continuous engine reads it | rebuilt S0 (nodes with references come from the program) |
| 621–658 | `_lists`, `_aggregate` | A reduction over a family becomes a named aggregate. Refuses a list in a part of a family (637) | replaced S1 (the lowering names the reductions; `collections.py` runs them) |
| 660–683 | `_inline`, `_formula` | Puts each formula in the place of its name; refuses a formula that reads itself | kept logic (S0) |
| 687–757 | `_quantities`, `_bound` | The parts of each rate, the flows, bounds, starts. Refuses a flow that joins two spaces (707) | rebuilt S0; the refusal goes in S2 |
| 759–782 | `_groups` | The allocation groups. Refuses a group of two spaces (782) | replaced S2 (`network.py`) |
| 784–811 | `_couplings` | Flows that move by one fraction; which spaces need the general tier | replaced S3 (flows with legs), and `islands.py` |
| 813–853 | `rate_nodes` | Every node that decides the rate of a quantity: parts, group, coupling, floor | kept logic (S2: read from the network) |
| 855–903 | `_floors` | The lines that can rest on a bound; refuses a ring of them | kept logic (S2) |
| 905–1060 | `_nets` | What the continuous engine reads of a space (`component.Network`). Refuses a flow that joins two spaces (925) and a rate that reads a value that moves outside (974) | replaced S2 (`network.py`); S0 keeps the part that builds one component |
| 1064–1187 | `_rules` | Rules, outcomes, extras, `sees`, the crossings of each quantity, `records` | replaced S4 (the classifier `analysis.classify` is reused by `triggers.py`) |
| 1191–1199 | `reads` | The names that a node reads, through its aggregates | kept logic |
| 1201–1324 | `_forms` | Value, line or numeric; the blocks by union-find; `whole`, `linear`, `net`; what a rule may read (1306–1324) | kept logic (S0); 1306–1324 replaced S4 |
| 1326–1339 | `_linear` | Whether a block is linear with constant factors (`core.derivatives`) | kept |
| 1343–1411 | `_readers` | For each name, the parts that read it, and how | kept logic (S0); S4 adds the readers of members that join and leave |

Proposal for the rebuilt planner. `plan.py` keeps `Plan`, `Quantity`, `Block`, `Floor`, the forms
(`_forms`, `_linear`, `reads`, `rate_nodes`) and the readers. `spaces.py` takes 67–78 and
474–541. `collections.py` takes 81–96 and 621–658. `network.py` takes 231–242, 759–811 and
905–1060. `islands.py` takes the choice of the way (339–364, and the `tier` and `space` of
`Outside`). `triggers.py` takes 154–182 and 1064–1187.

## 6. What B0-5 removes from these two files

Whole files: `derivatives.py`, `influence.py`, `smooth.py`. `places.py` is then left with no
reader: only the notes and `influence.py` read it (`run.py:69`, `expectations.py:324`). The brief
of B0-5 does not list it. Delete it there, with its entry in `CLOSURE`.

Whole methods of `Run` (14, 325 lines): `tangent`, `note`, `about`, `done`, `ties`,
`name_tangent`, `slope` (988–1129); `rate_tangent`, `block_ties`, `jumps` (1357–1439);
`own_tangent` (2557–2608); `chance_slopes`, `outcome_noted` (2781–2818); `step_noted` (3298–3318).

Lines inside parts that stay:

| Part | Lines | What goes |
| --- | --- | --- |
| module text, imports | 20, 31–36, 67, 69 | The text on tangents; `smooth`; `places` |
| `Trial` | 145, 148 | The field `tangents`. Its makers at 1445–1449, 1487 and 1634 lose one argument |
| `RuleState` | 254, 263–264 | `directions`, `cause`, `pending_dt` |
| `Solution` | 305, 433–434, 437 | The tiled tolerances; the call of `block_ties` |
| `Result` | 522–523, 528, 539–543 | `tangents`, `notes`, `margins` |
| `Run.__init__` | 627, 700–711, 716–717, 748–762, 770–772, 774 | See 4.1 |
| `numeric` | 957–970 | The argument `part` |
| `rationed`, `rest` | 1344–1345, 1959–1960 | Two refusals of a derivative |
| `field` | 1442–1459 | `K`, the tangent rows |
| `decide` | 1659, 1680 | `or self.directions` |
| `start` | 1749, 1772–1789, 1814–1816, 1821–1831, 1844 | The tangents of the starts |
| `restart_line`, `_restart_line` | 1862–1887, 1906–1909 | The wrapper for the notes; `tangents`, `totals` |
| `restart_block` | 2122, 2131–2138, 2149–2152 | The jump of the tangents |
| `apply` | 2224–2227, 2242–2246, 2256–2258, 2268–2269, 2277–2286 | The fourth field of a write, `before`, `jump` |
| `read_rule` | 2485–2495 | `cause`, the tie of a condition |
| `emitted`, `_trigger` | 2650, 2652–2659, 2686–2687 | `dnow`, the wrapper, `pending_dt` |
| `chosen`, `taken` | 2744–2745, 2763, 2772–2778 | `outcome_noted`, the slopes of a firing |
| `fire`, `_fire` | 2820–2827, 2830, 2841–2850, 2872–2892, 2896, 2906, 2932–2949, 2955, 2991 | The wrapper, the tangents of each value |
| `settle` | 3217, 3286–3288 | `dnow`, `step_noted` |
| `result` | 3453–3455, 3466–3473, 3479, 3487–3488 | The tangents of the outputs |
| `plan.py` | 354, 366–373 | `optional`, `Plan.fast` |
| `timeline/__init__.py` | 69–71, 83 | The call of `plan.fast()`; the test on `directions` |

`from ...core.derivatives import derivative` (`run.py:55`) stays. `matrices`, `block_program` and
`group_terms` use it for the closed form of a linear block, and `plan.py` uses it in `_linear`.

A write is a tuple of four, `(name, place, value, tangents)`, at every call of `apply`. B0-5
decides whether the fourth field goes or stays `None`. The split does not care.

## 7. The modules of the split

Lines are after the split of the base copy. They include the import block of each file. B0-5
makes `segments`, `steps`, `run` and `readers` shorter.

| Module | Mixin | Holds | Lines | Later |
| --- | --- | --- | --- | --- |
| `state.py` | `State` | The constants, `_one`, `_spread`, `_pairwise`, `Trial`, `Env`, `Seen`, `Unknown`, `Past`; reading a name now and in the past; `sizes`; the names of instances | 389 | kept |
| `lists.py` | `Lists` | `aggregate`, `combined`, `reduced`, `update_term` | 78 | deleted in S1, when `collections.py` lands |
| `sharing.py` | `Sharing` | `rate_of`, `delivered`, `alone`, `fraction`, `supply`, `rationed`, and the marks of flows that moved | 182 | deleted in S2, when `network.py` lands (`fraction` by S3 at the latest) |
| `segments.py` | `Segments` | `_span`, `Solution`; `field`, the closed form (`matrices` to `decide`), `within_bounds`; the restarts of lines and blocks, `rest`, `cut`, `segment_end` | 783 | kept |
| `readers.py` | `Readers` | `targets`, `merge`, `closure`, `apply` | 168 | kept |
| `checks.py` | `Checks` | `check`, `partition`, `check_all`, `check_readers`, `holds_at_start`, `input_failures`, `admit` | 146 | kept, smaller after S4 |
| `rules.py` | `Rules` | `RuleState`; `mark`, `holds`, `window`, `spent`, `later`, `read_rule`, `watch`, `ends`, `crossing_due`, `can_trigger` | 254 | deleted in S4, when `triggers.py` lands |
| `steps.py` | `Steps` | `shares`; `extras`, `count_step`, `emitted`, `trigger`, `_trigger`, `chosen`, `taken`, `fire`, `_fire` | 398 | deleted in S4, when `occurrences.py` and `moment.py` land |
| `choices.py` | `Choices` | `View`, `Pause`; `controller`, `controlled`, `pick`, `happened`, `ask`, `next_settled` | 218 | rewritten in S4 under the same name |
| `trace.py` | `Trace` | `_basis_ref`, `Result`; `entry`, `entry_at`, `state_now`, `store_now`, `snapshot`, `result` | 250 | deleted in S0, when `record.py` lands |
| `run.py` | `Run` | `__init__`, `start`, `settle`, `run`, `played`, `stale` | 495 | `settle` and `played` go in S4 (`moment.py`) |

Why six modules more than the plan's four:

- `rules.py` and `steps.py` hold what the plan says S4 replaces (`RuleState`, `read_rule`,
  `_trigger`, `_fire`). If they stayed in `run.py`, S4 could not delete a whole module.
- `sharing.py` is the fast tier's own arithmetic of sharing. S2 changes the rules of sharing, so
  none of it survives. `segments.py` is kept, so the two must not share a file.
- `lists.py` is small, but S1 replaces all of it.
- `trace.py` holds what S0 replaces with the record: the entries, the snapshots, `Result`.
- `checks.py` is kept code that `readers.py` only calls.

The loop (`settle`, `played`, `stale`, `run`) stays in `run.py`. It is 120 lines, and `settle`
handles the kept kinds of time (`BOUND`, `FLOOR`, `LIMIT`, `END`) in the same body as the rules.
S4 replaces the body.

The new modules have names that no later module of the plan takes, except `choices.py`, which the
plan itself reuses. So a slice can write `triggers.py`, `occurrences.py`, `moment.py`,
`collections.py`, `network.py` and `record.py` beside the old code and delete the old module in
the commit that switches.

### 7.1 How the class is cut

```python
# run.py after the split
from .state import State, Env, ...        # and the other mixins
class Run(State, Lists, Sharing, Segments, Readers, Checks, Rules, Steps, Choices, Trace):
    def __init__(...): ...
```

- A mixin has no `__init__` and no state of its own. Every attribute is still set in
  `Run.__init__` and in `start`.
- No two mixins define the same name, so the order of the bases changes nothing. `Run` uses no
  `super()`, no name with two leading underscores and no `Run.` by name (checked).
- The three static methods (`combined`, `reduced`, `merge`) are called through `self` and move as
  they are.
- A mixin module imports `state.py` and nothing else of the split. Calls between mixins go
  through `self`, so the modules cannot form an import cycle. `start` makes `Solution` and
  `Component` objects, so it stays in `run.py`, which may import every module.
- `run.py` imports back the five names that others import from it: `Past`, `Unknown`, `_one`
  (`reports.py:41`), `shares` (`tests/engine/test_timeline_outcomes.py:18`) and `Result`
  (`timeline/__init__.py:42`). The form is `from .state import Past as Past`: ruff keeps such an
  import, and no importer changes.
- `component.py` needs no change. It calls `run.cut`, `run.segment_end`, `run.crossing_due`,
  `run.check_readers`, `run.static`, `run.store_now` and `run.rule_free_name`, and reads
  `run.rules[rule].version`. All are still attributes of the run.

The mixins are a form for the time of the rewrite. They make a deletion cheap; they do not make
the class small. A new module of S0 and after should own its state in an object of its own (a
pool, a network, a set of triggers) and take what it needs as arguments.

### 7.2 The names that cross

Module-level names. Every one that two modules read lives in `state.py`:

| From `state.py` | Read by |
| --- | --- |
| `Env` | every module but `readers` and `choices` |
| `_spread` | `lists`, `sharing`, `segments`, `checks`, `rules`, `run` |
| `_one` | `segments`, `steps`, `choices`, `trace`, `reports.py` |
| `_pairwise` | `checks` |
| `Trial`, `ROOT_TOLERANCE` | `segments` |
| `Seen` | `segments`, `choices` (`View` extends it) |
| `NEGATIVE`, `POSITIVE` | `sharing`, `segments` |
| `BOUND`, `FLOOR`, `LIMIT`, `END` | `segments`, `run` |
| `RULE`, `ROOT`, `TRIGGER`, `FIRE`, `ONE` | `rules`; `ROOT` and `FIRE` also `run`; `TRIGGER` and `FIRE` also `choices` |
| `CHANCE_TOLERANCE`, `Past` | `steps` (`Past` also `reports.py`) |
| `SEEN` | `choices` |
| `Unknown` | `trace`, `reports.py` |

`Solution` and `RuleState` are read by `run.py` only (`start`, `__init__`); `Pause` by `choices`
and `run.py`.

Calls through `self`. This table is the list of seams: when a slice deletes the module in the
first column, it must give each caller in the second column something else to call.

| Module | Called from other modules |
| --- | --- |
| `state` | `value` from all; `index` from `rules`; `column` from `checks`, `trace`; `place`, `rule_name` from `steps`, `trace`; `rule_free_name`, `flat_entity` from `choices`, `trace`, `run`; `sizes` from `run` |
| `lists` | `aggregate`, `combined`, `reduced` from `state` (`read`, `read_past`); `update_term` from `readers` (`apply`); `aggregate` from `run` (`start`) |
| `sharing` | `rate_of`, `delivered`, `supply`, `rationed`, `fraction` from `segments` (`field`, `matrices`, `_restart_line`, `rest`); `negative_flow` from `Solution.settle`; `flows_at_end` from `reports.py` |
| `segments` | `decide` from `state` (`past_states`) and `run` (`start`); `field`, `restart_block`, `restart_line` from `readers` (`apply`); `matrices`, `group_terms`, `flows_from`, `restart_line` from `run` (`start`, `settle`) |
| `readers` | `closure` from `checks` (`check_readers`) and `rules` (`ends`); `apply` from `steps` and `run` |
| `checks` | `check`, `partition` from `readers` (`apply`) and `rules` (`ends`); `check_all` from `trace` (`result`) and `run`; `admit` from `run` |
| `rules` | `mark` from `readers` (`apply`), `steps`, `run`; `can_trigger` from `steps`, `choices`; `window` from `steps`; `read_rule`, `ends` from `run` (`settle`) |
| `steps` | `trigger`, `fire` from `run` (`settle`) |
| `choices` | `controller`, `controlled`, `pick` from `steps`; `next_settled` from `run` (`settle`) |
| `trace` | `entry`, `snapshot` from `steps`; `entry_at` from `choices`; `result`, `snapshot` from `run` |

Three attributes are set outside `__init__` and `start`, and each crosses a seam: `flag_changes`
(set in `rest`, drained in `apply` and `settle`), `wrote` (bumped in `apply` and `rest`, read by
`block_values`), and `entries` with `times` (the timeline: pushed by `later`, `decide`,
`_restart_line`, `segment_end`; popped by `settle`).

## 8. The order of the moves, and the tests that guard each

B0-5 comes first, as the plan says. (The script also runs before B0-5: the 14 derivative methods
then go to a module `tangents.py`, which B0-5 would delete. Not recommended: B0-5 still has to
edit lines in every other module.)

`state` is the first move: the others import its helpers. After it, any order passes, because
no mixin module imports another. The order below is the order of the file, so each diff reads
from top to bottom.

The plan's three files run after every move: `tests/engine/test_timeline.py` (61 tests in both
tiers, the only file that reaches the fast tier in full), `test_moment.py`,
`test_closed_form_short.py`. The table adds the files that reach the moved code most directly.
All are in `tests/engine/`.

| # | Move | Guards beside the three |
| --- | --- | --- |
| 1 | `state` | `test_timeline_reports.py` (`Past`, `read_past`, the record), `test_firing_values.py` (`delayed`), `test_sizes.py` |
| 2 | `lists` | `test_timeline_reports.py`, `test_timeline_row_facts.py`, `test_timeline_trees.py` |
| 3 | `sharing` | `test_timeline_long_steps.py`, `test_timeline_bounds.py` (the groups, floors and fractions of the fast tier are in `test_timeline.py`, lines 1340–1750) |
| 4 | `segments` | `test_timeline_long_steps.py` (`Solution.advance`, `settle`, `first_root`), `test_timeline_bounds.py`, `test_monotone_crossing.py` |
| 5 | `readers` | `test_rearm.py`, `test_timeline_reports.py`, `test_windows.py` |
| 6 | `checks` | `test_reporting.py` (`check_failed`), `test_timeline_reports.py`, `test_continuous_domains.py` |
| 7 | `rules` | `test_windows.py`, `test_rearm.py`, `test_monotone_crossing.py`, `test_timeline_unclassified.py` |
| 8 | `steps` | `test_chance.py`, `test_firing_values.py`, `test_timeline_outcomes.py` (`shares`, `taken`), `test_availability.py` |
| 9 | `choices` | `test_timeline_play.py`, `test_pause.py`, `test_settled_decisions.py`, `test_decision_resolver.py` |
| 10 | `trace` | `test_paused_results.py`, `test_reporting.py`, `test_run_evidence.py` |

I did not run these files: the brief forbids the repository's tests. The checks that I did run
are in section 9.

After the last move:

- `tests/test_api.py:34`, `CLOSURE`: add the ten files `engine/timeline/{checks,choices,lists,
  readers,rules,segments,sharing,state,steps,trace}.py`. B0-5 removes `smooth.py` from the same
  list, and `places.py` once nothing imports it. `store.closure()` finds the new files by itself
  (checked).
- `tools/bench/measure.py:85` groups `napkin/engine/timeline/` as one folder: no change.
- Four doc lines name `run.py` for a symbol that moves (`docs/engine.md:368`, `:478`;
  `docs/compiler.md:544`; `docs/extending.md:161`). The docs are rewritten in F; no test reads
  these lines.

## 9. `split_run.py`, and what was checked

```bash
PY=/home/user/napkin/.venv/bin/python
$PY scratch/rewrite/a4b/split_run.py . --only state      # one move; then the guard tests
$PY scratch/rewrite/a4b/split_run.py . --check ../napkin-base   # before B0-5 only, see below
$PY scratch/rewrite/a4b/split_run.py .                    # or: every remaining move in one pass
```

- A move cuts each part as text, with the comments above it, and pastes it. It then runs
  `ruff check --select F401,I001 --fix` and `ruff format` on the files that it wrote, with the
  `pyproject.toml` of the root, and stops if ruff finds an undefined name (F821). An undefined
  name is the one way a pure move can break a method without an import error: Python finds it
  only when the method runs.
- It stops, and writes nothing, when `run.py` has a method or a top-level name that `LAYOUT` in
  the script does not name. So a method that B0-5 adds or renames is reported, not misplaced. A
  method that is gone is skipped.
- `--check BASE` imports the split package and an unsplit one, each in a fresh process. It
  compares the bytecode, the constants and the names of every function, and the attributes of
  `Run`. `BASE` must hold the same code before the split: `../napkin-base` before B0-5, or a
  copy of the checkout made just before the first move.

Measured on copies of the base package (`/tmp/claude-0/.../scratchpad/a4b/{one,step,b5}`):

| Check | Result |
| --- | --- |
| One pass, base copy | 143 functions with the same code; `Run` has the same 103 attributes |
| Module by module, `--check` after each of 11 moves | The same, after every move |
| One pass against module by module | The same files, but for the layout of one import statement |
| `ruff check` and `ruff format --check` with the project's settings | Clean, 21 files |
| Three models (`examples/reservoir`, `examples/piano_tuners`, `scenarios/iv_fluid_shortage`), flat form and hybrid core in both tiers, 10 runs | The same digest of traces, outputs and counts as the base (`f765c4db…`) |
| A copy with the 14 derivative methods removed | The split runs, makes no `tangents.py`, 129 functions with the same code |

Not checked: the repository's tests on the split package.

## 10. The target layout, and what each later module replaces

| Module | Slice | Replaces | Holds |
| --- | --- | --- | --- |
| `record.py` | S0 | `trace.py`; `Result.trajectory`; `_OfResult` of `reports.py` | The history of each recorded value and the trace (A4a) |
| `islands.py` | S0 | `Plan.made`, `Plan.wider`, the retry loop of `timeline.run` (`__init__.py:76–86`) | The connected sets and the way each runs (A4a) |
| `spaces.py` | S1 | `Plan._spaces`, `space_of`, `how`; the `Space` record; changes `State.index` and `place` | Pools of members, link columns, the reverse index |
| `collections.py` | S1 | `lists.py`; `Plan._lists`, `_aggregate` | Reductions, `where`, `by`, `at`, the key index, key times. In S4 its members join and leave |
| `network.py` | S2 | `sharing.py`; `Plan._groups`, `_couplings`, `_nets`; `Group` | One sparse network, the totals of each endpoint. In S4 its edges join and leave |
| `occurrences.py` | S4 | `steps.py`; `RuleState.pending`; the event counters of `Plan._names` | The pool of frames |
| `triggers.py` | S4 | `rules.py`; `Plan._rules` | Eligibility, reset state, the prediction of a crossing |
| `moment.py` | S4 | `Run.settle`, `Run.played`, `Rules.ends`; the move rules of `_fire` | Rounds |
| `choices.py` | S4 | itself | Chance and choice producers, the pause |
| `state.py`, `segments.py`, `readers.py`, `checks.py`, `component.py`, `trees.py`, `plan.py` | — | — | Kept. `readers.py` gets the readers of members that come and go |

The layout of the pool of frames, the edges that join and leave `network.py`, and the reader
graph for them are the second deliverable (`FINDINGS.md` in this folder).

Other files of the package, for completeness:

| File | Fate |
| --- | --- |
| `__init__.py` | `run` kept (lines 69–71 and 83 go in B0-5; the retry 76–86 is replaced in S0). `_asked_once` replaced S4. `input_failures`, `admit` kept (S1). `trajectory`, `result`, `_plan`, `_digest`, `flat_plan`, `OF_A_RUN`, `OF_A_PLAN` deleted S0 (the flat entry points). `Sample`, `batch` kept (C). `check` retire? G0 |
| `component.py` | Kept: it is "one connected set as one component". `Network` (111–220) changes in S2. `watch` and `guards` (336–360) read `RuleState.version`: changed in S4 |
| `reports.py` | Kept until C, which merges it into the one report. Its reader `_OfResult` goes to the record in S0 |
| `trees.py` | Kept |
| `smooth.py`, `influence.py`, `derivatives.py` | Deleted B0-5. `places.py` has no reader after it |
