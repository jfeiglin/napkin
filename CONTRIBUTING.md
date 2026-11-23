# Contributing

This guide is for people who change `napkin`, its examples or its catalogue. It has eight parts: the
setup of a checkout, the repository, the rules of a change, testing, speed, the publisher, the
release, and the writing style.

Read [README.md](README.md) and [docs/README.md](docs/README.md) first. Before you change the engine,
read [the engine](docs/engine/README.md) and [the design](docs/design/README.md). Before you change
the compiler, read [the compiler](docs/compiler.md). Before you add a feature, read
[what to change for each kind of feature](docs/extending.md). Before you change the catalogue, read
[the rules of the catalogue](scenarios/docs/catalogue.md) and
[the evidence guide](scenarios/docs/evidence/README.md). The words **model**, **package**, **run**,
**record**, **method** and the other terms have the meanings that
[the terms](docs/language/README.md#terms) give.

## Prepare a checkout

You need Python 3.12 or later. Do these steps in the root of the checkout:

1. Make a virtual environment: `python3 -m venv .venv`.
2. Activate it: `. .venv/bin/activate`.
3. Install the locked requirements: `python -m pip install -r requirements.lock`.
4. Install the checkout in editable mode: `python -m pip install --no-deps -e .`.

`requirements.lock` pins the libraries of the engine (numpy, scipy, jsonschema and qdldl) and the
tools of the tests (pytest, pytest-xdist, Hypothesis, mpmath, PyYAML and ruff). The extra `dev` of
`pyproject.toml` names the same tools. The editable install gives you the `napkin` command, and a
change to `napkin/` has its effect at once.

The distribution is `napkin-sim`. It is not on PyPI, and the PyPI project `napkin` is a different
tool. Install napkin from a checkout or from a release wheel.

Use each command of this guide from the root of the checkout. The wheel does not hold the tools in
`tools/`. `python -m tools.check` finds them because the root is the current folder. The option `-B`
stops Python from writing bytecode files into the checkout.

Run an example to check the setup:

```console
$ napkin run examples/piano_tuners --value tunings_done --at 0h,1year
Piano tuners: a median run to 8760 h
               unit      0 h   1 year
tunings_done   tunings   0     2923.54
```

## The repository

| Folder or file | What it holds |
| --- | --- |
| `napkin/model/` | The compiler: the parser and the formatter (`language/`), the declared model (`semantic.py`), the lowering to a program, the runs, the identity of a model and the evidence rule (`support.py`) |
| `napkin/program/` | The program, which is the contract between the compiler and the engine: its parts, its checks, its proofs, its configuration, its record, its checkpoints and its file (`artifact.py`) |
| `napkin/core/` | The typed expressions, the units, the intervals and the comparison band (`comparisons.py`) |
| `napkin/engine/` | The engine: the timeline and its six methods (`timeline/`), the integrators (`continuous/`), the solve library (`solve/`), the report, the studies and the Monte Carlo studies |
| `napkin/cli.py`, `napkin/commands/` | The `napkin` command ([docs/cli.md](docs/cli.md)) |
| `napkin/draw/` | The picture of a model, which `napkin draw` gives ([docs/draw.md](docs/draw.md)) |
| `napkin/dynamics/` | The analysis of the dynamics of a run ([docs/python-api.md](docs/python-api.md)) |
| `napkin/session.py`, `napkin/spread.py`, `napkin/store.py`, `napkin/package.py` | A run that stops at breakpoints (`Session`), the Monte Carlo study of a model, the run store, and a package with its variants |
| `napkin/distributions.py`, `napkin/schema/`, `napkin/std/units.json` | The families of distributions, the schemas, and the units of the prelude |
| `examples/` | Three small packages that a reader runs as written: `piano_tuners`, `reservoir` and `incident_response_tempo` |
| `scenarios/` | The catalogue: one folder for each package, and the folders `docs/`, `library/` and `tests/` of the catalogue. The publisher writes its index, `scenarios/README.md` |
| `tools/` | The tools of the maintainers: the check (`check.py`), the publisher (`publish/`), the comparison of two runs (`compare.py`), the start of a package (`new.py`), the locator of the catalogue (`catalogue.py`), the evidence tools (`evidence/`) and the benchmarks (`bench/`) |
| `tests/` | The tests by part: `language/`, `model/`, `core/`, `program/`, `engine/`, `reference/`, `acceptance/`, `audit/`, `commands/`, `draw/`, `dynamics/`, `evidence/`, `publish/` and `release/`, and the tests of the tools |
| `docs/` | The documentation of the engine and the language ([docs/README.md](docs/README.md)) |

### Packages and variants

A package of the catalogue is the folder `scenarios/<package>/`, with its main file `model.scn`. The
name of the folder is the name of the package. The name starts with a lowercase letter and has only
lowercase letters, digits and `_`, such as `iv_fluid_shortage`.

A variant of a package is the folder `variants/<name>/` of the package, with its own `model.scn`.
Its name is `<package>:<name>`, such as `water_controls_wipe:juneau`. Each other `.scn` file of the
folder of the package is a module, which the main file and the variants can use.

The folders `scenarios/docs/`, `scenarios/library/` and `scenarios/tests/` belong to the catalogue as
a whole. They are never packages. `scenarios/docs/` holds the rules and the guides of the catalogue,
`scenarios/library/` its shared vocabulary, and `scenarios/tests/` its central tests.

## The rules of a change

### One owner for each decision

- One module owns each decision of the engine, and every reader of that decision calls that module.
  [docs/engine/owners.md](docs/engine/owners.md) names the owner of each decision.
- Keep one implementation of each rule. Do not copy a rule into a second module.
- In a program, each result has one writer. The program checker refuses a value that two writers set
  (`two_writers`). One solver owns each joint decision.

[The design](docs/design/README.md#one-owner-for-each-decision) gives the reason for this rule.

### Fix the cause, not the case

1. Reduce the failure to the smallest model that shows it.
2. Find the owner of the cause of the failure.
3. Fix the cause in its owner, not at the place where the case failed.
4. Search for each other reader of the same rule, and examine each one.
5. Test a close variant of the case, and make sure that it passes too.

A fix that cures one case and leaves a close variant broken is not a fix
([change 21](docs/design/decisions.md#change-21)). [docs/engine/owners.md](docs/engine/owners.md)
records the owner, the reduced cases and the evidence of each fix to the engine.

### A test for each rule

- Each fix comes with a test of its rule: a property, or a metamorphic test that does not depend on
  the reference interpreter. Put it beside the test of the example that failed.
- A bug fix comes with a test that fails before the fix.
- A new rule of the language comes with a test on a small model with a closed form.

### Keep the language and the engine sound

- There is no layer for compatibility. When a format changes, change every consumer and every fixture
  in the same change.
- `LANGUAGE_VERSION` in `napkin/program/artifact.py` names the meaning of a program. Increase it with
  each change of what a program calculates. `FORMAT_VERSION` names the layout of the program file.
- Weigh a choice of a method, a tolerance or a budget in this order: defensibility, then speed, then
  precision ([change 10](docs/design/decisions.md#change-10)).
- A run that cannot answer stops with a named failure. Never give a different answer in silence.
- An edit document is one transaction: the compiler checks it whole, in every run of the model,
  before any run takes its values.
- Freeze each acceptance expectation and its independent inputs. Do not take an expectation from a
  trace of the engine. Do not weaken an expectation to make a test pass.

### Keep the identity of a model

The model hash (`model_hash`, `napkin/model/identity.py`) names one revision of what a model
calculates. It covers these parts:

- the program, the options and the named runs;
- the horizon and the numerical settings of the default run;
- the version of the language.

It covers no text, title, menu line, note or `record` declaration. It also covers no place of a line,
and no name of a file or of a package. A saved edit document names the model hash, and the engine
refuses a document of another revision.

The run store keys each run by its program, its configuration and the code of the engine
([docs/engine/README.md](docs/engine/README.md#the-run-store)). A change to that code makes each
stored run a miss, so the next check calculates each run again.

### Author each part in its own file

- Write a model in `scenarios/<package>/model.scn`, and a variant in
  `scenarios/<package>/variants/<name>/model.scn`.
- Write what the briefs show in the `brief.toml` of the folder. `show` gives the values to show, and
  `drivers` the inputs to list. `featured` and `[[comparison]]` give the comparisons, and
  `[[spread]]` the spreads. The distributions of a spread are an edit document in the folder
  `spreads/`.
- Write the picture of the model in its `style.toml`, who plays each part in its `roles.toml`, and
  its local units in its `units.json`.
- Write the shared units and the conventions of the project in `scenarios/library/vocabulary.json`.
  Each main file names the library with `library "../library"`.
- No file defines a unit of the prelude again. A local unit cannot use the name of a unit of the
  library.
- The publisher only renders. Put no value and no rule of a model into it.

### Start a package

`python -B -m tools.new NAME` writes the folder of a new package of the catalogue, with each file in
its shape. Then it prints the list of what to write, in order. For a model outside the catalogue,
`napkin new DIR` writes a starter that compiles and runs as written
([docs/modeling-guide.md](docs/modeling-guide.md)).

After each change of a model, use `napkin compile scenarios/PACKAGE` and `napkin run
scenarios/PACKAGE`. `napkin fmt scenarios/PACKAGE` formats the files of the model. The tests require
that each committed model file keeps its format.

An AI case follows [the AI operations guide](scenarios/docs/ai-operations.md). A realistic pathway of
a human team matches its AI pathway.

### Give each value its support

- Each coefficient and each choice of a model cites a `record` declaration: a source, an identity, a
  convention or an assumption. The compiler warns of each value without one (`no_record`).
- Record the units, the place in the source, the applicability and the range of inputs of each
  number.
- Keep the applicability and the uncertainty of a source. A bound that you choose for a scenario is
  not a measured interval.
- Keep each historical observation in the population, the geography and the price year that its
  source reports. When a calculation uses another population, record the transfer.
- Let the units convert each number. Do not add a conversion by hand.
- A model declares only what it can estimate. It says in its documentation or its evidence why it
  leaves out an outcome.

### Write evidence through the evidence tools

`tools.evidence.integrate` is the only writer of claims and sources. Each evidence pack writes one
folder: the folder of a package or of a variant. A pack never changes the records of another folder.
Do not change claims or sources with a script of your own.

`python -B -m tools.evidence.adopt --from SOURCE --to DESTINATION --id RECORD` shows the copy of a
record and its dependencies into another folder. Add `--write` to apply the copy through the same
writer. The copies stay independent. [The evidence guide](scenarios/docs/evidence/README.md) gives
the details.

### Keep what a scenario owns in its folder

- Keep the names, the assertions, the fixtures, the oracle input maps and the prose of a scenario in
  the folder that owns them. In a package with variants, put what applies to every variant in the
  folder of the package.
- Central tests can find the scenarios, but they never keep a list of real packages. Their synthetic
  packages use the reserved IDs (`SC` and two digits, such as `SC97`) or generic names.
- Generated catalogues, dossiers, manifests and the changelog can name scenarios.
- Before you land a change, search outside `scenarios/` for whole words that name a package of the
  catalogue. Also search for the retired IDs SC10, SC41, SC43, SC43_<place> and SC45. Report each hit
  with its reason.

### Describe a pull request

In a pull request, describe the cause of the change and the behavior that results. Name the
scenarios that it affects and the checks that you did. For a correction of the evidence, give the
place in the original source and the input or the outcome that it affects.

## Testing

Use the smallest check that covers the change. A correction of one test calls for that test again.
It does not make the other tests that passed invalid, so do not do the whole suite again after each
fix. A refresh of the committed summaries is a separate task.

### The two tiers

`pyproject.toml` gives pytest the option `-m 'not deep'`, so a plain `pytest` runs the regular tier.

| Tier | Command | What it runs |
| --- | --- | --- |
| Regular | `python -B -m pytest` | Each test without the mark `deep`. The generated corpus runs 300 seeds. |
| Deep | `python -B -m pytest -m deep` | Only the tests with the mark `deep`: detailed or slow checks. The generated corpus runs 88,000 pairs of a seed and a transformation. |
| Both | `python -B -m pytest -m "deep or not deep"` | Each test |

The deep tier is slow. Do it by hand, never in the automatic check. Keep each regular test within
about 10 seconds. Make a slower test smaller, or mark it `deep`.

### The corpus and its transformations

- `tests/language/corpus/spec_NN.scn` holds each code block of the specification of the language
  as a file. The formatter tests parse and format each block, and other language tests compile some of
  them.
- The generated corpus (`tests/engine/test_port_invariance.py`) makes small exact models from a
  seed. A transformation changes how a model is written or run, but not what it means.
- Some of the transformations are these: another spelling of the units (`small_unit`), a split of a
  stage (`split`), and the Python builder (`builder`). Others load the program file (`artifact`),
  stop and resume the run (`checkpoint`), use another method (`sparse`), or move each read of the
  ledger (`roundoff`).
- Each transformation must keep the physical readings and the order of the events. The test
  compares each one with the reference interpreter.
- The regular tier runs seed k with transformation k modulo the number of transformations, for 300
  seeds. The deep tier runs each transformation for 2000 seeds.

[docs/engine/verification.md](docs/engine/verification.md#the-generated-corpus) gives each
transformation.

### The reference interpreter

`tests/reference/` is a small, slow and exact interpreter of the rules of the language. It shares no
code with the evaluation of napkin. A model is plain data (`model.py`), and `run.py` calculates it in
fractions. Where it cannot calculate a model exactly, it raises `errors.NotCovered` with the reason.
The tests of the engine compare the engine with it. A change of a rule changes the reference
interpreter and the engine in the same change, and each has its own test.

### The check and its scopes

`python -B -m tools.check` runs lint, the tests, the evidence stage and the committed summaries for a
scope. Add `--plan` to see the scope and the stages, and to run nothing.

| Command | Scope |
| --- | --- |
| `python -B -m tools.check` | The changes against the merge base with `main`. A change in a folder of a scenario selects the scenarios that read it. A change of docs only runs lint. Any other change stops the check (exit 2). |
| `python -B -m tools.check --tests PATH` | Lint and the named test file or test ID. Repeat `--tests` for more. |
| `python -B -m tools.check --scenario ID` | Lint, the tests of the folders of the scenario, the central contracts of the scenario, the evidence and the comparison of its summaries |
| `python -B -m tools.check --scenario ID --deep` | The same, with the deep tests of that selection |
| `python -B -m tools.check --scenario ID --skip-summaries` | The same, without the comparison of the summaries |
| `python -B -m tools.check --all` | Lint, each regular test, the evidence of each package and each committed summary |
| `python -B -m tools.check --all --deep` | The full check: each test, three stored runs calculated again, and each summary |
| `python -B -m tools.check --release` | The check of a release, from an empty run store, with the wheel ([Releasing](#releasing)) |

An ID names a package (`iv_fluid_shortage`), a variant (`water_controls_wipe:juneau`) or a package
with variants, which selects each of its variants. Repeat `--scenario` for more scenarios.
`--spreads` also samples each declared spread at its sample count. `--test-jobs N` and
`--publish-jobs N` set the number of processes.

The stages of a check, in order:

1. **Release notes** (`--release` only): `CHANGELOG.md` has notes for the version of the package.
2. **Lint**: `ruff check` and `ruff format --check` on `napkin`, `tools`, `tests`, `scenarios` and
   `conftest.py`.
3. **Python tests**: pytest stops at the first failed test, and lists each test that takes more than
   10 seconds.
4. **Evidence**: each selected package compiles with no warning `no_record` and no warning `datum`.
5. **Stored runs** (`--all --deep` and `--release`): three stored runs, calculated again in a
   separate process, must agree with the store bit for bit.
6. **Committed summaries**: `tools.publish --check` on the selected scenarios, or on the whole
   catalogue.
7. **Wheel** (`--release` only): the check builds the wheel and tests it outside the checkout.

The full check and the release check take a long time. Do not start them during a focused change. If
a check needs more time than the user gave you, say so before you start it.

The tests in `tests/engine/`, `tests/model/` and `tests/acceptance/` always calculate their runs.
Every other test takes its runs from the run store, which is `.cache/runs` in the checkout.
`NAPKIN_STORE=off` stops the store, and `NAPKIN_STORE=DIR` uses another folder.

`pytest --scenario ID --focused` applies the filter of a focused check: the tests of the folders of
the scenario and the central tests with the mark `scenario_contract`. Without `--focused`,
`--scenario` only narrows the scenario parameters. To test a change of central code, give the test
file without `--focused`.

### Do only the tests that failed

`tools.check` stops the cache of pytest (`-p no:cacheprovider`), so it keeps no list of failed tests.
To do only the tests that failed, use pytest directly:

1. Do the tests once: `python -B -m pytest tests/engine/test_port_invariance.py`.
2. Do only the tests that failed in that session: `python -B -m pytest --lf tests/engine/test_port_invariance.py`.
3. For deep tests, add `-m deep` to both commands.

pytest keeps the list of failures in `.pytest_cache/`, which git ignores. If no test failed, `--lf`
does each selected test. `-x` stops at the first failure.

### The kinds of test

- **The language** (`tests/language/`): the parser, the declared model, the formatter, each construct,
  and the corpus of code blocks.
- **The compiler** (`tests/model/`, `tests/core/`): one refused model for each stage that can refuse a
  model (`tests/model/test_compile.py`), the units, the library, and the typed expressions.
- **The audit cases** (`tests/audit/`): small models of an audit, through the compiler, the engine,
  the program file, the evidence check and the command.
- **The program** (`tests/program/`): the program file, its canonical bytes, its checks, its proofs
  and its record.
- **The engine** (`tests/engine/`): the mathematics of the engine on small models with closed forms,
  the generated corpus, and the distributions.
- **The reference interpreter** (`tests/reference/`): its rules, on their own small models.
- **The acceptance tests** (`tests/acceptance/`): one model that writes each construct of the
  language (`test_every_construct.py`), and the rules that every path of napkin keeps
  (`test_rules_across_paths.py`).
- **The command and the API** (`tests/commands/`, `tests/test_api.py`), the examples
  (`tests/test_examples.py`), the run store, the session and the spreads.
- **The catalogue** (`scenarios/tests/` and the `tests/` of each package): each model compiles, runs
  and keeps its format, and its oracles agree with its runs.
- **The picture, the dynamics, the evidence and the publisher** (`tests/draw/`, `tests/dynamics/`,
  `tests/evidence/`, `tests/publish/`).
- **The wheel** (`tests/release/wheel_smoke.py`), in a release check only. It installs the wheel
  outside the checkout, and it uses each command on the starters, the examples and the catalogue.

### Test rules

- Use independent mathematics, properties and real counterexamples. Agreement between two solvers
  or two builds of the engine is not an oracle.
- Never pin authored wording. When a test needs a text, read it from the scenario or the library.
- Never calculate an expectation by hand from an authored default input. An expected value comes from
  independent mathematics: closed forms, the shared conventions in `scenarios/tests/oracle_common.py`,
  and the oracles in `scenarios/<package>/tests/`.
- An expected value can also come from a property: conservation, partitions, bounds, finiteness, or
  the expected orders of the standard runs.
- Never copy a trace of the engine into an expectation.
- The same run is deterministic: test it for identity. A sample alone or in a batch, another solver
  or another platform agrees within the stated tolerances: compare it within them
  ([change 11](docs/design/decisions.md#change-11)).
- The root `conftest.py` rewrites the assertions of each test module of the catalogue and of its
  helpers. A `tests/conftest.py` of a scenario holds only fixtures of its own.

### Testing distributions

The tests of distributions and of Monte Carlo studies are thorough and fast. They follow these rules:

- **The mathematics without samples.** A distribution is its quantile function. At fixed
  probabilities, the quantiles of each family agree with the true quantile, which the cdf of the
  family in mpmath gives (`tests/engine/distribution_oracles.py`). The mean and the variance of a fine
  grid of quantiles agree with the closed forms.
- **An exact answer for each sample.** A study of a tiny model has an outcome with a closed form in
  the drawn inputs. The test checks each sample against that closed form, with no statistical
  tolerance (`tests/engine/test_monte_carlo_study.py`).
- **Seeded statistics only for the randomness itself.** These tests use thresholds from the DKW and
  Hoeffding bounds at a probability of false failure of 1e-9, with fixed seeds.
- **Properties** with Hypothesis, with `derandomize=True` and no database: quantiles increase with
  the probability, stay inside the support and invert the cdf.
- **The pool of processes** (`tests/test_spread.py`). A study in a pool of processes agrees with the
  same study in one process, and the same spread gives the same study again.

### Tests and the folders of the catalogue

Each scenario owns its specific tests and its frozen inputs. The shared mathematics and the
parameters across scenarios stay central. Central tests can loop over the folders of the scenarios
that they find. Assertions, expected orders, fixtures and oracle input maps that name a scenario
belong to its folder.

In a package, the assertions that apply to every variant go in the `tests/` of the package. The
assertions of one variant go in its own folder. The locator of the catalogue (`tools/catalogue.py`)
gives the scenarios that read each folder. After a move, compare the collected test IDs with those
before the move.

### Compare two runs

`python -B -m tools.compare BASE OTHER` compares two runs by their names, their values and their
traces. A side is a model, a capture that `--write FILE` keeps, or the old published results of a
scenario. Two numbers agree within `--absolute` (1e-9) plus `--relative` (1e-6) times the larger
magnitude. Agreement shows that a change kept the results. It does not show that either side is
correct: the independent tests show that.

## Speed

A change of the engine must not make it slower. `tools/bench/port_benchmark.py` compares two engines
on fixed workloads:

1. Make one clean worktree for the baseline engine (`B`) and one for the candidate engine (`F`).
   In the next step, `BASELINE` and `FINAL` are the folders of these worktrees.
2. Do the paired runs: `python tools/bench/port_benchmark.py campaign --phase final --out RESULTS --revision B=BASELINE --revision F=FINAL`.
3. Print the gate: `python tools/bench/port_benchmark.py summary --phase final --out RESULTS`.

Each row has three pairs of runs, and the order of the two engines changes in each pair. The gate compares the median of the paired
ratios F/B with the limit 1.05 for each row. The `events` guard has the limit 1.10. Do the benchmark
alone on the machine, with the same Python and the same power settings throughout.
[docs/engine/verification.md](docs/engine/verification.md#speed-benchmarks) gives the workloads, the
guards and the rules of each measurement. `python -B -m tools.bench` measures the compiler and the
engine on the models of the catalogue.

## The publisher

The publisher (`tools/publish/`) renders the committed summaries of the catalogue. For each package
or variant that runs, it writes `results/brief.md`, `results/readings.md` and
`results/source-dossier.json`. The command for the whole catalogue also writes the source manifest.

1. Check the summaries of one scenario: `python -B -m tools.publish --check --scenario ID`.
2. Write them again: `python -B -m tools.publish --write --scenario ID --jobs 1`.

`--only briefs`, `--only readings` and `--only dossier` select one format. `--only manifest` selects
the source manifest of the whole catalogue. `--sample-spreads` also samples each declared spread and
writes `results/paired-spreads.json`. `--model PATH` writes the readings of any model.

The publisher refuses a package with a warning `no_record` or `datum`. It only renders: put no value
and no rule of a model into it. After a change of the text that readers see, write the summaries of
the scenarios that you changed again. [tools/publish/README.md](tools/publish/README.md) gives the
coverage of each file.

## Releasing

1. Set the version in `pyproject.toml` and in `CITATION.cff`. Add the notes of the release under
   `## X.Y.Z` in `CHANGELOG.md`.
2. Do the check of the release: `python -B -m tools.check --release`.
3. Tag `vX.Y.Z`, and push the tag. No workflow runs on GitHub.

The check of the release checks the notes in `CHANGELOG.md` and the `v*` tag at HEAD, if there is
one. Then it does the full check with `--deep` from an empty run store, so the release never depends
on stored runs. Last, it builds the wheel and tests it in a new environment outside the checkout.

To keep a wheel for a release, build it into `dist/`. A build in the tree leaves `build/` and
`*.egg-info`, and a `build/` that stays goes into the next wheel. So delete both before and after the
build:

```bash
rm -rf build *.egg-info
python -m pip wheel --no-build-isolation --no-deps . --wheel-dir dist
rm -rf build *.egg-info
```

## Writing style

Each page of the documentation, and each text of a scenario that readers see, follows ASD-STE100
Simplified Technical English (STE). The aim is text that a reader understands the first time, in one
meaning only.

### The documentation

These rules apply to the pages in `docs/`, `scenarios/docs/` and the root, and to each README:

- **Sentences.** A sentence of a procedure has no more than 20 words. A descriptive sentence has no
  more than 25 words. A paragraph has no more than six sentences.
- **Procedures.** Write one instruction in each sentence, in the imperative: "Write the flow in the
  entity." Put a condition or a warning before the instruction that it applies to. Number the steps.
- **Verbs.** Use the active voice and the simple tenses: present, past and future. Do not use the
  passive voice in a procedure.
- **One word, one meaning.** Use each term of [the terms](docs/language/README.md#terms) only in its
  meaning, and use only that term for its concept. Do not use synonyms for variety. The keyword
  `record` declares evidence: write it in code type, as a `record` declaration. The word record
  alone means the result of a run.
- **Simple words.** Do not use a word that ends in -ing as a noun or an adjective where a simple verb
  or noun is possible. Do not use phrasal verbs ("set up", "carry out", "find out"): use one verb
  ("prepare", "do", "find"). Use no idioms, and no abbreviations except units, code names and the
  terms.
- **Articles and nouns.** Keep "the" and "a". Do not put more than three nouns together.
- **Lists and tables.** Use a list for a sequence and a table for a comparison.
- **Code.** Code names, syntax and example text stay exactly as the language spells them, in code
  type.
- **Content.** Write no filler and no marketing words. Do not tell the history of the rewrite, except
  in the pages of the design decisions and in the changelog.
- **Examples.** Each model example (a code block marked `scn`) compiles, or is an exact part of a
  model that compiles. Each output in a page is the real output of the command.

### The text of a scenario

These rules apply to everything that a reader sees in the briefs and the readings:

- the titles and the summaries of the scenarios;
- the AI operation;
- the labels of the responses, the attacks, the pathways, the outcomes and the inputs;
- the labels of the systems and the statuses;
- the text of the events;
- the notes that say where each value comes from.

#### Words

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
   These are names in the model, not in the world. Say what they mean: "after 15 days", "the people
   the study follows", "each person is counted once".
4. **Say who chose a value.** Keep the status of every value: reported by a source, taken from a
   source and applied here, true by definition, or assumed for this scenario. Write "the scenario
   assumes", "chosen for this scenario" or "reported by the study", not a bare "selected". A range
   that a reader can explore is not a measured interval: say so.
5. **Simple verb forms.** Use the present tense for what happens in a scenario. Do not use a word
   that ends in -ing as a noun or an adjective: write "the AI keeps its access", not "continuing
   access". A technical name is the exception (cooling, heating, shipping).

#### Noun clusters

6. **No more than three nouns together.** Break a longer cluster with a preposition or a short
   clause: "time until crews start repairs", not "repair crew start delay time".

#### Sentences

7. **Short descriptive sentences.** A sentence has no more than 25 words and one idea. Start with the
   most important information.
8. **Active voice.** Say who does the action: "Crews restore the circuits", not "The circuits are
   restored".
9. **Keep the small words.** Keep "the", "a", "of" and "to". Do not write telegraph text.
10. **One topic in each paragraph.** A paragraph has no more than six sentences.

#### Labels and statuses

11. **A label names one thing in a short noun phrase.** For example: "Deaths", "Hours without
    electricity", "Time until repair work starts".
12. **A status is a short, plain statement of the condition.** For example: "Power off", "Crews
    repair the circuits", "Access removed".
13. **Every quantity has its unit.** Do not show a yes/no condition as a percentage: make it a value
    of type `bool`, which reads `true` or `false`. A status display gives the text of the case that
    applies.
14. **A pathway label names the defender response, then the attack.** It is the response label and
    the attack label, joined by " · ". For example: "Delayed response · AI keeps access".
15. **Prose never shows a record ID.** The tables of the methods and the evidence keep the IDs.

#### Glossary

| Use | For | Do not use |
| --- | --- | --- |
| AI agent, the AI | The AI system that makes the attack | delegated AI, AI execution |
| human team | The people who make the matched attack in the comparison pathway | human operator team |
| attacker | The AI agent or the human team, when a sentence is true for both | intruder, adversary |
| defender response | How fast and how well the defenders act: early, delayed, limited | preset, response profile |
| attack | What the attacker does and how long it keeps access | configuration, package |
| pathway | One defender response together with one attack | variant, branch |
| outcome | A calculated result: deaths, serious casualties, economic loss, hours without a service | metric, dimension, endpoint |
| deaths | People who die because of the incident, above the deaths that occur without it | fatalities, excess fatalities |
| serious casualties | People who die or are seriously hurt, each person counted once | |
| economic loss | Cost in US dollars at 2025 prices | USD2025, damage |
| the people the study follows | The people whose harm the scenario counts | cohort, exposure population |

The three headline outcomes have the same labels in every scenario: "Deaths", "Serious casualties,
including deaths" and "Economic loss".

#### Examples

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
expression, and do not add detail of the attack. Then write the committed summaries of the scenarios
that you changed again: `python -B -m tools.publish --write --scenario ID --jobs 1`.
