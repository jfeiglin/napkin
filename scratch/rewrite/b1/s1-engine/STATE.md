# S1-E state: the engine, second slice (templates, tables, collections) — IN PROGRESS

Brief: `briefs/s1.md` (S1-E), with `COMMON-B.md` and `s0-engine.md`.

## Design (decided, built)
- Kept S0's per-value plan (engine names `member.field`). New: `timeline/pools.py` (a pool per
  template: ids, link columns, reverse CSR `Pool.back(link)`, `Keys` sorted index for `.at`),
  `timeline/collections.py` (Entries/Reduction/Keyed, evaluator `reduced`/`looked_up`, `node_of`
  for a component, exact `history_of`), `timeline/family.py` (`Family`: every set of one flow whose
  rate reads nothing that moves, on arrays, exact lines; `Columns`: a formula shared by a
  template's members evaluated once over the rows with `core.arrays.values`).
- Plan kinds LINK (text: the linked member's id, recorded), REDUCE, LOOKUP (no record key; the
  recorder keeps their histories internally; `read` evaluates them from recorded values; the
  reader caches one plan per program). Value has `shape`/`binding` for column evaluation.
- Entity read in an expression -> text const of the member id. Where tests per entry, constants
  folded at plan time; `T.instances.where(item.link == this)` uses the reverse index. Membership
  fixed for the run (found at start, `Run.kept_of`). A reduction/keyed read that reads no `this` is
  one shared value (name `|spelling`), else `member|spelling`.
- `.at(t)` stepped: `Run.stepped_of` (key times); the run is cut into windows at the key times of
  the stepped reads that sets read: family first (row events), then components; at each key time
  the component's store `S` entry is set, the family refreshes. `.at(x)` with x fixed -> fixed;
  other x, or a lookup of a moving value -> Outside (S4).
- Flow between stores of members of two templates -> Outside (S2). Assertions over inputs checked
  once at start (failure at 0); over state -> Outside (S4). Literal naming a member twice -> setup
  failure at 0 (`plan.failures`). Start is iterative (3,000-row link chain test).
- Recorder: formula over held reads -> one piece per interval (no fit); bare-ref formula copies.
- test_cumulative_integration dense fixture: the two single-flow accounts now read pending * 0,
  to stay in the component (a single-flow set with held rate runs on arrays).
- test_record: the link refusal case replaced by an assertion over state (S4).

## Done
- Engine as above; tests/engine/test_collections.py (15); test_programs SUBSET + keyed_lookup,
  oracle comparison accepts Unavailable where the oracle raises below the first key.
- Exit set (tests/engine live, core, program, reference, commands): 1,624 passed.

## Contract notes (for the last message)
- check.Resolver: a path that ends on a collection value (`count(this.pumps)`) is refused
  ("no collection"); `this.pumps.x` works.

## Next
1. Port test_timeline_bounds.py, test_timeline_long_steps.py (parts without events).
2. Benchmark 30,000 rows (scratch script), and speed of the plan at scale if needed.
3. Lint/format; final message.
