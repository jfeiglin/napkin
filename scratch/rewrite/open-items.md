# The open items of the spec

Every detail that `spec.md` calls open, proposed, recommended or deferred, with the prototype that
rules on it. Gate G0 is complete when each row has a ruling in `rulings.md`, or the words "not in
the first version" with the message that a model gets. The last column is filled at G0.

| # | Item | Section of the spec | Prototype | Ruling |
| --- | --- | --- | --- | --- |
| 1 | `move` may debit or credit a `readonly` stock | How to declare, read and change a value | A2 | |
| 2 | Boolean expressions have their own type | Primitive and composite types | A1 | |
| 3 | A complete type specification for named states, text, references and unit conversion | Primitive and composite types | A1 | |
| 4 | A `run` keyword or path in source | Primitive and composite types | A1 | |
| 5 | `this` always designates the owning entity | Primitive and composite types | A1 | |
| 6 | A distribution argument inherits a unit from its role | Units, comparisons and layout | A1 | |
| 7 | Unit arithmetic: `48 h / 2` against `48 h/2`, `-` between units, `^` and `**` | Units, comparisons and layout | A1 | |
| 8 | Wrapped clauses, escaped quotes, trailing comments | Units, comparisons and layout | A1 | |
| 9 | `min` and `max` over an empty collection | Collections, keys and projections | A2 | |
| 10 | General lists of scalar values | Collections, keys and projections | scope | |
| 11 | A writable `formula(T)` binding takes another formula, never a scalar | Formulas and the values a caller can read | A1 | |
| 12 | A property that takes a stored rate or a live formula; the copy of a formula | Formulas and the values a caller can read | A1 | |
| 13 | A default selection in a `report:` block | Model text, status cases and evidence | A5 | |
| 14 | Distribution constructors, `.mean`, `.std`, `.draw()` | Distributions and explicit draws | A1 | |
| 15 | Unbounded distributions, transformed draws, fixed defaults, distribution-valued overrides, correlations | Distributions and explicit draws | A1 | |
| 16 | A leg is named in `priority(...)`: `link.forward` | Flows and algebraic solvers | A1 | |
| 17 | An ordinary read of an equality that the solver enforced: rounding | Using collections in a solver | A3 | |
| 18 | The numerical convention of the distance step: scales, references | Solver and execution contract | A3 | |
| 19 | General affine inequalities in the distance step | Solver and execution contract | A3 | |
| 20 | Object parameters of an event: a stock against a copy of its value | Events, triggers and occurrences | A1 | |
| 21 | The spelling of `switch`; a Boolean shorthand | Choosing actions inside a stage | A1 | |
| 22 | The order in which the invocations of a start on a collection run | Calling an event on a collection | A2 | |
| 23 | Forward references in local formulas; when a declared flow may read a later local | State owned by an invocation | A1, A2 | |
| 24 | Short-lived names inside a stage | State owned by an invocation | A1 | |
| 25 | Interruption, cancellation, joining, limits on concurrency | Time, waiting and completion | scope | |
| 26 | An absolute `at T:` | Time, waiting and completion | scope | |
| 27 | The retirement rule for a store of an occurrence | Time, waiting and completion | A2 | |
| 28 | Contact tolerances, and the continuous predicates that the engine can certify | Monitoring a threshold | A4b | |
| 29 | The names of triggers, how many an event can have, which events a trigger can start | A trigger belongs to its event | A1 | |
| 30 | Reads of an occurrence at an earlier time; positional indexing | History and optional domain status | scope | |
| 31 | The syntax and the reads of a flow with legs | Shared resources and competing invocations | A1 | |
| 32 | A type for a resource that is held and released | Shared resources and competing invocations | scope | |
| 33 | The spelling of the choice producer and of the chance producer | Actor decisions and observations | A5 | |
| 34 | An opening balance from outside, in the conservation trace | Delivering at a changing rate | A2 | |
| 35 | `formula.diff(...)` | Optional formula differentiation | scope | |
| 36 | Where an `assert` on mutable state is checked or proved; `assert initially` | Assertions and their timing | A2 | |
| 37 | The syntax of a record: its kind, its id, `claims:` | Evidence at the point of use | A5 | |
| 38 | A citation for a column, and for a single cell | Evidence at the point of use | A5 | |
| 39 | Scale hints: `size`, `scale`, what the engine infers | Numerical scale hints | A5, A4a | |
| 40 | `resolution`: the spacing of inspections against the error of integration | Numerical scale hints | A4a | |
| 41 | `elapsed` after several writes in one stage; a read with zero delay in a stage | Expressions and instantaneous transfers | A2 | |
| 42 | `move(source, destination, amount)` as a shorthand | Expressions and instantaneous transfers | A1 | |
| 43 | The reserved words | Expressions and instantaneous transfers | A1 | |
| 44 | A table row named by position; the `id` column | How templates compose into a run | A1 | |
| 45 | Formula configuration, structural changes of flows, reference contracts | How templates compose into a run | scope | |
| 46 | `use`, `variant`, `change`, options: precedence and conflicts | How templates compose into a run | A5 | |
| 47 | Evidence for a value that an option, a `change` or an override gives; for an event argument | How templates compose into a run | A5 | |
| 48 | Where a comparison of runs lives now that `versus` goes | A run produces one trajectory | A5 | |
| 49 | Name shadowing; enum names with no expected type; when a formula can be replaced | Open design questions | A1 | |
| 50 | Where a collection declares a key that is used again; duplicate members in a literal | Open design questions | A1 | |
| 51 | The dispatch order of simultaneous starts | Open design questions | A2 | |
| 52 | What stays readable on a finished occurrence, also its local store | Open design questions | A2, A4b | |
| 53 | Whether a start returns a stable handle | Open design questions | A1 | |
| 54 | Tolerances for ranked optima | Open design questions | A3 | |
| 55 | Nonlinear route laws; types for two substances with one dimension | Open design questions | scope | |
| 56 | Conflicting writes from independent stages | Open design questions | A2 | |
| 57 | Reset cycles and their diagnostic | Open design questions | A2 | |
| 58 | One-time setup order | Open design questions | A2 | |
| 59 | Configuration precedence, model identity, evidence for overrides | Open design questions | A5 | |
| 60 | Another spelling of the units keeps allocations and levels | Allocation, timing and presentation | A3 | |
| 61 | The zero reference of a solver-local unknown | Allocation, timing and presentation | A3 | |
| 62 | The supported scale for coefficients that move continuously, and for thresholds on solver results | Allocation, timing and presentation | A4a, A3 | |
| 63 | References to status displays; how a report shows a history read that is not available | Allocation, timing and presentation | A5, A2 | |
| 64 | How an author asserts that two links name distinct instances | Scenario cases and remaining decisions | A1 | |
| 65 | Where a human choice pauses after a queued start | Scenario cases and remaining decisions | A2 | |
| 66 | An invalid history read from a report; whether a saved occurrence reference pins it | Scenario cases and remaining decisions | A2 | |
| 67 | `none` in arithmetic, in a comparison, in a reduction | Appendix, 1 | A2 | |
| 68 | A flow with legs that two endpoints rank differently | Appendix, 2 | A2 | |
| 69 | The budget for occurrences that never finish | Appendix, 3 | A2, A4b | |
| 70 | The cost of fair sharing on the route-and-level network | Appendix, 4 | A3 | |
| 71 | The `unserved_volume` example calls an accumulated volume a current one | Appendix, known error | owner | |

## Items that the plan adds for G0

| # | Item | Prototype | Ruling |
| --- | --- | --- | --- |
| P1 | What a run records, and when a stored run serves a request | A4a | |
| P2 | The rule that cuts a model into connected sets, and the limit of each way of running | A4a | |
| P3 | The fallback of each numerical no-go: slower and exact, or a refusal by name | A3 | |
| P4 | The layout of links and flows across tables | A4a | |
| P5 | The pool of occurrences; the proofs over templates | A4b | |
| P6 | The module layout of the engine, and the staging of Phase B | A4b, main | |
| P7 | Named runs, the scenario line, notes, `sees`, the report selection: a spelling for each | A5 | |
| P8 | Candidates to retire and not port | main | |
