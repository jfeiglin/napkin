# Brief of stage M: the migration of the catalogue

Read `briefs/COMMON-B.md` first (its rules hold: no git command that changes the repository, at most
`-n 2`, the house style, a short last message); then `PLAN.md`, "Changes after G0" items 1 to 17
and the section "M. Catalogue migration"; then `b1/m-prep/STATE.md`, which made this stage ready.
The language of now is `napkin/model/` (the docstrings of `semantic.py`, `compile.py` and
`support.py`), `spec.md` as the changes after G0 amend it, and the examples of `tests/language/`.
`examples/piano_tuners` is migrated by hand; it is the model of a finished package.

Stage M translates the five packages of the old language into the language of now, ports the tests
that read them, ports the publisher, and ends at gate G3: `python -B -m tools.check --all` is green,
the dormant list is empty and its mechanism deleted.

## Setup

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.lock && .venv/bin/python -m pip install -q --no-deps -e .
git worktree add --detach /home/user/napkin-base 8488047    # the old compiler, outside the checkout
```

The old compiler and the compiler of now are both the package `napkin`, so they never share a
process. The scripts of `scratch/rewrite/a5/` handle this themselves: what reads an old model runs
with `PYTHONPATH=/home/user/napkin-base` (and checks that it loaded the old package), what reads a
new one runs with the checkout's own `napkin` and no PYTHONPATH, and each calls the other in a
process of its own. Set `NAPKIN_BASE` for a worktree elsewhere. Run a test of the worktree with
`PYTHONPATH=$PWD` from inside it.

## The scripts (`scratch/rewrite/a5/`)

| Script | Runs under | What it does |
| --- | --- | --- |
| `translate.py [--compile] [PATH...]` | old (`PYTHONPATH=/home/user/napkin-base`) | Translates old files (a file, or a package's folder; relative paths read from the base commit; none: every model) into `translated/now/`, with each package's `units.json`, `evidence/` and the catalogue's library, so the output compiles where it stands. Prints the share of logical lines translated, the lines left for a person by reason, what the language has no place for, and the names it chose. `--compile` compiles each entry (a package without variants, each variant) with the compiler of now and prints the refusals by code and the `no_record` warnings. `--stdout FILE` prints one translation. Never writes over a model |
| `check.py OLD NEW [--rename A=B]... [--quiet]` | now (no PYTHONPATH) | Compares a whole new model with its old one, by meaning; exit 1 on a difference. Groups: `compile`, `number` (value in base units and dimension, counted), `text` (counted), `kind` (input, fixed, formula, state, stock, tally, link, collection, flow, event, entity, template, member, with the dimension of the type), `flow` (the stores it joins), `cumulative` (each value that the old compiler proved cumulative in a run is proved never to fall by `napkin/program/proofs.py` in the same run). `--rename Thing.status=Thing.state` declares a rename |
| `oldmodel.py ENTRY` / `newmodel.py --compile ENTRY...` | old / now | The two halves that the others call: the old model's facts as JSON; the compile of new entries as JSON |
| `census.py`, `table_check.py` | old / any | A5's census of the old forms (`census.md`), and the check that `migration-table.md` covers every key |
| `run_all.sh` | both | Translates the two test targets with `--compile`; the check PASSES on the piano tuners; it FAILS each wrong copy in `translated/wrong/piano_tuners_{number,text,kind,cumulative}` in exactly its group; it reports the reservoir's one missing text; the table check. About 6 s |

`translated/auto/` and the hand drafts in `translated/examples/`, `translated/scenarios/` and
`translated/bad/` are A5's, in A5's proposed spelling (`none`, `report:`, `choice(...)`, `sees`):
useful only as references, such as A5's hand-named legs of the multi-leg flows.

### What the translator does by rule (its module docstring has the whole list)

- `at R` is `request` and `capacity` both (D15; S0's D-8 for the piano tuners); a flow of several
  pairs is a flow with legs, each named by its target store, `owner_target` for another thing's
  (R-A5-12: rename freely); a share is the store's `outflow.capacity` and `outflow.allocation`.
- An event is `e = event():` with its trigger (`reset when false` for `once`) and one stage.
  Outcomes by condition: a local `outcome: enum[...]`, set in the stage, and `switch outcome:`;
  by chance: `switch categorical(...).draw():`; an actor's choice: a field `forecast =
  categorical(...)`, a local `order` drawn from it, `switch order:` (change 15, the acceptance
  example `pump_dispatch`). One outcome under a condition is a stage guard.
- Units with `*` and `/` (D12): `tunings/tuner-year` is `tunings/tuner/year`. A stock with no range
  gets `in [0,]`. `size` is `scale`. A value named `status` beside status lines is `state` (pass
  `--rename T.status=T.state` to the check). A state whose start an option sets starts from a new
  input `x_start`, which the option sets (R-A5-04).
- What the language has no place for goes into `notes:`, by what it was: `reporting:` (an output's
  `about`, `scope`, `category`, `lag`), `not_estimated:` (an output with no estimate: its label, its
  reason and its records, D4), `comparisons:` (each `versus` pair, D9), `titles:` (of members written
  by hand). An event's `role` is a comment; `sees` is dropped (change 15); `level`, `signed` and
  `cumulative` say nothing now. Texts keep their braces as written.

### Measured (2026-11-19), the whole old catalogue

6,918 of 6,960 logical lines translated (99.4%). Left for a person (42): 21 cases of a switch
whose old outcome has no line (a case needs an action), 11 reads of one outcome's history
(`since(attacker.alter_on_restart.done)`: start an event of its own in that case, R-A5-10), 5 option
values that are calculations (an option gives a constant now, D2), 4 states that an option starts
from a calculation, 1 share of such a state.

| Entry | Compile by the compiler of now |
| --- | --- |
| `examples/piano_tuners`, `examples/reservoir` | compile, no warning |
| `iv_fluid_shortage` | 8: the readers of the four hand-left states (`unknown_name` 5, `flow_end` 3) |
| `heat_wave_blackout` | 5: `timescales` names values (2), units `customer`, `case` (3) |
| `cyber_learning_loop` | 79: units `operation`, `access`, `target`, `yr` (76), `timescales` (3) |
| `water_controls_wipe`, each of 16 variants | 7 to 9: `cycle` 1 (`Utility.tie_asks`), units `facility`, `min`, `yr`, `acre`, `ft` (2 to 4), 4 that depend on them |

The parse succeeds everywhere; these are the problems of the declared model, so more may show once
these are mended. The units: 32 units of the library and of the packages' `units.json` have a name
made of parts that are no unit (`facility-hours`, `USD2024_bn/yr`, `person-years/operation`,
`gal/min`, `acre-ft`): the language of now composes a unit of its parts, so each part must be a unit.
Declare the parts (`yr`, `operation`, `facility`...) or rename the unit; `translate.py` lists them
for the packages that it translates. The cycle: `Utility.tie_asks` reads `Tie.ask`, which reads the buyer's need,
which reads `tie_asks`; member by member the ties make no cycle, but the front end checks the
template. Ask the front end, or restructure.

## The order, and what each package needs

For each: translate; finish the hand lines; `check.py` each entry until it passes (renames
declared); compile; run in `median` mode; port its tests with `oracle-inputs.json`,
`expected-orders.json`, its evidence index, `style.toml` and spread files; add one behaviour test for
each headline quantity, which shows what kind of quantity it is (water: when service returns, the
unserved rate is zero and the unserved volume keeps its value); then `python -B -m tools.check
--scenario ID --skip-summaries`, and nothing wider. The check's evidence stage refuses a package
with a `no_record` warning (change 16): every input, stored value, timed event, status case, assert
and member's own value cites a record.

1. **`examples/reservoir`**, by the main session, first; then the migration guide from
   `a5/migration-table.md` (its new forms are A5's: correct them by the rules above). Hand: the case
   `WAIT` (only a text). Unlocks `tests/test_examples.py` (it imports the old API: `actors`,
   `evaluate_study`, `sample_result`; rewrite it on `run`, `report` and breakpoints).
2. Then one subagent for each package, in parallel:
   - **`iv_fluid_shortage`** (1,137 lines): the states `supply_left`, `ordinary_left`, `reserve`
     whose starts are calculations and whose starts options set; 5 option values that are
     calculations; 2 lags, now the caller's. Tests: `tests/` (acceptance, adversary, clinical damage,
     briefs, expected orders).
   - **`heat_wave_blackout`** with `explore.ipynb`: `timescales` as times; units; empty cases. Tests:
     reference, properties, sweeps, electricity damage, briefs; the notebook runs on the new API.
   - **`cyber_learning_loop`** (3,200 lines, in sections): the units; 11 `since(... .done)`; its six
     test files use `napkin.dynamics` (`VectorField(program, configuration)`, `b1/c-dynamics`).
   - **`water_controls_wipe`** with its 16 variants: the cycle; the units; check each variant as an
     entry (`OLD=.../variants/V/model.scn`). Its UI (`ui/server.py`, `ui/view.py`,
     `tests/test_ui_server.py`, `test_ui_view.py`) becomes a client of the checkpoints
     (`run(..., breakpoints)`, `Checkpoint`, `resume`, change 15), as `napkin play` is.
3. **The publisher** (change 13), once the catalogue is migrated: `tools/publish` over the new record
   (it imports `filled`, which is gone). It reads what the translator put in the notes
   (`reporting:`, `not_estimated:`, `comparisons:`, `titles:`) and `brief.toml` (`show`, `featured`,
   sweeps). `tools/check.py` `catalogue_problems` reads the old model (`model.outputs`): port it with
   the publisher (the scope of each reported value) or delete it. Once, at the end: `tools.publish
   --write` for all, which remakes the 110 committed outputs; then read every changed brief.

## Dormant tests that each part unlocks

`tests/dormant.txt` holds them; a file leaves the list when it is ported or deleted, and the main
session edits the list. Each package: its own `tests/` (`scenarios/<package>/tests/`, and each
variant's `tests/` data). The reservoir: `tests/test_examples.py`. The whole catalogue:
`scenarios/tests/` (catalogue, library integrity, limits, scenario files, methods links, assumption
review), `tests/draw/test_catalogue.py`, `tests/evidence/test_catalogue.py`,
`tests/evidence/test_scientific_spec.py`, `tests/test_scenario_ownership.py`,
`tests/test_scenario_scope.py`, `tests/test_tools_new_catalogue.py`, `tests/test_check.py`,
`tests/release/`, and the three catalogue cases of `test_runs.py` (`b1/s6-front/STATE.md`). The
publisher: `tests/publish/`. `tests/test_session.py` and `tests/engine/test_decision_resolver.py`
wait for S7's session as well; the dormant `tests/model/` files belong to the test cleanup.

## No change is silent

Parity is not required, but every change is traced. A scenario test that fails after the migration
is traced to its cause: a translation error is fixed in the translation; a change that follows from
the new semantics goes on the owner's list with the old and the new numbers. **No expected value is
edited to pass.** Each package's agent keeps its list in `b1/m-<package>/changed.md`, one row for
each changed number: the test, the quantity, the old number, the new number, the cause (the rule of
the spec or the change after G0), and the evidence (the trace or the check line). The main session
merges the lists for the owner at G3.

## For the owner, found while making M ready

- A case of a switch needs an action, so an old outcome with only its text (21 lines, such as the
  reservoir's `WAIT` and the water's `SKIPPED`, `STOPPED`) has no form: let a case hold only its text
  (its card), or drop the texts.
- A member written by hand has no `title` (69 in the water variants) and an event no `role` (10): the
  translator keeps the titles in notes and the roles as comments.
- `timescales` names values in two packages; the language of now takes times only.
- The library's units whose parts are no unit (32), and the template-level cycle above.
