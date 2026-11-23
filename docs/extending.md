# Extend the language and the engine

This page tells a contributor what to change in the code for each kind of new feature. It names the
files and the functions of today's code. The paths are relative to `napkin/`, unless they start with
`docs/` or `tests/`. The words **model**, **value**, **stage**, **method**, **run** and
**configuration** have the meanings of [the terms](language/README.md#terms).
[compiler.md](compiler.md) describes the chain from the text to the program, and
[docs/engine/README.md](engine/README.md) describes the engine.

## Contents

1. [Rules for every change](#rules-for-every-change)
2. [A new statement](#a-new-statement)
3. [A new expression function](#a-new-expression-function)
4. [A new unit or dimension](#a-new-unit-or-dimension)
5. [A new collection operation](#a-new-collection-operation)
6. [A new engine method rule](#a-new-engine-method-rule)
7. [A new CLI flag](#a-new-cli-flag)

## Rules for every change

**One owner for each decision.** Each decision of the language or the engine has one owner: one
function that makes it. Every other part calls that function and does not make the decision again.
For example, `core/comparisons.py` owns the comparison band. `engine/departure.py` owns the rule
that releases a stock from a bound, and `program/check.py` owns the invariants of a program. Before
you add a rule, find its owner. When no owner exists, make one function the owner, and make every
caller use it.

**Write the rule in [docs/engine/owners.md](engine/owners.md).** Add one row to the table of its
subject. The row names the decision as a question. It also names the code that owns it, the code
that calls the owner, and the tests that check it.

**Keep the two ways to write a program equal.** A model text and a program that `program/build.py`
makes are the two ways to write a program
([compiler.md](compiler.md#the-builder-the-second-authoring-path)). A new feature needs both. The two
must give the same canonical bytes for the same model.

**Raise the versions.** In `program/artifact.py`:

- raise `FORMAT_VERSION` when a dataclass of `program/parts.py`, `program/refs.py`,
  `program/config.py` or `program/record.py` gets, loses, renames or moves a field, or when a new
  dataclass comes;
- raise `LANGUAGE_VERSION` when a program computes something new or other. The model hash covers it,
  so each saved edit document of an older revision becomes invalid.

**Keep the reference interpreter independent.** `tests/reference/` runs a program in exact
fractions, with no code of napkin's evaluation. Add the feature there with its own code, or make it
raise `errors.NotCovered` with the reason. Never import the engine into it.

**Test the rule, not one case.** Add a test of the rule, a property or a comparison of two paths,
beside the case that shows it. `tests/acceptance/test_every_construct.py` writes every construct of
the language in one package. Add each new construct to it.

**Write the documentation.** Each kind of feature below names the page of the language reference
([docs/language/README.md](language/README.md)) that describes it.

## A new statement

A statement is a line of a stage: today an assignment, a `move`, a start, an `if` and a `switch`.
Do these steps in order:

1. Add a frozen dataclass to `model/language/nodes.py`, with the fields that the line writes.
2. Read the line in `model/language/parse.py`, in `Parser.statement`, which reads each line of a
   stage. Add the form to the message `ACTION`, which lists the lines of a stage.
3. Write the line in `model/language/format.py` (`line_rows`). Make sure that
   `parse(write(tree)) == tree`.
4. Resolve the line in `model/semantic.py`, in `Resolver.statement`. Check its types
   and units, its writes (`fixed_write`, `readonly_write`, `result_write`), its draws and the
   lifetimes of what it installs. Give each refusal a code.
5. Add a dataclass to `program/parts.py`, and a constructor to `program/build.py`. `Builder.finish`
   gives it its origin (`step[k].do[j]`).
6. Add the kind of the dataclass to `KINDS` in `program/artifact.py`. Add the kind to `EXECUTABLE`
   when a run can stop before the statement. Raise `FORMAT_VERSION`.
7. Check the invariants of the dataclass in `program/check.py`, each with a code.
8. Write the statement with the builder in `model/lowering.py`.
9. Run the statement in the engine: `Moment.execute` in `engine/timeline/moment.py` runs the
   statements of a stage in order, and `engine/timeline/plan.py` resolves the targets of a stage.
   A statement that writes a stock commits it with `Run.write` (`engine/timeline/run.py`), and
   `engine/timeline/stocks.py` keeps the balance of the stock.
10. Keep checkpoints exact: `engine/timeline/checkpoints.py` stops before a statement, and
    `engine/timeline/saved.py` saves the state of a run. A statement that holds state across a
    stop needs both.
11. Add the statement to the proofs. `program/reach.py` finds what it can set and start.
    `program/proofs.py` counts it as a writer for `never_falls`, and as a part for `reads`.
12. Draw it: `draw/things.py` finds what it reads, changes, starts and moves, `draw/triggers.py`
    gives its words, and `draw/equations.py` gives its line in the panels.
13. Run it in the reference interpreter: `tests/reference/from_program.py`, `model.py` and `run.py`.
14. Raise `LANGUAGE_VERSION`. Describe the statement in
    [docs/language/events.md](language/events.md).

## A new expression function

A function of the language is a call such as `erf(x)`. `tests/engine/test_erf.py` is the model of
the tests that a new function needs. Do these steps in order:

1. Add an `Operation` to `OPERATIONS` in `core/ops.py`. It states the arity, the rule for units
   (one of `UNIT_RULES`), the domain and the kinks. It also states the partial derivatives and how
   the value moves with each argument. `core/derivatives.py` takes the derivative from it.
2. Add the name to `FUNCTIONS` in `core/expr.py`.
3. Give the function a handler in each table that `ops.handlers` checks: `TABLE` of
   `core/evaluation.py` (with its runtime function and its entry of `OF_ONE`), of `core/arrays.py`
   and of `core/intervals.py`. A table that lacks the operation fails when Python imports its
   module, so no consumer can miss it in silence. `core/units.py` takes the handler from the rule
   for units of the operation. A new rule for units needs a function in `RULES` of that module.
4. Add the function to the tables that name each function:
   - `core/literals.py`: the exact value of an expression of literals;
   - `core/comparisons.py`: the floor of the comparison band;
   - `FUNCTIONS` in `model/language/parse.py`;
   - the types of calls in `model/semantic.py` (`PURE`, for a function of one plain number).
5. Write it in the picture: `_FUNCTIONS` in `draw/notation.py` gives its LaTeX. `draw/triggers.py`
   writes any other function by its name.
6. Check what a solver can say with it: `call` in `model/solvers.py` refuses a function of an
   unknown as `nonlinear`, except the functions that it names. Change it only for a function that is
   affine or convex.
7. Add the function to `tests/reference/evaluate.py` (`_fn`), or let the interpreter refuse it by
   name.
8. Raise `LANGUAGE_VERSION`. Describe the function in
   [docs/language/values-and-types.md](language/values-and-types.md).

## A new unit or dimension

A unit is data, not code. A quantity is its dimension and its exact scale, never its spelling
(`core/units.py`). A dimension is a name with a power, so a new dimension needs no code.

| Where the unit is for | Where to write it |
| --- | --- |
| One package | The package's `units.json`, which `schema/scenario-units.schema.json` checks |
| One variant | The variant's own `units.json` |
| The packages that share a library | The `vocabulary.json` of the library that the `library "PATH"` line names (`schema/library.schema.json`) |
| Every model | The prelude, `std/units.json` |

A unit has its `dimensions` (`{"tunings": 1}`), its `scale` in the canonical unit of its dimension,
and a `description`. The examples of the repository show the form, as in
`examples/piano_tuners/units.json`:

```json
{"tunings": {"dimensions": {"tunings": 1}, "scale": 1, "description": "One tuning of one piano."},
 "tuner": {"dimensions": {"tuners": 1}, "scale": 1, "description": "One piano tuner who works full time."}
}
```

These rules apply:

1. A name is in one place only. No file can define a name of the prelude again
   (`model/library.py`, `with_prelude`).
2. Before you add a unit to the prelude, search the catalogue for that name. A package that already
   defines it no longer compiles. `tests/test_catalogue_units.py` checks the units of the catalogue.
3. Time is the dimension `time`, and its canonical unit is the hour. The commands read a time of
   `--at` and `--lag` by this dimension (`TIME_DIMENSION` in `commands/common.py`).
4. A unit spelled with `*` and `/` (`L/h`, `person * year`) composes from the units of the table.
   It needs no entry.

## A new collection operation

A collection operation is a call after a dot on a collection, such as `.where(...)`, `.by(...)` and
`.at(...)`. Do these steps in order:

1. Add the name to `METHODS` in `model/language/parse.py`. The tree holds it as a `nodes.Method`.
2. Type it in `model/semantic.py`: add the name to `KEYED` when it gives a keyed view. Give the read
   its form (today `('where', source, test)`, `('by', source, field)` and
   `('lookup', source, key)`), its member type and its key, and say if it is fixed for the run.
3. Add a start dataclass to `program/refs.py` beside `Where`, `By` and `Lookup`, and its spelling to
   `spelled`. Raise `FORMAT_VERSION`.
4. Write it in `model/lowering.py`, and give the builder a handle for it in `program/build.py`.
5. Resolve it in `program/check.py` (`Resolver`), with the code `collection` for a wrong use.
6. Run it in the engine: `engine/timeline/plan.py` resolves the paths through a collection, and
   `engine/timeline/collections.py` holds the entries, the reductions and the keyed reads. A keyed
   read whose key moves needs its crossings: `engine/timeline/region.py` gives the key surfaces to
   the methods Sparse and MovingDeclared.
7. Add it to the proofs: `program/proofs.py` (`never_falls` reads the members that a view can name)
   and `program/reach.py`.
8. Add it to `model/solvers.py` when a solver can read it, and to `draw/things.py`,
   `draw/notation.py` and `draw/triggers.py` for the picture and its words.
9. Run it in the reference interpreter: `tests/reference/from_program.py` and `evaluate.py`.
10. Raise `LANGUAGE_VERSION`. Describe the operation in
    [docs/language/values-and-types.md](language/values-and-types.md).

## A new engine method rule

A method is the engine part that calculates one connected set of stocks: Family, Lines, Component,
Sparse, Declared and MovingDeclared ([docs/engine/README.md](engine/README.md)). A method rule is a
decision that each method makes for its sets. Examples are when a stock leaves a bound, which branch
a formula takes inside a segment, and how much a full stock can pass.

| Part | Where it is |
| --- | --- |
| The choice of a set's method | `Plan.connect` in `engine/timeline/plan.py` (`FAMILY`, `LINES`, `COMPONENT`, `SPARSE`, `DECLARED`) |
| The instances of the methods of a run, and their rebuild at a moment | `engine/timeline/ways.py` |
| What every method gives the timeline | `Way` in `engine/timeline/way.py` |
| The methods | `engine/timeline/family.py`, `lines.py`, `component.py`, `sparse.py` and `declared.py` (`DeclaredWay`, `MovingDeclared`) |
| Shared owners | `engine/allocation.py`, `engine/departure.py`, `engine/continuous/`, `core/comparisons.py` |
| The state at a stop | `engine/timeline/saved.py` |

Do these steps in order:

1. Write the decision as one question, such as "Does a stock leave a bound?".
2. Find the owner of the decision in [docs/engine/owners.md](engine/owners.md). When it has none,
   write one function in a shared module, such as `engine/departure.py` or `engine/allocation.py`.
3. Make each method call the owner. Remove every copy of the decision from the methods. A method
   still supplies its own operands: its state, its rates and its time.
4. Keep the rule through a stop: `engine/timeline/saved.py` must save and restore what the rule
   reads, so that a resumed run gives the same answers.
5. Apply the rule in the reference interpreter (`tests/reference/run.py` and its helpers), with its
   own code.
6. Test each method that can meet the decision with a case that tells their answers apart. Put the
   test in `tests/engine/`. Include a stop and a resume when the rule holds state.
7. Add a row to [docs/engine/owners.md](engine/owners.md): the decision, the code that owns it and
   the code that calls it, and the direct coverage.
8. When the rule changes a result of a program that compiles today, raise `LANGUAGE_VERSION`, and
   record the decision in [docs/design/decisions.md](design/decisions.md).

To change which method a set takes, change only `Plan.connect`. Each method must give the same
answers within the stated tolerances, so the choice of a method changes the speed, not the result.

## A new CLI flag

Each command is a module of `commands/` with three names: `SUMMARY`, `configure(parser)` and
`main(args)` ([cli.md](cli.md)). Do these steps in order:

1. Add the flag in `configure(parser)` of the command, with `parser.add_argument`. Give it a
   `metavar` and a help text with an example.
2. At import time, a command module reads only the standard library and `commands/common.py`.
   Import the compiler and the engine inside `main`, so `napkin --help` stays fast.
3. Read the flag in `main(args)`. When two commands read the same kind of value, put the reader in
   `commands/common.py`, as `hours`, `times_of`, `edits_of` and `configured` are. One reader owns
   each kind of value.
4. Refuse a wrong command line with `common.UsageError` (exit 2). Refuse a problem of the model or
   the run with `common.Failed` (exit 1). A message names the flag and gives the closest names.
5. Add the flag to the JSON document of `--json` when it changes what the command prints (`document`
   in `commands/run.py` and `commands/sample.py`).
6. Update `DESCRIPTION` and `EXAMPLES` of the command when the flag is a main use.
7. Test the flag in `tests/commands/` (`test_<command>.py`, and `test_cli.py` for the exit codes).
8. Describe the flag in [docs/cli.md](cli.md), with a real example and its output.

A flag that sets an input belongs in the edit document, not on the command line
([cli.md](cli.md#the-edit-document)).
