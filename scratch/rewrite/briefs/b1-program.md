# Brief B1-P: the program, the contract between the compiler and the engine

Read `briefs/COMMON-B.md` first. You own `napkin/program/` and `tests/program/`, and nothing else.
State file: `scratch/rewrite/b1/program/STATE.md`.

## Why

Today the compiler gives the engine two compiled forms, and the tools read a third thing. The
rewrite has one contract, "the program": a typed description of a model with no text and no place
in a file. The front end will lower source to a program; the engine, the proofs and the oracle
will read programs. Engine tests will build programs in Python and never parse. You write the
contract and its builders, and every worked example of the spec as a program. Later stages extend
the contract one slice at a time, so a clean, small, consistent design matters more than covering
a detail that no example needs.

## Read

- `scratch/rewrite/g0-decisions.md` in full, and `scratch/rewrite/spec.md` in full: the program must
  be able to express every construct of the spec.
- `scratch/rewrite/PLAN.md`: "Changes after G0", choice 1 of "The approach", and "B1".
- A plain description of the whole language that already exists, as your starting design:
  `scratch/rewrite/a2/ref/model.py` (the oracle's model classes). It predates G0: it has `none`,
  no `if`, no categorical draw, and global sharing.
- `scratch/rewrite/a4a/FINDINGS.md`: the layout note (section 3.4) and R-A4a-01, 02, 07 and 08
  (pools of rows, links by row number, the record of a run, the key of a stored run).
- `scratch/rewrite/a4b/FINDINGS.md`: R-A4b-01, 02, 04 and 07 (the pool of occurrences, a finished
  occurrence, the reader graph, writer sites), and `scratch/rewrite/a4b/spike/program.py`.
- `scratch/rewrite/a1/types.md`: the type system.
- `napkin/core/expr.py` and `napkin/core/ops.py`: the expression nodes and their closed-list
  contract. Skim `napkin/model/structure.py` (today's contract) and `key` in `napkin/store.py`.

## What to build

1. **Records** (`napkin/program/`), frozen dataclasses, importing nothing of napkin but `napkin.core`:
   - the program: its templates, the members of each (hand-written instances and table rows, with
     their ids and their link columns resolved to row numbers), and the values of the run's root;
   - a value: name, kind (input, state, formula, link, collection binding, distribution), type
     (`bool`, enum, number with a unit, text, a reference to a template, a collection `<T>`, a
     distribution), bounds with either side open, `readonly`, a `scale` hint, its initializer;
   - flows: directed, reversible (one signed rate, two legs), and with several legs (one
     `served_fraction`); their ends (a store, `SOURCE`, `SINK`); `request` and `capacity`, each a
     value or a formula; the settings of an endpoint (`outflow` and `inflow`: `capacity`,
     `request`, `allocation` as `proportional()` or `priority(...)` over legs or a projection);
   - events: parameters, locals, local stores and flows, steps (`after D` with an optional guard,
     `until C`), the statements of a stage (assignment, `+=`, `-=`, `move`, `.start(...)` of one
     event or of a collection, `if`/`else`, `switch` with cases that can carry guards), triggers
     (condition, body, `reset when` or `reset after`);
   - solvers: inputs, `solve_for` (existing fields, projected fields, new unknowns with a domain),
     constraints, ranked objectives;
   - status displays (cases of condition and rating) and assertions;
   - collections and their operations: `Template.instances`, `event.occurrences`, `x.outflow.flows`,
     literals, `where`, `by`, projection, the six reductions, `.at(x)`;
   - draws (`d.draw()`, keyed by their site), an actor's choice (`actor.choose(d)`), `since`,
     `count`, `elapsed`, `delayed`.
   Expressions are nodes of `napkin/core/expr.py`. Add no node kind to `napkin/core`: a reduction, a
   keyed read, a read of an occurrence, a draw and a choice are named parts of the program that an
   expression reads by name. A reference is structured (template, field, path of links), never
   inferred from the prefix of a flat name. Each record carries `origin`: the stable path of the
   declared part that it comes from (such as `Tank.water`), never a line number, so that a report
   or a trace finds its label and its evidence. Texts and labels are not in the program.
2. **The run configuration**: the values of the inputs (a number with a unit, or a distribution for
   a distribution-valued input), the mode (`sampled` or `median`), the seed, the controller of each
   actor and its picks, the limits `max_occurrences` (default 1,000,000), `max_active` (100,000) and
   `max_rounds` (1,000), the solver budgets (counted in work, not in seconds), the numerical
   settings, and the request of what to record.
3. **The record** of a run, as an interface that the engine, the oracle and the report share: for
   each recorded value its history as pieces that can be read at any time, the trace (starts,
   finishes, stage commits, firings, draws, choices, moves, failures), and a manifest of what it
   holds.
4. **Builders** (`build.py`): a short Python API that tests and, later, the front end's lowering
   use to make programs. Its module docstring shows the tank of the spec ("This complete local
   example delivers 3 L/h until the tank empties at 2 hours 40 minutes") in about 15 lines.
   `finish()` checks the invariants that the engine relies on and refuses a program with a
   diagnostic that has a code and names the part: names resolve; one writer for each value (a
   flow's actual rate is the engine's, or one solver's); flow ends are stores or `SOURCE`/`SINK`,
   with compatible units; a reversible route joins two stores, never `SOURCE`, `SINK` or a tally;
   a formula reads but never draws, starts or writes; a trigger starts only its own event; links
   and flow ends are fixed; a parameter with a unit type is never a flow end (D13); the written
   order of event locals, also for the plain properties of a declared flow (D14). There is no
   `none` value (D4).
5. **Canonical bytes** (`canonical.py`) of a program and of a configuration, for the key of a stored
   run: equal for two builds of one model, different when a number, a unit, a name or a structure
   changes.
6. **Examples** (`tests/program/examples.py`): every row of the table "Acceptance cases" of
   `spec.md`, and every other worked model of the spec that has stated numbers, as a function that
   returns the program, the configuration and the expected results: (time, path, value) with exact
   numbers (fractions where exact), or an expected failure with a part of its message. These are
   the shared fixtures of the oracle, the engine and the front end from now on, so name them well
   and give each a docstring that cites the spec's section.
7. **Tests** (`tests/program/`): each example builds and passes `finish()`; a list of malformed
   programs, each refused with its code; canonical bytes equal and different as above.

Do not write any engine, front end or evaluation of expressions. Do not touch `napkin/model/`,
`napkin/engine/` or `napkin/core/`.

## Exit

`tests/program/` passes, and `tests/core` still passes. Every acceptance row of the spec has an
example. Your last message lists the records in one line each, the examples by name, and the
decisions that you made beyond the spec.
