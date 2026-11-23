# The design of the compiler and the engine

This folder gives the design of napkin:

- the principles
- the chain from the text of a model to the record of a run
- the rulings and measurements that support them.

The words in **bold** type below have the meanings that
[the terms](../language/README.md#terms) give.

| Page | What it holds |
| --- | --- |
| This page | The principles, the chain from text to record, the libraries, and the archive of the rewrite |
| [decisions.md](decisions.md) | The rulings of the owner (D0 to D17 and changes 1 to 33), which code comments cite |
| [measurements.md](measurements.md) | What a proof establishes, the experiments, and the measured speed |

The pages of the engine give the detail: [docs/engine/README.md](../engine/README.md) for the
engine, [docs/engine/owners.md](../engine/owners.md) for the module that owns each decision, and
[docs/engine/verification.md](../engine/verification.md) for the tests.
[docs/language/changes.md](../language/changes.md) gives what replaced each word of the old
language.

## The principles

### Defensibility, then speed, then precision

The owner ranks three aims in this order ([change 10](decisions.md#change-10)). A choice between
two algorithms, two tolerances or two budgets follows the same order.

1. **Defensibility.** Each number comes from a stated rule and its evidence. The same **run** gives
   the same **record** again ([change 11](decisions.md#change-11)). A run that cannot answer stops
   with a named failure. It never gives a different answer without a word
   ([D0](decisions.md#d0)).
2. **Speed.** People explore a model, run it again, sample it and change its assumptions. A run of
   20 minutes is not used, so speed comes before precision.
3. **Precision.** The **inputs** of a model are uncertain by tens of percent, so a tolerance of
   1e-7 against 1e-10 changes nothing that a reader uses.

Some precision is defensibility, and it stays exact in every case:

- the books of each **stock** balance;
- two equal claims get equal shares;
- a stock stays in its range, and a value that a proof says never falls does not fall;
- where a small difference changes a **trigger**, a branch or who is served, the engine does not
  calculate more precisely. It finds the near-tie and reports it.

### One owner for each decision

Each result has one writer. A flow's **actual rate** comes from the engine, or from one
**solver**. The program checker refuses a value that two writers set (`two_writers`,
`napkin/program/check.py`). When two solvers would compete for one hard limit, one solver owns the
joint decision ([G0 decisions](decisions.md#flows-solvers-and-events-at-g0)).

The same rule applies to the code. One module owns each rule of the engine, and every reader of
that rule calls that module. [docs/engine/owners.md](../engine/owners.md) names the owner of each
decision. A fix goes to the owner of its cause, not to the place where a case failed
([change 21](decisions.md#change-21)).

### Put a rule on the value that has the information

A flow knows its two ends, so its **capacity** and its **request** are on the flow. A stock knows
all of its flows, so the shared limit of its outlets is on its `outflow`. Each endpoint shares among
its own flows by its own allocation. Sharing across several endpoints happens only inside a declared
solver ([change 2](decisions.md#change-2)).

### The model declares, and the caller selects

A **model** holds its values, their texts, their ranges and their evidence. It has no report block
and no comparison ([D9](decisions.md#d9), [D10](decisions.md#d10)). A caller selects the
**paths** and the times to report. To compare two runs, a caller starts the engine two times and
compares the two records.

### An operation that matters is written

A calculation that follows its inputs is a `formula(...)`. A random number comes from `.draw()`. A
new **occurrence** comes from `.start(...)`. A model never gets one of these from a rule that the
reader cannot see.

### Size never changes the equations

A model of any size has the same meaning ([D3](decisions.md#d3)). A large model can take longer,
or stop with a named failure of time, memory or accuracy. The engine never freezes a moving rate
because a model is large.

### A proof is information, not a change of the run

The compiler proves what it can: that a value never falls, and which **events** cannot start
under a **configuration** ([D16](decisions.md#d16)). A report and the evidence displays read these
proofs. A run gives the same record with or without them.

## The chain from text to record

A model goes through one chain. Each step is a function with a contract. A later step reads only
what the step before it gives, and the program is the one contract between the compiler and the
engine.

| Step | What it gives | Where |
| --- | --- | --- |
| 1. Parse | The tree of one text: the logical lines, the tokens and their places. The parser resolves no name. | `napkin/model/language/lex.py`, `parse.py` (`parse`), `nodes.py` |
| 2. Declare | The declared model: the names resolved, the types and the units checked, the texts, the titles and the evidence. The files of a **package** become one declared model. | `napkin/model/semantic.py` (`declare`), `napkin/model/language/modules.py`, `napkin/model/support.py` (the warnings for missing evidence) |
| 3. Lower | The program: frozen parts with no text and no place in a file. Each part has the path of the declared part that it comes from (`origin`). | `napkin/model/lowering.py` (`lower`), through `napkin/program/build.py` (`Builder.finish`, which runs `napkin/program/check.py`) |
| 4. Program and artifact | The program as canonical bytes, and the artifact: the program with its side table (the place, the label and the evidence of each part). A fresh process loads an artifact and runs it without the parser. | `napkin/program/parts.py`, `canonical.py`, `artifact.py`; proofs in `proofs.py` and `reach.py` |
| 5. Plan | What the engine runs of one program under one configuration: an engine name and an expression for each value, the connected sets of stocks and the **method** of each set. | `napkin/engine/timeline/plan.py` (`Plan.of(program, configuration)`) |
| 6. Run | The start, then **moment** after moment to the horizon. Each moment has rounds of **stages**, a new share of the flows, and the triggers. Between moments, each method calculates its sets. | `napkin/engine/timeline/run.py` (`Run`), `moment.py`, `triggers.py`, `occurrences.py`, `ways.py`, `checkpoints.py` |
| 7. Record | The history of each value as pieces, the trace, the failure if one stopped the run, and the manifest. A reader gives the **reading** of a path at a time. | `napkin/program/record.py` (the interface), `napkin/engine/timeline/record.py` (`read`), `napkin/engine/report.py`, `napkin/store.py` (the run store) |

Two entry points join the steps:

- `napkin/model/compile.py` does steps 1 to 3. `compile_text` reads a text, and `load_scenario`
  reads a package or a **variant**. The result (`Compiled`) holds the declared model, the program,
  the configuration of one run, the side table and the hash of the model.
- `napkin.engine.timeline.run(program, configuration)` does steps 5 to 7. With breakpoints, it
  gives a **checkpoint**, and `resume` goes on from it in this process or in a fresh one.

The configuration comes from the model and its named runs (`napkin/model/runs.py`), with the
**edits** of the caller. It holds the inputs, the mode, the seed, the limits, the budgets, the
numerical settings and the request of what to record (`napkin/program/config.py`).

### The methods of the engine

A connected set of stocks runs on one method between two moments (`plan.Connected.way`,
`napkin/engine/timeline/ways.py`):

| Method | File | What it calculates |
| --- | --- | --- |
| Lines | `lines.py` | Connected sets whose rates read nothing that moves, on one network, at any size |
| Family | `family.py` | Each connected set of one flow whose rate reads nothing that moves, on arrays |
| Component | `component.py` | One connected set of stocks and flows, on the continuous engine (`napkin/engine/continuous/`) |
| Sparse | `sparse.py` | A connected set whose rates read moving values, of any size ([change 3](decisions.md#change-3)) |
| Declared | `declared.py` (`DeclaredWay`) | The set of a declared solver whose rates read nothing that moves |
| MovingDeclared | `declared.py` (`MovingDeclared`) | The set of a declared solver whose rates follow the moving state |

## The libraries

Napkin owns the meaning of a moment, the sharing and the conservation, and the place of a crossing.
It also owns the proofs, the units and the names of the random streams. It gives the rest to
libraries.

| Library | What napkin uses it for | Where |
| --- | --- | --- |
| SciPy `Radau` | The integrator of the continuous engine. The engine drives it one step at a time. | `napkin/engine/solvers.py` |
| HiGHS, as SciPy bundles it | The linear programs of the sharing at a bound, and the kept instance of each declared solver | `napkin/engine/continuous/highs.py`, `napkin/engine/solve/kept.py` |
| `qdldl` | The LDL' factorization of the final distance step of a declared solver ([change 18](decisions.md#change-18)) | `napkin/engine/solve/distance.py` |
| SciPy `quad` | The amount that a curved rate moves over an interval | `napkin/engine/continuous/transfers.py` |
| CVODE of SUNDIALS (`sundials4py`) | An optional adapter of the same integrator interface. It is not a dependency. | `napkin/engine/solvers.py` |
| mpmath | A reference for closed forms, in the tests only | `tests/` |

The dependencies of the package are `jsonschema`, `numpy`, `qdldl` and `scipy` (`pyproject.toml`).

### Expressions and operations

An expression is a tree of typed nodes (`napkin/core/expr.py`). Two nodes that compute the same
thing are one object. Each operation has one contract in `napkin/core/ops.py`. The contract gives
its arity, its rule of units, its domain and the points where it is not smooth. It also gives its
partial derivatives and how it moves with each argument. Each consumer (the evaluation, the units,
the intervals, the derivatives, the picture) has one handler for each operation. A consumer that has
no handler for an operation must say so, so no operation is half supported without a word.

## Archive

The working notes of the rewrite are kept in git at commit `af5428b` under `scratch/`: the
spec, the plan, the audits and the prototypes. The commits after it do not hold `scratch/`. To read
one of these files, give its commit and its name to git:

```sh
git show af5428b:scratch/rewrite/spec.md
git show af5428b:scratch/rewrite/PLAN.md
git show af5428b:scratch/rewrite/g0-decisions.md
```

[decisions.md](decisions.md) states each ruling of these notes as it applies today. Where the notes
and the code disagree, the code is correct.
