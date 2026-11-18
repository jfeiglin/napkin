# Brief B1-O: the oracle, phase 1 (the semantics of gate G0)

Read `briefs/COMMON-B.md` first. You own `tests/reference/` and nothing else. State file:
`scratch/rewrite/b1/oracle/STATE.md`.

## Why

The new engine is checked against a small, slow, readable interpreter of the spec's rules, in exact
fractions. Prototype A2 wrote it in `scratch/rewrite/a2/` and it reproduced 31 worked cases. Gate G0
then changed several rules. You move the interpreter into the test tree and make it follow the
decisions of G0. In phase 2 (a later message) it will read the programs of `tests/program/`, which
another agent is writing now; for phase 1 it keeps its own model classes.

## Read

- `scratch/rewrite/g0-decisions.md` in full, and these parts of `scratch/rewrite/spec.md`: "Flows
  and algebraic solvers" (all), "Solver and execution contract", "Events, triggers and occurrences"
  (all), "Distributions and explicit draws", and "Acceptance cases".
- `scratch/rewrite/a2/FINDINGS.md` and `scratch/rewrite/a2/STATE.md`, then the code in
  `scratch/rewrite/a2/ref/` and `scratch/rewrite/a2/cases/`.

## What to do

1. Copy the interpreter into `tests/reference/` as a package, and its cases into
   `tests/reference/test_*.py`. They run under the repository's own pytest and conftest. Keep the
   description of a model (data classes) apart from the code that runs it.
2. Make it follow G0. Each change gets a test, and a test of A2 that G0 overturned is changed, not
   deleted:
   - **Local sharing** by default: each endpoint shares among its own flows by its own rule, also
     when [0, 0] junctions make rates depend on one another. Fair sharing across endpoints happens
     only inside a declared solver. Two junctions: 1/2, 1/4 and 1/4 L/h; with one solver over the
     four flows and no objective, 1/3 each.
   - **No `none`** (D4). `min` and `max` of an empty collection fail; `sum` is zero in its unit,
     `count` zero, `any` false, `all` true.
   - **Rounds** (D5): stages due together commit one after another, the earliest-started occurrence
     first; 20 g, then a stage that sets 8 g, then one that adds 4 g, gives 12 g. A read of a solver
     result whose inputs changed before it settles is an error, also through a formula (no stale
     answer with a warning).
   - **Branching**: `if`/`else` in a stage (D11); `switch` on a drawn `categorical(...)` value with
     guards on cases (D1): a sampled run samples among the eligible cases; a median run takes the
     most likely eligible case, the first declared on a tie; no eligible case runs `else` and draws
     nothing. An actor's choice: a human picks any eligible case; with no controller the value is
     the forecast's `.draw()`; eligibility and probability are independent.
   - **Requests are soft, capacities hard** (D15): a higher-ranked objective can give a flow more
     than its request.
   - **Writes to a live occurrence** are allowed unless the field is `readonly`; a finished
     occurrence is frozen. Its formulas keep the result they had at the finish (14 stays 14). A
     formula that could not be evaluated at the finish keeps its error: a read raises it, and the
     occurrence still finishes normally (D7).
   - **Written order** of event locals, also for the plain properties of a declared flow; a retained
     `formula(...)` may name a later local (D14).
   - **Limits** (D6): `max_occurrences` (1,000,000), `max_active` (100,000), `max_rounds` (1,000),
     each configurable; the message names the limit, the event, and for `max_active` the oldest
     waiting occurrence and its step.
   - **A human prompt** pauses one atomic stage: a draw and a queued start made before the prompt are
     kept; resuming or replaying commits the stage once, with no second draw, start or transfer.
   - **Units**: the interpreter may work in one canonical unit for each dimension, converting at the
     edges, so that the worked network in kW gives 0.004 kW.
3. Add the acceptance rows of `spec.md` that A2 had no case for, among them: legs that request 0 and
   8 give 0 and 8 with fraction 1, legs that request 0 and 0 give fraction 0; the dispatcher who
   always waits, with and without a spare pump; the water model where service returns at hour 5
   (the rate is 0 at hour 6, the volume keeps the loss); a frozen formula; the two-junction case.
4. Keep the oracle independent of the engine: it may import data (records, and the expression nodes
   of `napkin/core/expr.py`), never napkin's evaluation code. `tests/core/reference.py` is an
   example of an independent walker over expression nodes.

## Exit

`tests/reference/` passes in a few seconds. Every acceptance row of `spec.md` that the interpreter
covers is a test; your last message lists the rows that it does not cover, and why.
