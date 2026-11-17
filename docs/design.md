# The design of the compiler and the engine

This page is an account of the design: how the parts fit, which foundations were weighed and why
each was taken or left, the contracts that the design keeps, what was measured, and the limits and
the costs that remain. The pages of the parts have the detail: [compiler.md](compiler.md) for the
compiler, [engine.md](engine.md) for the engine, [extending.md](extending.md) for a new feature,
[language.md](language.md) for the language.

## The chain

A model goes through one chain. Each step is a function with a contract, and a later step reads
only what the step before it gives.

| Step | What it gives | Where |
| --- | --- | --- |
| The text to the syntax tree | Nodes with the place of each token. The parser is written by hand, for its diagnostics. | `model/language/` |
| The syntax tree to the resolved model | Names, templates, links and evidence, with typed expressions. | `model/language/resolve.py`, `model/semantic.py` |
| The resolved model to the structure | The parts of a model (quantities, flows, groups, rules, checks, outputs), each with the node of each expression. One structure for each set of start-state options. Nothing after this step reads a text of an expression or a nested mapping. | `model/lower/`, `model/structure.py` |
| The structure to a resolved run | The values of the inputs of one run, with the proofs of its bounds, domains and crossings. | `model/analysis/`, `model/compile.py` |
| The resolved run to a plan | What the engine holds for every run of one structure: the spaces, the form of each quantity, the rules, the groups, the reads of each part. | `engine/timeline/plan.py` |
| The plan to a run | The events in their order, the outcomes, and the record that a report reads. | `engine/timeline/run.py` |

A model with a table has one more product: the hybrid core (`model/hybrid.py`), with one family
for the rows of a table that have one shape. The engine runs a family on arrays.

## Why it is built so

**An expression is a typed node, and one computation is one node.** The compiler before held each
expression as text: one condition was parsed five or six times, its units were found and thrown
away, and seven lists named the functions. Now `core/expr.py` has the nodes, and `core/ops.py` has
one contract for each operation: its arity, its rule of units, its domain, where it is not smooth,
its derivatives. Each consumer (the value, the programs, the units, the intervals, the faces, the
derivatives, the picture) has one handler for each operation, and a test fails when a consumer has
none.

**A fact is found when it is known, and once.** What follows from the structure alone is found for
the structure. What needs the values of a run is found for the resolved run, and the proofs of one
structure are kept from run to run. What holds for every row of a table is proved once for each
class of rows, over the range of its rows. No check writes into what it reads.

**One timeline, and a rule is read only when its answer can have changed.** The engine before read
every rule at every moment and started every part again: n instances with their own events cost n
times n. Now each rule has a due time in one queue, and a step marks what it wrote; only the rules
that read it are read again. A crossing is due at its own time. The cost of independent instances
grows as their number.

**Blocks, and two tiers.** Between two moments a quantity is a value, a line, or a member of a
block of quantities that read one another. A linear block has a closed form where the proofs allow
it; any other block goes to a solver. A space whose parts the array form does not run goes,
instance by instance, to the general tier: the allocation in full, with its mathematics at a
bound. The things of a model with no table are in the general tier by default.

**The step cap is how often the engine reads a block, and no limit of the solver.** The engine
reads the roots and compares the field with the solution at each cap inside a longer step. The
solver takes the steps that its error allows.

**A derivative says of which kind it is.** A run with directions carries the derivative of each
value on the path of its events. The report gives each derivative a class (smooth, one-sided,
undefined, unsupported, structurally zero) and an estimate of its numerical error.

**An estimator is a claim of its own.** A study gives the mean with the error of independent
samples. Each other estimator (Sobol' points, weighted outcomes, a control, the derivative of an
expectation) is asked by name, says what it assumes, and has its own interval. The mean of the
derivatives of the samples is given only where the structure shows that it is the derivative of
the mean.

## The foundations that were weighed

Napkin owns the meaning of a moment (order, cascades, windows, delays), the rationing and the
conservation, where an event is located, the proofs, the units, the names of the random streams
and the rules of the derivatives. It gives the rest to libraries: stepping, error control, the
solution between two steps, linear algebra, linear programs, special functions and quasi-random
points.

| Candidate | What was found | Decision |
| --- | --- | --- |
| SciPy `Radau` | Correct, and the engine drives it step by step. It finds its Jacobian by differences. | **The solver of the engine**, and the only one that the package needs. |
| CVODE of SUNDIALS (`sundials4py`) | It passes the conformance suite of the solver adapters. On equal work in the thin slice it was 4.6 and 4.8 times faster, most of it from the Jacobian. Its bindings are a beta release with no wheel for Linux on aarch64. It reads the rate at the ends of its steps only, so a narrow pulse inside a long step is not seen where the engine holds it at the cap. | **An adapter** that a caller can name when the package is there. Not a dependency. |
| CasADi | The library marks its integrators with events as experimental. In two probes, integrators of it gave wrong values when more than one event fell in one output interval; whether that is a defect or a limit of the experimental feature was not found out. | **Not a dependency.** It is the independent implementation in the tests of the derivatives. |
| A native tier for the kernels (llvmlite) | It compiles generated code fast, but it is a code generator: to take it is to own the lowering, the errors, the derivative code and a cache. The evaluation of expressions was 25 to 40% of a field evaluation when the choice was due. | **After the gate**, as a stage of its own, with the Jacobian from the contracts of the operations. |
| Numba | 1 to 37 s to compile generated straight-line code. | Not for generated model code. |
| JAX with Diffrax, Julia SciML, torchdiffeq | A poor fit for resets, the order of the events of one moment, latency or packaging. | Not adopted. |
| Lark, xDSL, SymPy | The parser by hand gives better diagnostics; the others are heavy or slow here. | Not adopted. |
| HiGHS through SciPy (`linprog`) | In use for the allocation at a bound. | Kept. |
| `scipy.stats.qmc.Sobol`, `scipy.integrate.quad` | Scrambled Sobol' points; the mean of a distribution as the integral of its quantile function. | Taken for the estimators. |
| mpmath | Closed forms at 30 to 40 digits. | In the tests only, as an oracle. |

## The contracts

| Contract | What it says | Where |
| --- | --- | --- |
| The comparison of two builds | A change of the numerical core is judged by classes of difference: within the tolerance of the solver, an event time within the event tolerance, or a discrete difference, each of which is explained. | `CONTRIBUTING.md` |
| When a rule is read | At one time the due events go one at a time in the order of the file, and each reads what the events before it wrote. A rule is read when its answer can have changed; a crossing is due at its own time. | [engine.md](engine.md#one-moment) |
| The two tiers | The tier of a run follows from its own values alone. The two tiers give the same run within the tolerance. | [engine.md](engine.md#tables-and-tiers) |
| The proofs of a table | A proof holds for every row of a class. It is made over the range of the rows, so it can refuse a table that a model written out row by row admits. | [compiler.md](compiler.md#what-is-known-for-every-row-of-a-table) |
| The step cap | The engine reads a block at each cap. A longer step is taken only where the field agrees with the solution at each half cap. | [engine.md](engine.md#between-moments-the-solver) |
| The class of a derivative | The class is the safe one: a derivative can be called one-sided that is not, never the reverse. | [engine.md](engine.md#tables-and-tiers) |
| The estimators | Nothing changes unless a caller asks. Each estimator has the interval that belongs to it. A pair with no valid estimate has no value. | [engine.md](engine.md#estimators) |
| The same result again | The same build, platform and inputs give the same result, whatever the number of processes. | [engine.md](engine.md#the-run-store) |

## What was measured

Measured at the gate of Stage B (2026-11-14), on one machine with 4 processors, the run store off,
each workload once and alone on the machine. The baseline is that of Stage 0, on the engine before
this work. The minimums are those that the owner set.

| Workload | Baseline | Now | Minimum |
| --- | --- | --- | --- |
| The largest compile of the catalogue, cold | 79.3 s | 2.6 s | 10 s |
| The first run of each model, warm | the slowest 11.9 s | the largest model 4.5 s; the heaviest water model 1.9 s; each other model 1.4 s or less | 6 s; 2.5 s; 2 s |
| Every run of the catalogue, warm | 111 runs in 513 s; the slowest 23.7 s; 84 runs above 2 s | 111 runs in 157 s; the slowest 11.6 s; 21 runs above 2 s | (see below) |
| 1,000 samples of the heaviest water model, 4 processors | about 4.7 hours | 8.7 minutes | 12 minutes |
| 100,000 rows of a table, independent: compile | not reached (585 s for 12,800 instances) | 2.5 s | 60 s |
| 100,000 rows of a table, independent: one run | not reached (149 s for 400 instances) | 68 s | 10 minutes |
| 100,000 rows: peak memory | not reached (1.9 GB for 12,800 instances) | 0.84 GB | 8 GB |
| Growth of the cost from 1,000 to 100,000 rows | about the cube | the power 1.02 | the power 1.3 |

**Where a minimum is not met.** The minimums of a run were set from the first run of each model.
At this gate each run of each model was timed for the first time. Eight of the 111 runs are above
the minimum of their model: two runs of the largest model (11.6 s and 8.0 s against 6 s), two of
the heaviest water model (3.0 s and 2.5 s against 2.5 s), and four runs of three other water models
(2.2 s to 3.7 s against 2 s). Each is two to four times faster than at the baseline. The owner
decided that such an overrun is reported and not chased; the native tier of the kernels is the
next step for the time of a run.

**The same results.** The whole catalogue against the baseline: no event in another order, no
outcome changed, no moment moved; 691,053 values within the tolerance of the solver; 64 values
beyond it, each of a kind that the ledger explains (the time of a peak on a plateau, whose value is
the same; one variance that roundoff moves). The suite: 5,570 tests pass. All 112 committed
summaries match a fresh render.

## The limits, and the costs that remain

- **The general tier evaluates formulas in Python.** The field of a heavy run is most of its time.
  A native tier for the kernels, with the Jacobian from the contracts of the operations, is the
  next stage.
- **No derivative goes through the general tier**, through a stock that comes to rest on its
  bound, through a drawn value or through a value of the past. The report names the part.
- **The proofs of a table are over the range of its rows.** A proof that needs two columns of one
  row together is refused.
- **Two crossings of one mark between two readings are not seen**, as before.
- **The labels of the derivative of an expectation are the safe ones.** A store that can rest on
  its bound, and a comparison that the input can reach, have no estimate. No estimator is built
  for an edge that an event or a comparison makes, or for a distribution that reads the input.
- **The weighting of outcomes runs every path from the start.** It pays where the paths are few.
- **A list whose members all read one another** has a Jacobian with no zero entry: its cost grows
  faster than its size.
- **The report of a large table** reads each row at each candidate time of a peak. For rows that are
  blocks with exact solutions its cost grows as the square of the rows (1,000 rows 28 s, 3,000
  rows 4 minutes), where the run itself grows as the rows.
- **A rate that jumps at a time that the input moves** has no derivative in the report (it is
  `unsupported`): the tangents of a block carry no term for the jump.
- **An expression has a deepest tree**: 150 operations one inside the other. The readers of an
  expression go down its tree with calls. A model with no table writes a sum over a list member by
  member, so such a sum has at most about 150 members; a list of a table is one node and has no
  such limit.
- **A model with a table has shapes that the engine names as outside**
  ([engine.md](engine.md#tables-and-tiers)): the model is refused by the name of the shape, and the
  same file with its instances written out runs.
