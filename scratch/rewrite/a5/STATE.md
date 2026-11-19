# A5 state (checkpoint 1; update at each milestone)

> Stage M uses these scripts as M-prep brought them to the language of now (2026-11-19): see
> `briefs/m.md` and `b1/m-prep/STATE.md`. What follows is A5's own record, in A5's spelling.

Run everything with `PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python X.py` from this folder.

## Done, by task of the brief
1. Census: DONE. `census.py` writes `census.json` and `census.md` (23 files, 358 keys, 0 unresolved names). Rerun once at the end. Helpers: `oldmodel.py` (old parser, name table `Symbols`, `quantity_kinds`: agrees with the old compiler on 700 of 700 number vars).
2. Hand translations: NOT STARTED. `translated/auto/` holds the output of `translate.py` for all 23 files; start each hand file from it.
3. `migration-table.md`: NOT STARTED.
4. `translate.py`: WORKS. 6691 of 6960 logical lines (96.1%), 0 lost. Left for a person: flows with several pairs 172, events with several outcomes 75, `versus` 11, `since(e.outcome)` 11.
5. `check.py`: WRITTEN, FIRST RUN FAILS (see "In the middle"). `exprs.py` (tree, printer, old-to-new rewrite, reader of new expressions) and `newreader.py` (reads all 23 auto files, 0 unread lines) work.
6. Comparison proposal: decided, not written (below).
FINDINGS.md: started, with TODO marks.

## Spellings and decisions (each is `# PROPOSED` unless the spec gives it)
- Names: a member is `this.x`; through a link `this.link.x`; another thing by its name `relief.status`; a template's list `Utility.instances.x`. Top-level names stay readable everywhere (1007 reads depend on it).
- `let f: u = E` is `readonly f: formula(u) = formula(E)`; `let k = v` is `readonly k = v`; `var s: "a"|"b"` is `s: enum[A, B]` (members upper case); number var is `n: u = start`.
- A stock with no range gets `in [0, none]` (`none` = no bound on that side). `size S` is `scale S`.
- Flow: `flow f: this.a -> this.b` with `request = formula(RATE if WHILE else 0)`; outside is `SOURCE` / `SINK`.
- Share: under the store, `outflow.capacity = formula(LIMIT)` and `outflow.allocation = priority(a, b)`; its text and records go under the capacity line.
- Flow with several pairs: `flow f:` with named legs `flow leg: A -> B` under it, each with its `request`. Leg names by hand.
- Event: `e = event():` then `when C:` / `this.e.start()` / `reset when false` (for `once`), then `after D:` with the lines. `since(e) >= d` becomes `count(e.occurrences) > 0 and since(e) >= d` (the old compiler's own reading).
- Outcomes by condition: occurrence local `outcome: enum[...]`, set by a conditional expression, then `switch outcome:` with one case for each. Choice: `switch choice(OPEN: 1, WAIT: else):`; chance: `switch chance(A: p, B: else):`.
- `since(e.outcome)`: no form; start an event of its own on that branch.
- Sum check `assert a + b is T within TOL` is `assert a + b in [T - TOL, T + TOL]`.
- Output: a named formula (`name: formula(u) = formula(E) in [0, none]` unless `signed`) plus an entry of a `report:` block: `path [cumulative] [lag D]`. `level` = no `cumulative`. `distinct @r` = `@r` on the formula. `unestimated "R"` = `= none` with `@identity "R"` in place. `about`, `category`, `scope`, `title`, `role`, `sees` stay as lines.
- Options: as today; `Template.x = v` is `Template.instances.x = v`. Runs: `runs:` as today without `versus`.
- Comparison (task 6), recommended: named runs stay in the model; a comparison is the list of runs of one study call, and the catalogue names its pairs in `brief.toml` (`[[comparison]]`, `featured`). Alternatives: a package file `experiments.toml` read by core; a `comparisons:` block in the model file.
- Records: `record n: kind "text"`, the ID on a line under it (`assumption ID`, or `convention ID`), `claims:` and `datum:` as today. Notes, `use`, `variant`, `change`: as today.
- Instance that replaces a formula: `m = formula(E)` in the instance; the template then declares a formula.
- Evidence of an option line: require a record (104 of 108 lines have one; the 4 without set a text).
- Not in the first version: copies `* k`, `while K` on an event header, `count(e.outcome)`. `each W` = a trigger capture with `reset when W != captured`.

## In the middle of
(checkpoint 7) All done but FINDINGS.md: the harness refused to let this agent write it ("subagents return findings as text"). Its full text went to the main session in the hand-back message; the main session saves it as FINDINGS.md. run_all.sh OK.

## Steps that remain, in order
1. Fix the crash above; make `check.py` pass on `translated/auto/examples/piano_tuners/model.scn`.
2. Hand translations in `translated/`: both examples in full; `water.scn` in full plus `variants/jamestown`; heat wave slice (options, runs, the `ai` thing with `sees_switching`, `crews` status); cyber slice (the runs with `versus`). Copy from `translated/auto/` and replace each `# TODO(hand)` block. List each `# PROPOSED` line.
3. Run `check.py` on each hand translation until it passes.
4. Bad case: copy the hand `water.scn`, turn `unserved` into `formula(max(0, demand - delivery_rate) * ...)` and drop the flow `count_unserved`; `check.py` must FAIL on kind and on cumulative. Keep it in `translated/bad/`.
5. `migration-table.md`: one row for each census key group; a script check that every key has a row.
6. `run_all.sh`: census, translate, each check, the bad case.
7. FINDINGS.md: summary, how to run, results, rulings `R-A5-01..`, not covered. Then the 300-word report.

## Facts in no file yet
- Only `examples/reservoir` has `sees` and `choice`. `heat_wave_blackout` has none: its brief slice uses `ai` (a three-outcome event by condition) and shows the choice spelling as a marked alternative.
- The catalogue never uses: tables, copies, `change`, `each`, `while` on events, `delayed`, `count(list)`, `any`, `all`, lists in `min`, yes/no states, outcome `when`. One `use`. One drawn input, one draw in an event.
- Every non-sum `assert` (21) is an input check; every state check is a sum with a tolerance (17).
- Every crossing that the old compiler classified uses `<=` or `>=` (no strict continuous threshold).
- 40 instance lines replace a `let` of the template (cyber 39, water 1). 13 members are named `status`, 4 events `start`.
- `scenarios/water_controls_wipe/model.scn` does not build alone (templates only); use a variant for compiled facts.
- `versus` users: `napkin sample` (same draws), `compile --json`, draw subtitle, `tools/publish` (pairs, order, `featured` must be a versus pair), tests. `tests/expected-orders.json` holds run orders.
- Old option precedence: default < option (template line < thing line) < edit of every run < of one option < of one run; options of two groups never set one value (compile error).
- Dead end: classifying stock/tally per declaring thing by owner name fails for flows that name an instance; use `Symbols.declarer`.
