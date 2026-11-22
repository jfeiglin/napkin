# Brief: restore the attack side of the catalogue, and empty the dormant list

Start from `claude/blissful-heisenberg-5me2hn` at the commit that adds this brief and work on a
`codex/` branch from it. That commit holds your engine refactor and recovery ports
(fast-forwarded from `6f4134a`) and the Linux review's fixes, which `PLAN.md` lists. The owner's
review merges your branch.

The engine rules in `audit/engine-finalized-simple.md` still hold:
- one owner per decision;
- fix every copy of a rule in one commit;
- the copy register;
- ask the owner when the spec does not decide: park that item, batch the questions, continue.

## What the Linux review changed that you build on

- Five decisions differed between Linux and macOS because they read the last places of a stock's
  ledger against its trajectory. They are fixed. `stocks.LEDGER_PROBE` now moves every ledger read
  that a decision makes, and every rebuilt method's start, two places each way.
  - `tests/engine/test_ledger_roundoff.py` uses it on those five cases.
  - The generated corpus uses it as transformation `roundoff` (`tests/engine/test_port_invariance.py`).

  A decision that changes under it depends on the platform, so it catches on macOS what only Linux
  showed before. Run it on everything you add.
- `napkin draw` works on every catalogue model, and `tests/draw/test_catalogue.py` is live again.
- Readings pages show six significant figures. A value within 10⁻⁶ of its own comparison scale
  shows as zero (`tools/publish/readings.py`, `Reader.comparison_floor`). The pages are the same
  on every computer.

## 1. Restore the attack side of every package (the owner's decision)

The owner wants the full historical models, not recovery-only versions. Everything each package
computes at `8488047` comes back. The supplied-incident inputs may stay as options; the default
and named runs are the full models.

Every dropped attacker is a fixed rule set by options. None used `sees` or a choice, so their
removal (change 15) is no obstacle. Current-language drafts of all four historical models,
attackers included, are in `a5/translated/now/scenarios/`. They predate changes 22–29 and your
port fixes, so they are starting points, not drop-ins.

| Package | Dropped (old files at `8488047`) | Draft | Fit with your port |
|---|---|---|---|
| water | `platform`, `attacker`, the re-strike loop in `Utility`, the "Access" and "Attacker" options, the dashboard's attacker view (`ui/view.py`); runs `*_kept`, `delayed_kept_human` | 1,631 lines, no TODOs | Extend: `Utility.observed_setback.start(work)` is what `strike_again` did |
| heat | `grid`, `contractor`, `ai`, `job`, the crews' halt and rework coupling, the "AI conduct and protection" options, the Delayed tier, most of `explore.ipynb`; 11 runs became 3 | 2,168 lines, all 11 runs | Extend: the attacker starts `incident.hold` and `extra`; a hold ends `until` the attacker stops |
| IV | `attacker` (access, alterations, ransomware), the foothold and credential race, the "Access" and "Attacker" options | 1,302 lines, 7 TODOs, 8 refusals | Restructure: `released_lot` and `initial_review` become states written by attacker events, reserves sized from an access input |
| cyber | The whole strategic model: leadership, the four expert groups, the surveillance and effects programs, `Stage`, `Pool`, `Channel`, planners and doctrine, `ai_tools`, `other_states`; 12 runs and 2 spreads | 3,490 lines, no TODOs, 76 unit refusals | A separate entry; `defensive_response` stays as a leaf |

Gaps to close, or to bring to the owner as questions:
- **Comparisons.** `versus` is gone from models, but the historical briefs lead with comparisons
  (hidden access against the human team; refuses against obeys). The publisher takes one
  `featured` pair (`tools/publish/brief.py`). Build the planned `[[comparison]]` table (R-A5-06),
  any number of pairs per brief, with its tests, before the packages.
- **A state that an option starts** needs its own `x_start` input (R-A5-04).
- **`since(e.outcome)`** has no form. Start a separate event in that branch and read it.
- **Distribution-valued spread edits** need explicit input fields, as Washington, DC's
  `uncertainty.*` does.
- **There is no event cancellation.** The heat job's cancellation becomes a guard.

Order: the comparison table, then water, heat, IV and cyber, smallest change first. For each
package:
- **Restore** every dropped part and every historical named run, option and sweep. Keep your later
  fixes: the Jamestown queue in the outage stage, the Washington refill branch, the Lehigh guard.
- **Compare** with `8488047` as you did for the kept parts: every named run and option, within the
  package's stated tolerances, using the paired scripts in `a5/`. Put any changed number on a list
  with its old value, new value and reason. If the language cannot express a part, park it, send
  the owner the smallest example, and continue.
- **Port the old tests for the restored parts:**
  - water's `test_family_properties` attacker cases;
  - heat's `test_reference.py` ledger cases and the refuse/obey brief tests;
  - IV's `test_adversary_acceptance.py`;
  - cyber's 178 tests in `scenarios/cyber_learning_loop/tests/`, with
    `vector_field(program, configuration)` (`napkin/dynamics/field.py`), `engine.study` in place of
    `evaluate_study`, and run names resolved to configurations.
- **Republish** the readings, dossiers and briefs from the full models. Restore the water
  dashboard's attacker view and the heat notebook.

## 2. Empty the dormant list, then delete the mechanism

Gate G3 requires an empty `tests/dormant.txt`. When it is empty, delete the file, the hook in
`conftest.py` (`pytest_ignore_collect`) and `selection.dormant`. Naming a dormant folder on the
command line collects nothing. Only a file named one by one bypasses the list, so check each
file by name. Dispositions from the review:

- **Already pass; just take them off the list:** `tests/test_tools_new_catalogue.py`,
  `tests/publish/test_limits.py`, and `tests/release/`, whose only file is `wheel_smoke.py`, which
  `tools/check.py` runs.
- **Port to the current APIs:**
  - `tests/evidence/test_catalogue.py`: read roles from `roles.toml` through `draw/style.py`
    (`roles_of`); split variant ids on `': '`; the dossier is `source-dossier.json`; read
    collections with `catalogue.locate(sid).collections()`.
  - `scenarios/tests/test_library_integrity.py`: `napkin.model.library.load_library`.
  - `tests/test_scenario_ownership.py`: the `readings` format.
  - `scenarios/tests/test_scenario_files.py` and `tests/test_scenario_scope.py`:
    `napkin.engine.configurations`, `napkin.model.language.parse`, and a helper module for
    `source_contract_files`.
  - `scenarios/tests/test_catalogue.py`: `engine.study`.
  - `scenarios/tests/test_assumption_review.py`: rewrite the dead `tests/owned.py` and
    `tests/build.py`, which import a `runtime.simulate` that no longer exists.
  - `tests/engine/test_distributions_deep.py`: `stream(...).random(n)` and `monte_carlo`; delete
    its Latin-sampling test with the docs that still describe Latin sampling
    (`docs/python-api.md`, `docs/engine.md`).
  - The current-format publish tests: `test_publish_drift`, `test_publish_selection`,
    `test_identity`, `test_owned_evidence`.
- **Return with the cyber model:** `scenarios/cyber_learning_loop/tests/`.
- **Delete as tests of removed features:**
  - `tests/evidence/test_scientific_spec.py`;
  - the historical publication-format tests in `tests/publish/` (`test_brief`,
    `test_brief_spreads`, `test_briefs`, `test_builder_robustness`, `test_display_metadata`,
    `test_evidence_relations`, `test_formatting`, `test_methods`, `test_pages`);
  - `scenarios/tests/test_limits.py` and `test_methods_links.py`.

  Keep one small test for spread sampling, which `tools/publish/__main__` still uses.
- **Delete or port the dead publisher modules** that no longer import (`pages.py`, `briefs.py`,
  `methods.py`, `assumptions.py` and `runs.py` in `tools/publish`), as the comparison table needs.
- **Delete `napkin/engine/runtime.py`** once nothing imports it.

## 3. Hand back

Hand back with:
- the comparison table of each package against `8488047`, and the changed-number list;
- the disposition of every dormant file;
- the owner's rulings you asked for;
- the regular and deep suites on macOS, and on Linux in a Docker container;
- `python -m tools.publish --check --jobs 4`;
- `python -B -m tools.check --all`.

Hand back the comparison table and water first, if it is ready before the rest. Water can then
be reviewed and merged while you work on heat, IV and cyber.
