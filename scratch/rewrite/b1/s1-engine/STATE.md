# S1-E state: the engine, second slice (templates, tables, collections) — DONE

Brief: `briefs/s1.md` (S1-E), with `COMMON-B.md` and `s0-engine.md`.

## Design (built)
- S0's per-value plan kept (engine names `member.field`). New modules: `timeline/pools.py` (pool
  per template: ids, link columns, reverse CSR `Pool.back(link)`, `Keys` sorted index for `.at`),
  `timeline/collections.py` (Entries/Reduction/Keyed; `reduced`, `looked_up`; `node_of` for a
  component; exact `history_of`: sums of lines by two pairwise trees, count/any/all/min/max of
  held values), `timeline/family.py` (`Family`: every set of one flow whose rate reads nothing
  that moves, on arrays, exact lines, at any size; `Columns`: a formula shared by a template's
  members evaluated once over the rows with `core.arrays.values`). `trees.Pairwise` has min/max.
- Plan kinds LINK (text id of the linked member, recorded), REDUCE, LOOKUP (no record key; the
  recorder keeps their histories internally; `read` evaluates them from recorded values).
  `Value.shape/binding` for column evaluation. `Expanded` (leaves, formulas, stepped, time).
- Entity read in an expression -> text const of its id. Where tests per entry, constants folded
  at plan time; `T.instances.where(item.link == this)` by the reverse index. Membership fixed for
  the run (`Run.kept_of`). A derived value that reads no `this` is shared (`|spelling`).
- `.at(t)`: `Run.stepped_of`; the run is cut at the key times read by rates: family first, then
  components; a component reads the value from its store `S`, set at each key time. `.at(x)`, x
  fixed -> fixed. Other x, or `.at` of a moving value -> Outside (S4).
- Refused: a flow between stores of members of two templates (S2); an assertion over state (S4).
  Assertions over inputs: checked at the start, failure at 0. A literal naming a member twice:
  setup failure at 0 (`plan.failures`). Start is iterative (no recursion limit).
- Recorder: a formula over held reads is one piece per interval; a bare-ref formula copies; the
  family's request/capacity formulas come from the run; a narrow request computes only what it
  needs. The reader reuses the last run's plan (`record.remember`), indexes histories by key.

## Done
- Tests: `test_collections.py` (15, new); `test_programs.py` SUBSET + keyed_lookup (oracle may
  raise below the first key: engine reads Unavailable). Ported (replace in place, take off
  dormant.txt): `test_timeline_bounds.py` (2; the Plan.flat test deleted), 
  `test_timeline_long_steps.py` (5; events removed: the fade stops by a switch of its rate, the
  drain is held at its bound, the negative rate fails the run, the hump is one matrix-exponential
  segment). Mended: `test_record.py` (link case -> assertion over state, S4),
  `test_cumulative_integration.py` (dense fixture's single-flow accounts read pending * 0).
- Exit set (tests/engine live, core, program, reference, commands): 1,624 passed; ports 7 passed.
- Benchmark `b1/s1-engine/bench.py 30000`: build 1.4 s, plan 4.7 s, run+record 7.2 s (210,012
  histories, 588,009 pieces), read 4 paths x 3 times 0.55 s; record of 2 values: 9.2 s.

## For the main session (contract notes)
- check.Resolver: `count(this.pumps)` (a path ending on a collection value) is refused.
- `Record.history` is a linear scan (slow at 200k histories); an index would help.
- build: a field named `start`/`draw`/`where`/`by`/`at`/`choose` cannot be read by a handle.

## Not done
- Per-row formulas other than a family's request/capacity are fitted row by row (slow at scale).
- A failure inside one long numerical segment is timed at the segment's start (as in S0).
- Setup reports for equal keys of `.at` and coverage at a lower bound (front end/setup).
