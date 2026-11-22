# Contributing

This guide is for people who change `napkin` or its catalogue. It has five parts: the setup of a
checkout, the parts of the repository, the rules of a change, testing, and the style of the text that
readers see.

Read [README.md](README.md) first. Before you change the engine or a model, also read the
[language](docs/language.md), the [engine](docs/engine.md) and the
[modelling guide](docs/modeling-guide.md). Before you change the compiler, read
[the compiler](docs/compiler.md); before you add a feature to the language, read
[what to change for each kind of feature](docs/extending.md). Before you change the catalogue, read
[the catalogue's rules](scenarios/docs/catalogue.md) and the
[evidence guide](scenarios/docs/evidence/README.md).

## Set up a checkout

You need Python 3.12 or later. Make a virtual environment in the checkout. Install the locked
requirements, then install the package from the checkout in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

`requirements.lock` pins the libraries of the engine (numpy, scipy and jsonschema) and the tools of
the tests: pytest, pytest-xdist, Hypothesis, mpmath, PyYAML and ruff. The extra `dev` of
`pyproject.toml` names the same tools. The editable install gives you the `napkin` command, and a
change to `napkin/` takes effect at once.

The distribution is `napkin-sim`. It is not on PyPI, and the PyPI project `napkin` is a different
tool. Install napkin from a checkout or from a release wheel.

Run each command of this guide from the root of the checkout. The maintainer tools are in `tools/`,
and the installed package does not hold them: `python -m tools.check` finds them because the root is
the current folder. The option `-B` stops Python from writing bytecode files into the checkout.

Run an example to check the setup:

```console
$ napkin run examples/piano_tuners
base
                             at the end (8760 h)
  Tunings done in the year   2924 tunings
```

## The repository

| Path | What it holds |
| --- | --- |
| `napkin/` | The package, which is all that the wheel ships. The compiler of the language is in `model/`, the engine in `engine/`, the expression evaluator in `expressions.py` and the distributions in `distributions.py`. The schemas are in `schema/`, and the prelude's units in `std/units.json` |
| `napkin/cli.py`, `napkin/commands/` | The `napkin` command ([docs/cli.md](docs/cli.md)) |
| `napkin/draw/` | The picture of a model, which `napkin draw` gives ([docs/draw.md](docs/draw.md)) |
| `napkin/dynamics/` | The analysis of the dynamics of a run ([docs/python-api.md](docs/python-api.md#dynamics)) |
| `napkin/session.py`, `napkin/spread.py`, `napkin/store.py`, `napkin/package.py` | A played run (`Session`), the processes that sample a spread, the run store, and a package with its variants |
| `examples/` | Two small packages that a reader runs as written: `piano_tuners` and `reservoir` |
| `scenarios/` | The showcase catalogue: one folder for each package, and the catalogue's own folders `docs/`, `library/` and `tests/`. The publisher writes its index, `scenarios/README.md` |
| `tools/` | The maintainer tools: the check (`check.py`), the publisher (`publish/`), the comparison of two revisions (`compare.py`), the start of a new package (`new.py`), the locator of the catalogue (`catalogue.py`) and the evidence tools (`evidence/`) |
| `tests/` | The tests of the engine, by part (`model/`, `engine/`, `dynamics/`, `draw/`, `acceptance/`), and the tests of the maintainer tools (`publish/`, `evidence/`, `test_check.py` and others) |
| `docs/` | The docs of the engine only: the command, the Python API, the language, the engine, the picture and the modelling guide |

### Packages and variants

A model is a package: a folder with its main file, `model.scn`. In the catalogue, the folder
`scenarios/<package>/` gives the package its name. The name starts with a lowercase letter and has
only lowercase letters, digits and `_`, such as `iv_fluid_shortage`.

A variant of a package is the folder `variants/<name>/` of the package, with its own `model.scn`. Its
name is `<package>:<name>`, such as `water_controls_wipe:juneau`. Each other `.scn` file of the
package's folder is a module, which the main file and the variants can use
([language.md](docs/language.md), §2.12).

The folders `scenarios/docs/`, `scenarios/library/` and `scenarios/tests/` belong to the catalogue
as a whole. They are never packages. `scenarios/docs/` holds the catalogue's rules and guides,
`scenarios/library/` its shared vocabulary, and `scenarios/tests/` the catalogue-wide tests with
their shared support.

## The rules of a change

### Author each part in its own file

- Write a model in `scenarios/<package>/model.scn`, and a variant in its
  `scenarios/<package>/variants/<name>/model.scn`.
- Write what the briefs show in the folder's `brief.toml`: `attack`, `choice_group`, the run
  tables (`[[sweep]]`) and the spreads (`[[spread]]`). The distributions of a spread are an edit
  document in the folder's `spreads/`.
- Write the picture of the model in its `style.toml`, and its local units in its `units.json`.
- Write the shared units and the conventions of the project, as records, in
  `scenarios/library/vocabulary.json`. Each main file names it with `library "../library"`.
- Every model has the prelude's units (`napkin/std/units.json`). A composed unit, such as
  `tunings/tuner-year`, needs no entry.
- No file redefines a unit of the prelude. A local unit cannot use the name of a unit of the library.
- The publisher only renders. Put no value or rule of a model into it. Changes to the summaries use
  the data of the model that `tools/publish/pages.py` gives.
- Do not add a dependency on a temporary prototype or a spreadsheet: not in the code, the tests or
  the rendering.

### Start a scenario

Start a package of the catalogue with `python -B -m tools.new PACKAGE`. It writes the folder with each
file in its shape, and prints the list of what to write, in order. For a model outside the catalogue,
`napkin new DIR` writes a starter that compiles and runs as written.

After each change of a model, run `napkin compile scenarios/PACKAGE` and
`napkin run scenarios/PACKAGE`. They give each diagnostic with its file and line, or the outcomes of
each run, in seconds. `napkin fmt scenarios/PACKAGE` formats the model files; the tests require that
each committed model file keeps its format.

An AI case follows [the AI operations guide](scenarios/docs/ai-operations.md). A realistic pathway of a
human team matches its AI pathway, and its story names the recovery measures that lead the comparison.

### Give each value its basis

- Each coefficient and each meaningful choice of a model has an explicit basis. The basis is a
  source, an identity, a convention or an assumption that nobody has reviewed.
- Record the basis, the units, the locator in the source, the applicability and the range of inputs
  with each quantitative choice.
- Keep the applicability and the uncertainty of a source. A bound that you choose for a scenario is
  not a measured interval.
- Keep each historical observation in the population, the geography and the price year that its
  source reports. When a calculation uses another population or exposure, record the transfer
  explicitly.
- Units normalize to the units of execution. Distinguish physical counts, episodes, patients and
  the price years of a currency. Do not add a manual conversion that the units already make.
- Evidence records, numerical validity and an estimated outcome are three different things. An
  outcome that a model does not estimate is not zero. A numerical failure makes the run invalid.

### Write evidence through the evidence tools

`tools.evidence.integrate` is the only writer of claims and sources. Each evidence pack writes one
folder: the folder of a package or of a variant. A pack never changes the records of another folder.
Do not edit claims or sources with a script of your own.

`python -B -m tools.evidence.adopt --from SOURCE --to DESTINATION --id RECORD` shows the copy of a
record and its dependencies into another folder. Add `--write` to apply it through the same validated
writer. The copies stay independent. The [evidence guide](scenarios/docs/evidence/README.md) gives
the details.

### Keep the language and the engine sound

- Version 0.0.1 of the language and of the schemas is a fresh start. There is no reader or schema of
  an earlier version, and no layer for compatibility. When a format changes, change every consumer
  and every fixture in the same change.
- Algebraic expressions stay on a list of allowed forms, and each one has a type. A new class of
  crossing needs a structural argument for its detection, not only a SciPy simulation that passes.
- An edit is a transaction across every declared run: the engine admits it in all of them, or in
  none. The one exception is a study of named runs (`evaluate_study(…, runs=…)`). It admits the edits
  that hold in those runs.
- The engine checks a combination of options that no run makes only when a caller asks for it
  (`model.combination(run, options)`). The same edits apply to it.
- Keep one implementation of each validation.
- Freeze each acceptance expectation and its independent inputs. Do not take an expectation from a
  production trace. Do not weaken one to make a regression pass.

### Keep the identity of a model

A saved input binds to the `model_hash` of its model. The model's identity covers the meaning of
each file of the model: the main file, a variant's file and the modules that they use. It also
covers the units that the model uses, the records that it reaches and the version of the language
(`LANGUAGE_VERSION`). It covers no name, path, list of variants, unused unit or record, and no
version of the package. A change to the code keeps every `model_hash`.

The implementation's identity, `implementation_hash`, covers the engine, the compiler of the model,
the expression evaluator and the compiler's schemas (`napkin/schema/`). Reports, jobs and caches
carry it too. Saved edits and the edit documents of spreads use the model's identity only: the engine
refuses a document of another revision of the model.

A change to a file of `napkin/engine/`, `napkin/model/` or `napkin/schema/`, or to
`napkin/expressions.py`, changes `implementation_hash`. The run store keys each run by a digest of
the code that a simulation runs ([engine.md](docs/engine.md#the-run-store)). That code includes
`napkin/distributions.py` and `napkin/__init__.py`. A change to that code makes each stored run a
miss, so the next check simulates every run again.

### Keep what a scenario owns in its folder

- Keep a scenario's names, its specific assertions, its fixtures, its oracle input maps and its prose
  in the folder that owns it. In a package with variants, put what holds for every variant in the
  package's folder.
- Central tests can discover the scenarios, but they never keep a list of real packages. Their
  synthetic packages use the reserved IDs (`SC` and two digits, such as `SC97`) or generic names.
- Generated catalogues, dossiers, manifests and the changelog can name scenarios.
- Before you land a change, search outside `scenarios/` for whole words that name a package of the
  catalogue or a retired ID: SC10, SC41, SC43, SC43_<place> and SC45. Report each hit with its
  reason. This is a manual review: do not add a test that guards against the hits.

### Describe a pull request

In a pull request, describe what started the change and the behavior that results. Name the
scenarios that it affects and the checks that you ran. Discuss a correction of the evidence with the
locator in its original source and the input or outcome that it affects.

## Testing

### Choose the check

Use the smallest check that covers the change. A correction of a test fixture calls for that test's
check again. It does not make the other tests that passed invalid, so do not start the whole suite
again after each fix. A refresh of the committed summaries is a separate task. It is not part of
each edit.

| Command | What it runs |
| --- | --- |
| `python -B -m tools.check --tests tests/test_check.py` | Lint and the named test file. Repeat `--tests` for more paths or node IDs |
| `python -B -m tools.check --scenario ID` | Lint, the tests of the scenario's folders, the central contracts of the scenario, and the comparison of its committed summaries |
| `python -B -m tools.check --scenario ID --deep` | The same, with the deep tests of that selection. It replays no stored run and runs none of the exhaustive central tests |
| `python -B -m tools.check --scenario ID --skip-summaries` | The same, without the comparison of the summaries. Use it when the change cannot change a rendered result |
| `python -B -m tools.check --all` | Lint, every test that is not deep, and the comparison of every committed summary |
| `python -B -m tools.check --all --deep` | The full check: every test, the exhaustive tests of admission, the replay of three stored runs, and every summary |
| `python -B -m tools.check --release` | The check of a release, from an empty run store, with the wheel ([Releasing](#releasing)) |

An ID names a package (`iv_fluid_shortage`), a variant (`water_controls_wipe:juneau`) or a package
with variants. A package with variants selects each of its variants. Repeat `--scenario` for more
scenarios.

Add `--plan` to see the scope and the stages of a check without running them:

```console
$ python -B -m tools.check --scenario water_controls_wipe:juneau --plan
Scope: water_controls_wipe:juneau (named with --scenario)
Stages: Lint, Python tests, Committed summaries
Tests: owned scenario/family tests and marked scenario contracts; unrelated central tests excluded
Pytest workers: 0
```

The full check and the release check can take a long time. Do not start them during a focused
change, or before you know how much time you have. If a check would take more time than the user
gave you, say so before you start it.

### What the check selects

Without `--tests`, `--scenario`, `--all` or `--release`, the check reads the changes. These are the
files that differ from the merge base of HEAD with `main` (or `origin/main`): committed, staged,
unstaged and new files.

- A change in a scenario's folder selects the scenarios that read that folder. A change in a folder
  of modules selects each scenario that uses them.
- A change in the written docs only runs lint. The written docs are the Markdown files at the root,
  in `docs/` and in `scenarios/docs/`, and the index `scenarios/README.md`. Data in a folder of docs,
  such as the source manifest, is not documentation.
- Any other change, an unknown diff or no diff stops the check (exit 2). Then choose `--tests`,
  `--scenario` or `--all`. The check never starts the whole repository by itself.

`--tests` takes exact pytest paths or node IDs, and runs no publication work. It cannot go with
`--all`. Add `--scenario` when the test file must take its scenario parameters from those scenarios
only. A path that does not exist fails at once; it never falls back to the full suite.

`--skip-summaries` is explicit, and the check reports it. A release check does not allow it.

### The stages of a check

1. **Release notes** (`--release` only): CHANGELOG.md has notes for the version of the package, and
   a `v*` tag at HEAD, if there is one, names that version.
2. **Lint**: `ruff check` and `ruff format --check` on `napkin`, `tools`, `tests`, `scenarios` and
   `conftest.py`.
3. **Python tests**: pytest stops at the first failed test, and lists each test that takes more
   than 10 seconds.
4. **Stored runs** (`--all --deep` and `--release`): it simulates three stored runs again in a
   separate process. It compares them with the store, bit for bit.
5. **Committed summaries**: `tools.publish --check` on the selected scenarios, or on the whole
   catalogue. A focused check calls the publisher once, for its selection only: it does not first
   render the whole catalogue. The aggregate builders run only in the full check.
6. **Wheel** (`--release` only): `check.wheel()` builds the wheel and tests it outside the checkout.

A focused check, and a check with `--tests`, runs the tests in one process (`--test-jobs 0`), so the
tests can share each compiled model. A focused check also uses one publication worker. Use
`--test-jobs N` and `--publish-jobs N` when more processes help and the memory allows it. The full check uses pytest's automatic number of workers
and four publication workers.

The run store keeps simulations. It does **not** keep compiled models, the admission of inputs or the
rendered pages. So a full check is not fast when the store is warm. The read-only contracts of the
scenarios share compiled models, but the tests of the compiler and the mutation tests compile their
own inputs. A focused check clears the registered study results after each test, which limits the
memory; it keeps the compiled models. Plain pytest keeps the study results for the whole session.

The engine, language and acceptance tests (`tests/engine/`, `tests/model/`, `tests/acceptance/`)
always simulate, because they test the simulation itself. Every other test takes its runs from the
run store (the root `conftest.py`). At the end, the check says how many runs it simulated. The run
store is `.cache/runs` in the checkout. `NAPKIN_STORE=off` turns it off, and `NAPKIN_STORE=DIR` uses
another folder.

### Run pytest yourself

`pytest` collects `tests/` and `scenarios/` with `--import-mode=importlib`, and leaves out the deep
tests. `pytest -m deep` runs only the deep tests, and `pytest -m "deep or not deep"` runs both.

`pytest --scenario ID --focused` applies the filter of a focused check: the tests of the scenario's
folders and the central tests marked `@pytest.mark.scenario_contract`. Without `--focused`,
`--scenario` only narrows the scenario parameters and the scenario folders, and the central unit
tests still run. To test a change of central code, give the test path without `--focused`.

The renderers of the whole catalogue and the exhaustive matrices of admission stay in the full
check.

### The kinds of test

The **core tests** prove that the software works:

- The catalogue (`scenarios/tests/test_catalogue.py`): each model file of the catalogue is a case
  of the catalogue, and it compiles and runs its default study. Its standard runs keep the orders of their local
  expectations (`tests/expected-orders.json`), and the report is finite. Each example edit set in a
  package's `edits/` folder, if there is one, runs and keeps the orders that it binds.
- The files of the catalogue (`scenarios/tests/test_scenario_files.py`): every committed model file,
  a module included, reads and keeps its format, and every scenario builds. Each `style.toml` and
  `brief.toml` reads and names what its model declares, and the model admits the edit document of
  each spread.
- The language acceptance test (`tests/acceptance/test_every_construct.py`) compiles a package,
  a module, and a variant that exercise the language. The test checks formatting, event order,
  and values worked out from the fixture's equations.
- The compiler: one test for each class of compile diagnostic (`tests/model/test_compile.py`), and
  the evidence index and trail (`tests/evidence/test_index.py`, `tests/engine/test_evidence_trail.py`).
- The rules of the language, each on a small model with a closed form. For example:
  - the order of one moment (`tests/engine/test_moment.py`);
  - an event that fires again (`tests/engine/test_rearm.py`);
  - the chances of the outcomes and their draws in a study (`tests/engine/test_chance.py`);
  - what an actor sees (`tests/model/test_sight.py`);
  - a played run (`tests/engine/test_play.py`).
- A scenario and its modules build and run as the same model written in one file
  (`tests/model/test_modules.py`). A template's name is the list of its instances
  (`tests/model/test_template_lists.py`).
- The mathematics of the engine, on small synthetic models with closed forms (`tests/engine/`), and of
  the dynamics (`tests/dynamics/`).
- The `napkin` command, on fake packages (`tests/test_cli.py`); packages and their variants
  (`tests/test_package.py`); the public API (`tests/test_api.py`); the examples
  (`tests/test_examples.py`); and the run store (`tests/test_store.py`).
- The picture (`tests/draw/`): its relations, the properties of its layout, its SVG and the checks
  of the stylesheet.
- A played run (`tests/test_session.py`): a finished `Session` gives the report of
  `evaluate_study(play=…)`, and a log replays the same run.
- The evidence library, the publication builders, the formatting of the text and the briefs
  (`tests/evidence/`, `tests/publish/`), and the other maintainer tools.
- The sampling pool (`tests/test_spread.py`).

The **deep tests** (`pytest -m deep`, or `--deep`) check details:

- The acceptance tests of the damage and recovery accounting, against reference oracles. Their shared
  support is in `scenarios/tests/`, and each package's own oracles are in its `tests/`. An oracle
  reads the inputs of a run by its own names, and each `tests/oracle-inputs.json` maps those names
  to the inputs of the model (`entity.value`).
- Slower checks of the engine and of the evidence, such as `tests/engine/test_distributions_deep.py`.

The **wheel smoke test** (`tests/release/wheel_smoke.py`) runs only in a release check. It installs
the wheel in a fresh environment outside the checkout, and checks five things:

1. The wheel ships the engine only, with no catalogue, library or tool.
2. `napkin new`, then `napkin run`, on a starter with and without variants.
3. `napkin compile`, `run`, `sample` and `draw` on each example, and `napkin play` on each example
   that has an actor.
4. `napkin fmt --check` on the starters, the examples and each package of the catalogue.
5. `napkin compile` on each package of the catalogue, which finds the library through its own
   `library "../library"` line.

### Test rules

- Use independent mathematics, properties and substantive counterexamples. Agreement between two
  solvers is not an oracle.
- Never pin authored wording. When a test needs a text, read it from the scenario or the library.
- Never compute an expectation by hand from an authored default input. An expected value comes from
  independent mathematics: closed forms, the shared conventions in `scenarios/tests/oracle_common.py`,
  and the owned oracles in `scenarios/<package>/tests/`. It works on inputs that the test reads from
  the model or applies as explicit edits. An expected value can also come from a property:
  conservation, partitions, bounds, finiteness, or the expected orders of the standard runs.
- Never copy a trace of the engine into an expectation.
- Keep each core unit test within about 10 seconds. Make a slower test smaller, or mark it `deep`.
- The root `conftest.py` rewrites the assertions of each test module of the catalogue, its helpers
  included: in a package's `tests/`, in a variant's and in `scenarios/tests/`. So no scenario has a
  conftest for that. A scenario's `tests/conftest.py` holds only fixtures of its own.
- A bug fix comes with a test that fails before the fix.

### Testing distributions

The tests of distributions and of Monte Carlo studies are thorough and fast: all of them together take
a few seconds. They follow these rules:

- **The mathematics without sampling.** A distribution is its quantile function. At fixed
  probabilities from 1e-9 to 1 - 1e-9, each family's quantiles are within a few units in the last
  place of the true quantile. The family's own cdf, written in mpmath, gives the true quantile
  (`tests/engine/distribution_oracles.py`). The mean and the variance of a fine grid of quantiles
  match the closed forms, which finds a wrong parameterization.
- **An exact answer for each sample.** A study of a tiny model has an outcome with a closed form in
  the drawn inputs. The test checks each of its 8 to 64 samples against that closed form, with no
  statistical tolerance.
- **Deterministic bounds from Latin strata.** With one sample in each stratum, the mean and the median
  of a monotone outcome have bounds that hold for every seed.
- **Seeded statistics only for the randomness itself**: the uniform numbers, and the shares of
  bernoulli and categorical draws. These tests use vectorized draws, and thresholds from the DKW and
  Hoeffding bounds at a probability of false failure of 1e-9. The seeds are fixed.
- **Exact structural properties.** One seed gives one result. Sample k does not depend on the number
  of samples. Another uncertain value leaves the draws of the others alone. Copies draw their own
  values. An outcome that reads no uncertain value is the same in every sample. A central run at the
  old point values is the point run, bit for bit.
- **Properties** with Hypothesis, `derandomize=True`: quantiles rise with u, stay inside the support
  and invert the cdf.
- **The sampling pool** (`napkin/spread.py`). One test runs the samples of a tiny model in a pool of
  two processes. It compares the result with the same study in one process, bit for bit. No core test
  samples a scenario of the catalogue. The texts of the distributions are in
  `tests/fixtures/distribution-texts.json`.

### Tests and the folders of the catalogue

Each scenario owns its specific tests and its frozen inputs. The shared mathematics and the
parameterizations across scenarios stay central.

Central tests can loop over the scenario folders that they discover. Assertions, expected orders,
fixtures and oracle input maps that name a scenario belong to its folder. Synthetic central test data
uses the reserved IDs, and no central list registers real cases. A synthetic package with variants
(`write_family` in `tests/owned.py`) uses the same IDs: the main file and the modules in `SC97/`, and
the variants in `SC97/variants/<name>/`.

In a package, the assertions that hold for every variant go in the package's `tests/`. The
assertions of one variant go in its own folder. `pytest --scenario SC97:east` also collects the tests
of the package's folder `SC97/`, because the model of `SC97:east` reads the files of that folder.
`--scenario SC97` selects the package and each of its variants. The locator of the catalogue
(`tools/catalogue.py`) gives these readers. After a move, compare the collected node IDs with those
before it.

### Refactor comparisons

A refactor keeps the numerical results bit for bit, in the same interpreter, dependencies and
numerical environment. First, the compiled order of quantities, rules and flows must be identical.
Then compare the ordered values, states, events and evidence of each standard run and each declared
sweep. An event comparison keeps the round and the order within each moment: a sort by time only
loses that order. Also check the admission and the rejection of edits, their origins and each
combination of options that is necessary. The independent oracles stay the tests of mathematical
correctness. Agreement between two revisions tests only that the change keeps the results.

Only the revision hashes that you list, and the evidence aliases or source locations that you map,
can change. Apply each evidence mapping to the traces as well as to the indexes and the reports. A
location that changes without a mapping fails. A comparison must find a changed floating-point bit,
two simultaneous steps in the opposite order, and an evidence location that changed without a
mapping.

`python -B -m tools.compare` applies this contract (`tools/compare.py`). It puts the base in a
temporary git worktree: by default the merge base with main, or `--base REV`. Each side runs the
capture code of its own revision with its own package. For each scenario it records:

- the compiled model;
- the compiled order by names only: for each structure, the names of each section in their order, the
  rules in the order of one moment, the kind of each rule's trigger, the order in which the formulas
  are computed, and the names of the parts that the structure leaves out;
- the pages;
- the default study: its admission, its diagnostics and its report;
- a record of each run's trajectory: a digest of each numeric part, and the units that the run names;
- the numbers of each run: the quantities and the discrete values after each step, in the order of
  the steps, and the same with the formulas at each sixteenth of the run's length;
- the declared sweeps (`[[sweep]]` in `brief.toml`);
- the example edit sets, if the scenario has any.

The order and the numbers hold names and numbers only: no expression, and no field of an object of
the engine. So they compare when two revisions keep a model or a run in different forms, where the
compiled model and a trajectory's record cannot.

Beside the catalogue, the comparison captures each example (`examples/<name>/`, as the owner
`examples.<name>`) and the acceptance fixture (as `acceptance.F5`): the compiled model, its order and
the default study of each. `--scenario` takes these owners too.

Both sides first take a canonical form: no source positions, each event rank as its order, no
`controls` in the pages, and the gate and the times of each trigger written in one way. A capture failure on either side fails the comparison. Then the comparison
compares the records exactly, and prints the first differences of each. Only `implementation_hash`
is left out.

- `--allow FILE` names what else can change:
  - `"ignore"`: keys to leave out;
  - `"ignore_paths"`: single places, such as `default/report/runs/*/peaks/*/t`;
  - `"map"`: evidence locations that moved;
  - `"reporting": "final"`: compare only the final reporting point of each run.
- `--rename FILE` reads the base's owners and paths as new ones, whole paths only.
- `--keep DIR` saves the records of both sides, with the machine that they ran on.
- `--baseline DIR` compares the working tree with the saved base side (`DIR/base`), and captures no
  base. With `--scenario`, it compares only those scenarios. It refuses the records of another
  machine, whose last bits can differ, and a `--keep` folder that overlaps the baseline.
- `--jobs N` sets the number of processes for each side.

Both sides take their runs from the run store. So a refactor that keeps every resolved run compares
without a simulation; compilation and rendering still take time. No test reads the records of the
comparison, and no runtime, renderer or configuration uses it.

### Comparisons of a change of the numerical core

A change of the numerical core does not keep the bits: another solver, a Jacobian from the formulas,
another arithmetic of the rates. The results before such a change are not the truth, and the new
results can be the better ones. So this comparison does one thing: it finds each place where the
results changed. The independent oracles stay the tests of correctness.
`python -B -m tools.compare --tolerance` applies it. It is for a change that the ledger marks as a
change of the numerical core, and for no other change: a refactor keeps the bits.

These stay identical: the compiled model, its order and the pages; the admission or the rejection of
each edit, with its code; each status of an outcome; each warning and each error, by its code; each
step of the trace, with its rule, its event, its outcome and its place in its moment; the health of
each entity; the evidence trail.

The numbers of the simulation are sorted:

| Class | What it is | What it needs |
| --- | --- | --- |
| Within tolerance | Two values differ by no more than their tolerance (below). A time that cannot shift differs by no more than 1e-8 h. | A count. |
| A moment that shifted | The time of a moment that a root can give differs by no more than one part in a million of the larger of one hour and the time. A moment counts once, however many steps and values repeat its time. | A count, and the largest shift. |
| A discrete difference | Another event, outcome, order, moment, status, warning or tolerance of a quantity. | Each one is listed, and explained before the change lands. |
| Beyond tolerance | A value or a time that differs by more than its tolerance, and a number that is not finite (two equal infinities are the same value). | Each one is listed, and explained before the change lands. |

The tolerance of a value:

- A quantity: one part in a million of the larger value, plus an absolute term. The absolute term is
  1,000 absolute tolerances of the quantity in the base run, but no more than one part in a thousand
  of the quantity's largest value in the base run, and no less than one absolute tolerance. The
  absolute tolerance follows the authored size of a quantity, which can be far above its values:
  without the second bound, such a quantity could change by a large part of its value with no word.
- An outcome or a formula, which has no tolerance of its own: one part in a million of the larger
  value, plus one part in a million of its largest value in the base run, plus 1e-9. The last term lets
  an outcome that is zero on one side differ by a residue of roundoff on the other.

The time of a step can shift only when a root can give it. That is so when both of these hold in the
base run: the model writes no time for the step, and a numerical segment starts before it. The model
writes a time when exact arithmetic on the inputs gives it:

- the time of a timer on the inputs, and of each timer that waits on an event whose own time is
  written. When a trigger has several times, its largest time counts, and each time that is as near
  to the largest as a root can move a time must be exact;
- the time of a firing that waits, when its rule triggered at a written time and its delay was exact
  then. A delay that the rule draws is exact, and so is a delay that reads the time of a written
  moment.

Every step of that moment takes the written time. So a timer cannot shift, whatever the solver does
around it, and neither can a chain of timers that starts at one; no time shifts in a run of closed
forms only. The time of a crossing that a root gives is not written, and neither is a time that waits
on it, that reads a quantity that a flow moves, or that reads the run's past (`delayed`): such a time
carries the accuracy of what it reads.

The base side gives each tolerance and each written time. The side under test cannot widen what judges
it: its own tolerances, when they differ from the base's, are a discrete difference.

An explanation says which side is right, and shows it with something that depends on neither side's
engine alone: a closed form, an independent calculation, or the same run with a much tighter tolerance
of the solver, which both sides must approach. One of three things follows. A near-tie in the base run
(two moments within the tolerance of a shift of each other, or a guard within its tolerance of its
value) is an explanation when it is shown. A new result that is nearer to the reference stands.
A new result that is further from it is a defect.

The record of a trajectory's parts, the list of the numerical segments and the notes of the numerics
are left out of this comparison or only counted: they say how one engine cut the run. A different
number of notes counts as one difference within tolerance. The time of a peak takes the tolerance of
a time that a root gives and is not counted.

The comparison holds the default study, the sweeps and the example edit sets of each scenario, each
example and the acceptance fixture. It holds no Monte Carlo sample of a spread and no played run.

### The committed summaries

The catalogue publisher renders each runnable entry’s `results/brief.md`, `results/readings.md`
and `results/source-dossier.json`. The whole-catalogue command also renders the active source
manifest. A scoped check or refresh covers only its selected package or variants.

```sh
python -B -m tools.publish --check --scenario ID
python -B -m tools.publish --write --scenario ID --jobs 1
```

`--only briefs`, `--only readings` and `--only dossier` select individual formats. Use `--only manifest` for the
whole-catalogue source manifest. The regular checker uses these current publications.
`tools.check --spreads` and the current release check also execute the declared sample studies.
The [historical briefs](https://github.com/jfeiglin/napkin/tree/8488047/scenarios) accompany the earlier catalogue.
[Current publication commands and coverage](tools/publish/README.md)

### Releasing

1. Set the version in `pyproject.toml` and in `CITATION.cff`. The package reads its version from its
   metadata (`napkin.__version__`). Add the notes of the release under `## X.Y.Z` in CHANGELOG.md.
2. Run `python -B -m tools.check --release`. It checks that CHANGELOG.md has notes for the version,
   and that a `v*` tag at HEAD, if there is one, names that version. Then it runs the full check with
   `--deep` from an empty run store, so the release never depends on stored runs. Last, it builds the
   wheel and checks it in a fresh environment outside the checkout (`tests/release/wheel_smoke.py`).
3. Tag `vX.Y.Z`, and push the tag. No workflow runs on GitHub.

`check.wheel()` in `tools/check.py` builds the wheel with
`pip wheel --no-build-isolation --no-deps`. A build in the tree leaves `build/` and `*.egg-info`
behind, and a leftover `build/` goes into the next wheel. So `check.wheel()` deletes both before the
build and again after it. It builds into a temporary folder, which it deletes after the smoke test.
To keep a wheel for a release, build it the same way into `dist/`. Delete `build/` and `*.egg-info`
before and after the build:

```bash
rm -rf build *.egg-info
python -m pip wheel --no-build-isolation --no-deps . --wheel-dir dist
rm -rf build *.egg-info
```

## Writing style

The text that readers see follows ASD-STE100 Simplified Technical English (STE), adapted for scenario
text. That covers everything that a reader sees in the briefs and in the methods:

- the titles and the summaries of the scenarios;
- the AI operation;
- the labels of the responses, the attacks and the pathways;
- the labels of the outcomes and the inputs;
- the labels of the systems and the statuses;
- the event text and the stories;
- the notes that say where each value comes from.

The aim is text that a reader understands the first time, in one meaning only.

### Words

1. **Technical names are correct.** Use a technical name when specialists use it: SCADA, IV fluid,
   clearinghouse, circuit breaker, ransomware, terminal, heatstroke, thrombectomy, value added,
   person-hours. Do not make new terms, and do not join words into a name that nobody uses
   ("delegated border-zone blackout").
2. **One word, one meaning.** Use the same word for the same thing everywhere (see the
   [glossary](#glossary)).
3. **No model words.** Do not write binding, branch, configuration, variant, overlay, scope, state,
   flag, cohort, witness, package, preset, ledger, vintage, partition, footprint, inventory (for
   people or services), accounting window, horizon, metric or dimension. Do not use declared,
   executed, authored, finite, disjoint, conserved, coupled or bookkeeping to describe the model.
   These are names in the model, not in the world. Say what they mean: "after 15 days", "the
   people the study follows", "each person is counted once".
4. **Say who chose a value.** Keep the status of every value: reported by a source, taken from a
   source and applied here, true by definition, or assumed for this scenario. Write "the scenario
   assumes", "chosen for this scenario" or "reported by the study", not a bare "selected". A range
   that a reader can explore is not a measured interval; say so.
5. **Simple verb forms.** Use the present tense for what happens in a scenario. Do not use a word
   ending in -ing as a noun or an adjective ("the AI keeps its access", not "continuing access"),
   unless it is part of a technical name (cooling, heating, shipping).

### Noun clusters

6. **No more than three nouns together.** Break a longer cluster with a preposition or a short
   clause: "time until crews start repairs", not "repair crew start delay time".

### Sentences

7. **Short descriptive sentences.** A sentence has no more than 25 words and one idea. Start with
   the most important information.
8. **Active voice.** Say who does the action: "Crews restore the circuits", not "The circuits are
   restored".
9. **Keep the small words.** Keep "the", "a", "of" and "to". Do not write telegraph text.
10. **One topic per paragraph.** A paragraph has no more than six sentences.

### Labels and statuses

11. **A label names one thing in a short noun phrase.** For example: "Deaths", "Hours without
    electricity", "Time until repair work starts".
12. **A status is a short, plain statement of the condition.** For example: "Power off", "Crews
    repair the circuits", "Access removed".
13. **Every quantity has its unit.** Do not show a yes/no condition as a percentage: make a yes/no
    state a bool (`state: bool`), and it reads Yes or No. An event card shows only the states that
    have a label; a state without a label stays inside the model.
14. **A pathway label names the defender response, then the attack.** It is the response label and
    the attack label, joined by " · ". For example: "Delayed response · AI keeps access".
15. **Prose never shows a record ID.** The methods tables and the evidence records keep the IDs.

### Glossary

| Use | For | Do not use |
| --- | --- | --- |
| AI agent, the AI | The AI system that makes the attack | delegated AI, AI execution |
| human team | The people who make the matched attack in the comparison pathway | human operator team |
| attacker | The AI agent or the human team, when a sentence is true for both | intruder, adversary |
| defender response | How fast and how well the defenders act: early, delayed, limited | preset, response profile |
| attack | What the attacker does and how long it keeps access; the sidebar shows it with its conditions | configuration, package |
| pathway | One defender response together with one attack | variant, branch |
| outcome | A calculated result: deaths, serious casualties, economic loss, hours without a service | metric, dimension, endpoint |
| deaths | People who die because of the incident, above the deaths that occur without it | fatalities, excess fatalities |
| serious casualties | People who die or are seriously hurt, each person counted once | |
| economic loss | Cost in US dollars at 2025 prices | USD2025, damage |
| the people the study follows | The people whose harm the scenario counts | cohort, exposure population |

The three headline outcomes have the same labels in every scenario: "Deaths", "Serious casualties,
including deaths" and "Economic loss".

### Examples

| Before | After |
| --- | --- |
| Delegated border-zone blackout in a heat wave | Blackout in a heat wave, caused by a contractor's AI agent |
| Access held on the target's networks under the approved operation | The operation's access to the target's networks |
| Delayed enforcement | Delayed response |
| No health binding | Not tracked |
| Contractor operators: Disclosure: 100% | Record passed on to the utility: Yes |
| Unique serious people per qualifying emergency visit | People seriously hurt for each emergency visit |
| State and transfer bookkeeping; coefficients carry their own bases. | The model counts this quantity. Each value that changes it has its own source. |

When you change the text that readers see, keep its meaning exactly. Change no number, unit, ID or
expression, and do not add detail of the attack. Then refresh the committed summaries of the
scenarios that you changed: `python -B -m tools.publish --write --scenario ID --jobs 1`.
