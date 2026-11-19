# A5: catalogue fit — findings

> M-prep (2026-11-19) brought `translate.py` and `check.py` to the language of now; `briefs/m.md`
> says how stage M runs them. What follows is A5's record, in the spelling that G0 replaced.

## 1. Summary
- The new language covers the catalogue. Each of the 401 census keys (358 used, 43 never used) has a new form or a ruling (`migration-table.md`, checked by `table_check.py`).
- 96.1% of logical lines translate mechanically (6691 of 6960). The rest are flows with several pairs (172 lines), events with several outcomes (75), `versus` (11) and `since(e.outcome)` (11).
- Six hand translations pass `check.py`: both examples, `water.scn` with `jamestown`, and `heat_wave_blackout` and `cyber_learning_loop` in full.
- The bad case (unserved volume turned into a formula of the present shortfall) fails on kind, on the missing flow and on cumulative.
- The old compiler proves 19 outputs cumulative in these files, and the check lists each one. 18 never fall by its simple rule in both files. It cannot decide `casualties`.
- No outcome in the catalogue reads a value that an earlier line of the same outcome writes. The new stage order therefore changes no result. `check.py` now tests this (`order`).
- The main owner decisions are R-A5-06, R-A5-08 and R-A5-09.

## 2. What was done
`sh /home/user/napkin/scratch/rewrite/a5/run_all.sh` runs everything and prints `run_all: OK` (24 s, load 3.8; it sets `PYTHONPATH=/home/user/napkin-base`). It runs:
- `census.py`: writes census.md and census.json, using the old parser and compiler.
- `translate.py [FILE]`: writes translated/auto/ and prints the share translated for each file.
- `check.py OLD NEW [--quiet] [--no-compile]`: exits 1 on any difference.
- `table_check.py`: checks the migration table against the census.

The helpers are `oldmodel.py`, `exprs.py` and `newreader.py`.

The hand translations are in `translated/`, each started from `translated/auto/`. I finished the 28 multi-leg flows of heat_wave_blackout and cyber_learning_loop from translate.py's drafts with a helper kept in my scratchpad. Their legs are named after the target store.

I mended finished work in three places:
- `exprs.canonical` had no case for an old name node, which crashed the check.
- newreader now compares E in `outflow.capacity = formula(E)`.
- newreader gives `formula(bool)` no unit.

## 3. Results
| Old | Verdict | Cumulative listed |
|---|---|---|
| piano_tuners | PASS | 1 |
| reservoir | PASS | 2 |
| water.scn | PASS | 4 |
| jamestown | PASS | 0 |
| heat_wave | PASS | 10 (`casualties` undecided) |
| cyber | PASS | 2 |
| bad/water.scn | FAIL, as it must: `kind` Utility.unserved is a formula; `flow` count_unserved is missing; `cumulative` unserved_volume reads demand − delivery_rate | |

The check compares:
- every number with its unit, and every text;
- each name's kind and unit;
- expressions at their place, ranges and scales;
- flow legs with their requests;
- store limits and allocation;
- triggers, `once`, stages, and the lines of each outcome;
- status cases, asserts, `sees`;
- instance lines, options, and runs with their order;
- records, notes, `use`, the scenario line;
- `report:` entries with `cumulative` and `lag`;
- the new `order` test.

Share translated by machine: 100% for the variants and piano_tuners; water.scn 97.7%; heat 97.3%; iv 94.1%; cyber 92.6%; reservoir 83.7%.

Not verified:
- No new compiler exists, so nothing is run.
- For outcomes, the check compares the names that the conditions read, not the conditions.
- The old file's number count leaves out instance-line numbers. The instance-line comparison still catches a changed value (0.78 in place of 0.781186 fails).
- iv and 15 of the variants are not hand-checked.
- The "never falls" rule is syntactic. It is no proof.

## 4. Rulings
### R-A5-01: Scenario line [owner]
Rule: keep `scenario "T"` with `summary`, `horizon`, `scope`, `library`, `timescales` and `resolution` as lines under it. `resolution` keeps its old meaning until the engine names a control.
Alternative: a `scenario:` block of fields.
Example: `scenario "Pumps"` / `horizon 5 days`. The rule changes 0 lines; the alternative rewrites 36 and makes the scenario look readable from a formula.
Recommendation: the rule.

### R-A5-02: Records, claims, notes [owner]
Rule: `record n: kind "text"`, with `assumption ID` or `convention ID` on the line under it, then `claims:` and `datum:` as today. A record in place is `@kind "text"` with the same ID line under it. `notes:` is unchanged.
Alternative: the ID after the kind.
Example: in `source_transfer A-TIMING`, the ID reads as a source citation.
Recommendation: the rule. It is the spec's own candidate and it migrates by machine.

### R-A5-03: use/variant/change precedence [owner]
Rule: the first of these that applies wins:
1. an external edit of the run;
2. an option of the run (a thing line beats a `Template.instances` line);
3. a `change`;
4. a variant's instance line;
5. the template.

A `use` module only adds names. These are errors: two options of one run that set one value, two `change` lines on one value, and a `change` of a missing name.
Alternative: the last file read wins.
Example: template rate 2, variant 3, option "Fast" 5. The rule gives 5 with "Fast" and 3 without, whatever the order of the files.
Recommendation: the rule. It is the old compiler's order, with `change` placed between instance lines and options.

### R-A5-04: Options and runs [owner]
Rule: keep `options "G":` / `"Opt":` / `path = v @r`, and `runs:` / `n = "A" + "B"`, with full paths. Only an `input` can be set by an option.
Alternative: a run as a typed value.
Example: all 108 setting lines and 36 runs stay as they are.
Recommendation: the rule.

### R-A5-05: Evidence for option or change values [owner]
Rule: a number or yes/no set by an option or a `change` needs a record. A text needs none.
Alternative: today's exemption.
Example: 104 of 108 option lines already have a record, and the 4 without one set texts, so the rule breaks no model.
Recommendation: the rule.

### R-A5-06: Where runs and comparisons live [owner]
Rule: named runs stay in the model. Pairs go into brief.toml as `[[comparison]]` with `run` and `against`, and `featured` names one of them. A study call takes a list of runs and gives one trajectory each.
Alternative A: a core-read experiments.toml that holds the runs and the pairs.
Alternative B: a `comparisons:` block in the model.
Example: `delayed_human = "Delayed" + "Human team"` stays in the model. brief.toml gets `[[comparison]]` with `run="delayed_human"` and `against="delayed_refuses"`, beside its `[[sweep]]` tables.
Recommendation: the rule. brief.toml already holds `featured` and the sweeps, `tools/publish/brief.py:290` already checks the pairs, and only 11 lines move.

### R-A5-07: An instance replaces a template formula [owner]
Rule: an instance writes `m = formula(E)`. The template must declare `m` as a formula, and a scalar is refused.
Alternative: an empty slot in the template that each instance fills.
Example: `speed = formula(2 * this.base) @r` is accepted; `speed = 3 m/s` is refused.
Recommendation: the rule. It matches the spec's formula type rule.

### R-A5-08: Outcomes, chance and choice producers [owner]
Rule: an event with outcomes becomes one `switch` in one stage:
- by condition: `switch (A if C1 else B if C2 else E):`
- by chance: `switch chance(A: p, B: else):`
- by an actor: `switch choice(OPEN: 1, WAIT: else):`. The numbers are the forecast, and a case left out is unavailable.

The case labels give the selector its enum type. An outcome's texts, records and `role` go under its case.
Alternative: the earlier proposal, a local `outcome: enum[...]` and then `switch outcome:`.
Example: `start_manual` in water.scn.
Recommendation: the rule. I changed the earlier proposal: the spec evaluates a selector once, the local adds lines, and the check can see what the selector reads. Keep a local only when a later stage needs the value.

### R-A5-09: Report selection and a default `report:` [owner]
Rule: an `output` becomes a named value, `name: formula(u) = formula(E) in [0, none]`, with no range if it was `signed`. Its text, `about`, `category` and `scope` lines stay with it. A package `report:` block holds the default selection, one `path [cumulative] [lag D]` entry per line. `level` means no `cumulative`. `unestimated "R"` becomes `= none` with `@identity "R"`.
Alternative: a report flag on each declaration.
Example: `report:` / `tunings_done cumulative`.
Recommendation: the rule. Each `cumulative` is a claim that the new compiler must prove.

### R-A5-10: Old forms with no new form [owner]
Rule: these have no form in the first version, each with its message:
- copies `* k` and `copy`: "write the instances or use a table";
- `while` on an event header: "use `after D when C:`";
- `count(e.outcome)` and `since(e.outcome)`: "start an event in that case and read it";
- status lines and `output m` in an instance;
- `assert C within TOL`: "write `x in [lo, hi]`".

Alternative: keep `since(e.outcome)` by storing the case in each occurrence.
Example: 11 lines read `since(attacker.alter_on_restart.done)`. Each needs one added event.
Recommendation: the rule.

### R-A5-11: Scale hints and store range [owner]
Rule: `size S` becomes `scale S`. A store with no range gets `in [0, none]`.
Alternative: keep `size`, and leave the store unbounded.
Example: `due: tunings = this.need in [0, none] scale 20000 tunings`.
Recommendation: the rule.

### R-A5-12: Names of flow legs [owner]
Rule: the author names each leg. A migration tool may default to the target store's name, or to `owner_target` when two legs share a target.
Alternative: legs read by position.
Example: water's `replace` has the legs `labor`, `work` and `parts`. The defaults would be `field_crew_used`, `replace_done` and `parts_used`.
Recommendation: the rule. The spec reads legs by name.

### R-A5-13: Names and reserved words [owner]
Rule: members are read as `this.x`, through a link as `this.link.x`, and across a template as `Template.instances.x`. A top-level thing stays readable by its name everywhere. Members may be named `status`, `start`, `capacity` or `size`; `from` and `to` stay reserved.
Alternative: a declared link for every read of another thing.
Example: 1007 such reads are kept as they are.
Recommendation: the rule. The 13 members named `status` and 4 events named `start` need no rename.

### R-A5-14: `sees` [owner]
Rule: `sees thing.field` under the actor.
Alternative: `sees` written under the value that is seen.
Recommendation: the rule.

### R-A5-15: What a migration check compares [technical]
Rule: a migration passes only with no difference in any group of section 3. The check also lists every output proved cumulative, for the new compiler to prove.
Alternative: check only that numbers and texts are present.
Example: the bad case keeps every number and text, so the alternative passes it.
Recommendation: the rule. Run it at G0, and add a comparison of switch conditions.

## 5. Not covered
- No hand translation of iv_fluid_shortage or 15 of the variants.
- No trajectories are compared.
- Four strict `when` thresholds are not classified.
- Where a human decision pauses the run is not covered.
