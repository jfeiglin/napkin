# Brief A4b: members that come and go, and the map of the engine code

Folder: `scratch/rewrite/a4b/`. Read `briefs/COMMON.md` first. A second agent has brief A4a (links
and flows across tables, connected sets, the record of a run). Do not do its work.

## Two deliverables, in this order

### 1. `LAYOUT.md`: the map of `timeline/run.py` and `timeline/plan.py`. Deliver it first.

The main session waits for this file. It will split `napkin/engine/timeline/run.py` (3,490 lines;
the class `Run` starts at line 619) into modules by pure moves, with no change of behaviour, so
that later steps delete whole modules.

Read, at the base commit: `napkin/engine/timeline/run.py`, `plan.py` (1,411 lines), `__init__.py`,
`component.py`, `reports.py`, `trees.py`, and `docs/engine.md` ("Rules", "One moment", "Between
moments: the solver", "Play", "Tables and tiers"). Read `scratch/rewrite/PLAN.md`: choices 2 and 3,
steps B0 and B1, and slices S0 to S5.

One change is already decided and happens before the split: the whole-run derivative code goes
(`timeline/derivatives.py`, `influence.py`, `smooth.py`, the tangent arrays in `run.py`,
`Plan.fast()`, `plan.optional`). Mark what that removes; do not plan modules for it.

Write a table with one row for each method or group of methods of `run.py`, and one for each of
`plan.py`: its lines, what it does in one line, and its fate: **kept** (the slice that changes it,
if one does), **replaced** (by which slice), or **deleted**. Then propose the modules. The plan has
a provisional list: `state.py` (columns and the past), `segments.py` (lines, blocks, closed forms),
`readers.py` (closure and apply), `choices.py` (picks and the pause), and the later new ones
`spaces.py`, `islands.py`, `network.py`, `collections.py`, `moment.py`, `occurrences.py`,
`triggers.py`, `record.py`. Change the list where the code says otherwise. Each module of the split
must be made by moves only: say how one class of 2,870 lines is cut (mixins, or functions that take
the run), which names cross between modules, and in which order to move them so that the tests pass
after each move. Name the three or four test files that guard each move.

The parts that the later design replaces, for orientation: `RuleState` (253), `read_rule` (2439),
`_trigger` (2661), `_fire` (2829), `settle` (3210), play (3036, 3320). Kept: `Solution` (267),
`field` and `decide` (1441, 1656), lines and floors (1862, 1931), `read` and `read_past` (821,
848), `closure` and `apply` (2189, 2222).

### 2. Members that come and go

The new language starts an occurrence at each `.start(...)`. An occurrence owns parameters, locals,
stages, and its own flows and stores. Its flows join the network when it starts and leave when it
finishes. The present engine has a fixed structure: one pending firing for each rule and row, and
proofs and readers that assume that no member appears during a run.

Read `scratch/rewrite/spec.md`: "Collections, keys and projections" (the paragraph on membership),
"Flows created during a run", "Events, triggers and occurrences" (every part), "Solver and
execution contract", "What a proof establishes", and the last paragraph of the spec. Read at the
base commit: `napkin/model/analysis/values.py` (the proofs; 716 and after), `analysis/structure.py`
(the trigger classes), and how `run.py` predicts a crossing and keeps its readers up to date.

Design, and show with a standalone spike in plain numpy:

- **A pool of frames** for the occurrences of an event: parameters, locals, the step pointer,
  `started`, `done`, `active`. It grows. A finished occurrence stays as a record.
- **Flows and stores that join and leave** the network, and the totals of each receiver that must
  follow at once: `outflow.actual_rate`, `count(store.outflow.flows)`, the sum of the requests.
- **The reader graph.** When a member joins or leaves, which values, rates and predictions must be
  made again? Show it with this case: a tank at 10 L fills at 1 L/h; an occurrence drains 2 L/h
  more from 2 h to 4 h; a trigger on `>= 16 L` must fire at 10 h. A prediction that is not made
  again fires at 6 h, when the tank holds 12 L.
- **The proofs.** The present proofs cover a fixed structure: stocks with a proved zero face,
  crossings of a value that moves one way, outputs that never fall. Say how each is stated over the
  templates of events, so that it covers every occurrence that can exist. A tally that only
  nonnegative additions change, from any occurrence, never falls. A store that an occurrence can
  drain does not qualify.
- **Cost.** 100,000 starts and finishes in a run, 1,000 alive at a time, each with one flow from a
  shared store with a limit. Measure the cost of a start, of a finish, and of the predictions that
  are made again.

## Rulings that you owe

The layout of the pool. What stays readable on a finished occurrence and its flows, as the engine
would hold it. The budget for the count of occurrences, and its message. How the proofs are stated
over templates. The module layout.

## Exit

`LAYOUT.md` first. Then the spike and its script, and `FINDINGS.md`.
