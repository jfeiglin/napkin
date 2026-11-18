# Brief S0-S: the switch of the first slice

Read `briefs/COMMON-B.md` first. State file: `scratch/rewrite/b1/s0-switch/STATE.md`.

## Why

The two tracks of S0 are merged. The new front end lowers the subset of the slice to a program
(`napkin.model.compile.load_scenario`), and the engine runs programs only (`napkin.engine.run`,
`napkin.engine.read`). From source, `examples/piano_tuners/model.scn` already runs: 2,923.5
tunings done in a year. What is left is the switch: the command line on the new path, the old
compiler deleted, and the small changes to the contract that the two tracks asked for.

## You own

`napkin/cli.py`, `napkin/commands/run.py`, `fmt.py`, `compile.py` and `common.py` (and
`commands/__init__.py`), `napkin/model/__init__.py`, the old compiler modules named below,
`napkin/program/` (for the changes below only), the engine's reader of formulas, new tests in
`tests/commands/` (new folder), and `scratch/rewrite/b1/s0-switch/`. Do not change the parser, the
declared model or the lowering of the front end, nor the engine beyond the items below.

## What to do

1. **Delete the old compiler** that nothing live imports any more: `napkin/model/hybrid.py`,
   `structure.py`, `lower/`, `resolved.py`, `meaning.py` and `model.py`. Keep `ir.py`, `runs.py`,
   `views.py`, `uncertain.py` and `analysis/` for the stages that port them. First prove what
   imports what: every module that a live test, `napkin.engine.run` or `load_scenario` loads must
   still import. Remove `Model` from the lazy names of `napkin/model/__init__.py`.
2. **The command line on the new path**, as small as the slice allows:
   - `napkin run MODEL [--at TIMES] [--value PATHS] [--json]`: compile, run in the model's default
     configuration, and print the values of the named paths at the times. With no `--value`, every
     named value; with no `--at`, the start and the horizon. Errors print their code, file, line and
     column and exit with status 1.
   - `napkin fmt FILES [--check]`: the new formatter.
   - `napkin compile MODEL [--json]`: the diagnostics, or a short summary of the program.
   - The other commands (`play`, `sample`, `draw`, `new`) print that a later stage brings them back,
     and exit with status 2. `napkin --help` and `napkin --version` work and load no engine.
3. **The contract changes that the tracks asked for** (`scratch/rewrite/b1/s0-front/STATE.md`,
   `scratch/rewrite/b1/s0-engine/STATE.md`):
   - `build.py`: a public builder for a call (`abs`, `exp`, `sqrt`, `min`, `max` and the rest of the
     closed list of `napkin/core/ops.py`), replacing `build._call` in the tests; document `X(node,
     reads)` as the way to wrap any other node (chains, n-ary `and` and `or`).
   - The rate unit of a flow whose store is a plain number: one spelling that the front end, the
     builders and the engine all read the same way (the front end writes `1/h`; the builders write
     `/h`, which does not compose).
   - Document in `refs.py` that a draw carries a temporary site that `finish()` replaces, and that the
     second parameter of `lognormal` (`gsd`) is a plain number although the tuple has one unit.
   - `record.Piece`: give curved pieces their own field (the engine passes a `Curve` object as the
     rate today), so that a reader of the record needs no knowledge of the engine.
   - A configuration `Quantity` may use a unit of the library, not only of the program's table.
   - The engine honours `Numerics.crossing` (it keeps a fixed 1e-8 today).
   - Check how `napkin.engine.read` gives a formula: the engine fits formulas after the run from the
     histories that they read. A read of a formula at a time must equal the formula evaluated on
     the recorded values at that time, to their tolerance. If the fit can lose more, make `read`
     evaluate the formula there instead.
4. **Tests** (`tests/commands/`): `napkin run` on `examples/piano_tuners` gives the closed form: the
   median of `pert(600, 1000, 1200)` tunings per tuner-year, times 3 tuners and 1 year, which is
   under the 5,000 tunings needed (work the median out independently, for example with `mpmath`);
   `napkin run` on a source text of the tank of the spec gives 3 L/h until 2 h 40 min and 0 L in the
   tank after; `napkin fmt --check` passes on the example and fails on a badly formatted copy;
   `napkin compile` reports a diagnostic with its place; `napkin --help` works; a refused command
   exits with status 2.

## Checks

At the end, once: `tests/commands tests/language tests/program tests/reference tests/core`, the
engine files that are not on `tests/dormant.txt`, and `ruff check` and `ruff format --check` on
`napkin tools tests scenarios conftest.py`. Then a run of the whole `tests` folder, which the
dormant list keeps to live tests: list every failure, and either mend it or say why it belongs on
the dormant list.

## Exit

Your last message: what was deleted (lines by module), the commands and what they print, each
contract change, the test counts, and any test that you put on the dormant list, with its reason.
