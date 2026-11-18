# STATE of prototype A4b (updated at each milestone; newest facts first)

## Done, and where
- `LAYOUT.md`: complete (map of `run.py` and `plan.py`, the split by mixins, order, guards).
- `split_run.py`: complete and checked (one pass, module by module, and after a mock B0-5).
- `spike/exact.py`: `ExactSum`, done and tested (2,000 random histories equal `math.fsum`).
- `spike/expr.py`, `spike/program.py`: done (expressions with `ev`, `names`, `iv`; the records).
- `spike/engine.py`: written in full (1,570 lines), NOT yet run green. `spike/cases.py`: written.
- `FINDINGS.md`: started; rulings drafted; results marked TODO.

## In the middle of
First run of `python spike/cases.py`. It stops in `Columns.add`: the edge table has a column named
`capacity`, which overwrote the attribute `Columns.capacity`. Fix: rename the attribute (`room`).
Then debug case by case, in the order of `cases.main()`.

## Steps that remain, in order
1. Make `cases.py` green: flows table (0,1,0,1), frozen request, shared limit (2; 1.5+1.5; 2; none),
   the 6 h / 10 h case with and without `forget_membership`, grinder 108 g, clock 3-6-9, inspect
   3 h and 5 h, the delivery table of the spec, failed retirement, starved flow, two starts.
2. `spike/test_spike.py`: pytest over those cases, plus "fresh formation" (rebuild the endpoint
   from its present members at random moments and compare rates bit for bit).
3. `spike/proofs.py`: writer sites for each (template, field); never-falls, one-way, line class;
   check against random runs of the spike engine (a proved value never falls; an unproved one has
   a run in which it falls).
4. `spike/measure.py`: 1,000 lanes, each repeats `deliver` (cases.py `delivery()`), 100,000 starts
   and finishes; limit not binding and binding; cost of a start, of a finish, predictions made
   again; bytes for each occurrence; best of three, `uptime`. Also k = 10, 100, 1,000, 10,000.
5. `FINDINGS.md`: fill the tables; final check of every ruling against the runs.

## Decisions taken (one line each, with the reason)
- Pool of frames: one `Columns` for each event; a row is an occurrence for good, never moved, never
  reused, so the row number is the identity and the creation number. Reason: timeline entries, the
  trace and `.at(t)` name rows; a moved row would need a map.
- Active rows: a compact list beside the pool (swap-remove, `place[row]`). Vector work reads
  `column[active]`. Reason: 1,000 alive among 100,000 rows.
- For each receiver: `newest`, `started_count`, `done_count`, `active_count`; `before[row]` chains a
  receiver's occurrences. Reason: `count`, `any(active)`, `.at(t)` and `since` are O(1).
- A parameter has two columns: the argument as given (`arg:name`) and the live copy.
- Local stores are rows of the one table of stores (line: `y0, t0, rate, version`); local flows are
  rows of the one table of edges; the frame holds their ids. A finished flow keeps key, endpoints,
  last request, rate 0, `alive` false; a finished local store must be empty within its tolerance.
- Endpoint: unordered member list (O(1) join and leave), count, and the EXACT sum of the requests
  (`ExactSum`). Reason: a running float total keeps its history, and a pairwise tree depends on
  which slot a member got; the exact sum equals a freshly formed problem bit for bit.
- Reader graph: at the level of templates, never one list for each member. The membership of a
  collection is a written name: `('occ', T, E)` and `('flows', T, store)`. How a write finds its
  readers: SAME, LINK (reverse index), FRAME, RECEIVER. A join or a leave is a write.
- Round: stages and starts commit; requests that read a written name are evaluated again; ONE
  sharing pass; each store whose rate changed restarts; then triggers and gates are read. A firing
  or a released gate acts in the next round (spec: once in a round).
- Predictions are a column for each pool. One row that changes: one timeline entry with the row's
  version. Many rows together (8 or more): ONE entry, the least time; due rows are found in the
  column. Reason: under a binding shared limit every join changes all k predictions.
- Proofs over templates: the writer sites of a (template, field) are the flow declarations (of
  entities and of events) whose endpoint has that static type, and the stage statements that
  assign or move it. Never falls: every site adds zero or more. One way between moments: every
  flow declaration there points the same way. Line class: no request, capacity or endpoint limit
  reads a moving name; a join or a leave is a moment. Reductions over `.flows` and over `active`
  are never monotone (members leave); `count(occurrences)` and `count(.done)` are.
- Budgets: `max_occurrences` (total starts), `max_active` (alive at once), `max_rounds` (a moment).

## Numbers measured so far
- Split: 143 functions same bytecode, `Run` same 103 attributes; after removing the 14 derivative
  methods 129 functions. `python split_run.py COPY --check /home/user/napkin-base`.
- Smoke digest of 10 runs, base and split copies: `f765c4db…` (scratchpad `a4b/smoke.py`).
- No cost number yet.

## Facts that are in no other file yet
- D-65: a prediction that comes due makes its crossing hold WITHOUT a look at the value
  (`run.py:2447`, `holds(..., reached)`). So a stale prediction fires wrongly; only the version of
  the rule (`run.py:2444`, `stale` at 3441) protects. This is the 6 h case.
- Today a line that restarts marks the rules that read it (`closure` 2202-2205, `apply` 2306).
  The fixed part is `plan.parts[name]` (`plan.py:690-709`): a new flow is in no list.
- The fast tier has a second copy of "a coupled transaction must request every flow together"
  (`run.py:1289`); S3 must reverse it there too, not only in `allocation.py:165`.
- `timeline.run` is the function; import the module with `importlib.import_module`.
- Dead end: one heap entry for each prediction under a binding limit is 2e8 pushes for the cost
  case. Dead end: `Columns` must not take a column named like one of its own attributes.
- Open item 28 of `open-items.md` (contact tolerances, certified predicates) is mine too.
