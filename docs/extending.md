# Extend the language

This page is for a person who adds a feature to the language. For each kind of feature, it lists what
must change, in the order of the work. It also names the check that fails when one part is left out.
[compiler.md](compiler.md) describes the steps and the modules of the compiler, and
[CONTRIBUTING.md](../CONTRIBUTING.md) gives the rules of a change and of its tests.

The paths on this page are relative to `napkin/`. A test has its path from the root of the checkout.

Two exercises tested this page: a new function and a new clause of an event, each done for real on a
copy of the code. [The two exercises](#the-two-exercises) gives the files that each one changed, and
what the tests did and did not catch.

## Contents

1. [What holds for each kind](#what-holds-for-each-kind)
2. [A function that the engine evaluates](#a-function-that-the-engine-evaluates)
3. [A form that is no operation of the engine](#a-form-that-is-no-operation-of-the-engine)
4. [A clause of an event](#a-clause-of-an-event)
5. [A policy of a share](#a-policy-of-a-share)
6. [A family of distributions](#a-family-of-distributions)
7. [A lag of an output](#a-lag-of-an-output)
8. [The two exercises](#the-two-exercises)

## What holds for each kind

- **The lists are closed.** Algebraic expressions stay on a list of allowed forms, and each form has
  a type ([CONTRIBUTING.md](../CONTRIBUTING.md#keep-the-language-and-the-engine-sound)).
- **One change.** The language has no layer for an earlier version. Change each consumer and each
  fixture in the same change.
- **The identity of the code.** The `implementation_hash` covers each file of `core/`, `engine/` and
  `model/`, the file `expressions.py`, and the schemas of `schema/` (`model/compile.py`). A change
  to one of them changes the hash.
- **The identity of a model.** The model hash covers each field of each node of the syntax tree
  (`meaning` of `model/language/evidence.py`). So a new field of a node changes the `model_hash` of
  every model. It does not when `identity` of that module leaves the field out for a file that does
  not write it. `identity` does this for the `resolution` line.
- **The run store.** `tests/test_api.py` pins the list of the files that the engine imports
  (`CLOSURE`). A new module that the engine imports changes that list. Then
  `test_the_run_store_reads_the_same_engine_files_as_before_the_api` fails until the list has the
  module.
- **The typed parts.** `Structure.of` loses nothing. When the builder writes a key that no field of
  the typed part takes, it raises `StructureError`, such as `Rule has no field for 'until'`. When the
  builder does not write a field that must be there, it raises `Rule lacks rank`.
- **The documents.** [language.md](language.md) says what a file can write, and
  [engine.md](engine.md) what a run does with each part.

## A function that the engine evaluates

Such a function is an operation: a `Call` node whose name is in `expr.FUNCTIONS`, such as `erf`
([compiler.md](compiler.md#the-contract-of-an-operation)). Do the work in this order.

| Order | What to change | What fails when it is left out |
| --- | --- | --- |
| 1 | `core/expr.py`: the name in `FUNCTIONS`. | `expr.read` gives a part outside the language for each call of the name. The test of step 2 also fails. |
| 2 | `core/ops.py`: its `Operation` in `OPERATIONS`, with each field of the contract. | `tests/core/test_ops.py::test_each_operation_that_a_node_can_have_has_a_contract_and_no_other_name_has_one` |
| 3 | `core/evaluation.py`: its handler in `TABLE`. When the written code calls a name, that name goes in `RUNTIME`. | `LookupError` when Python reads the module: `the value of an expression: no handler for NAME`. |
| 4 | `core/units.py`: nothing, when the contract names a rule that exists. A new rule needs its sentence in `ops.UNIT_RULES` and its function in `RULES`. | `LookupError` when Python reads the module: `the rules for units`, with the name of the rule. |
| 5 | `core/intervals.py`: its handler in `TABLE`. The handler gives the interval of the result, and it refuses arguments that can be outside the domain. | `LookupError` when Python reads the module: `the interval of an expression: no handler for NAME`. |
| 5a | `core/arrays.py`: its handler in `TABLE`. The handler gives the value for many instances in one pass. | `LookupError` when Python reads the module: `the values of an expression for many instances: no handler for NAME`. |
| 5b | `core/derivatives.py`: nothing. The derivative of an expression comes from `partials` of the contract. | |
| 6 | `model/language/expressions.py`: the name in the grammar's `FUNCTIONS`. | The grammar reads the name as a name of a value. A model that calls it gets the code `build`: `NAME is not a function of the language`. |
| 7 | `model/lower/expressions.py`: nothing. The typing's `FUNCTIONS` is the list of step 1. | |
| 7a | `tests/core/reference.py` and `tests/core/test_evaluation.py`: the tests' own walker of a node, and their generator of random nodes. | `tests/core/test_evaluation.py::test_the_function_of_a_node_gives_what_a_walk_of_the_node_gives`, which asks for each operation in some node. |
| 8 | `draw/notation.py`: the name in `ARITY`, with the number of its arguments. | `tests/draw/test_notation.py::test_the_notation_knows_each_function_of_the_language` |
| 9 | The readers of the form of an expression (below). | No check fails. |
| 10 | [language.md](language.md), §2.1, "Functions", and the counts of the functions and the operations in [compiler.md](compiler.md). | No check fails. |
| 11 | The tests of `tests/core/` (below). | |

**The contract (step 2).** State each field. `arity` and `units` decide what the code does.
`domain` and `kinks` are sentences. `partials` gives the derivative by each argument as nodes, and
`monotone` says how the value moves with each argument. The tests of step 11 check `partials` and
`monotone` against the values of the function.

**The consumers (steps 3 to 5).** Each consumer with a table calls `ops.handlers` when Python reads
its module. So the package does not import while one table has no handler for the new operation. A
consumer can name the operation in `unsupported` in place of a handler: it then states that it has
none. The proof on the zero faces (`core/faces.py`) has no table and needs no change.

**The picture (step 8).** A function with a name of its own in LaTeX also goes in `_FUNCTIONS` of
`draw/notation.py`. Any other function is written with `\operatorname`. A function that is not
written as a call, as `sqrt` and `abs` are, also needs its case in `call` of `draw/notation.py` and
of `draw/typeset.py`.

**The readers of the form (step 9).** Some readers know some functions by name. They treat any other
function as a function that they know nothing of:

- `switching_surfaces` of `engine/continuous/integrate.py` ends a numerical segment where `min`,
  `max`, `clip` or `abs` switches. A new function that is not smooth needs its surfaces there. The
  field `kinks` of its contract is a sentence, and no code reads it.
- The classifier of a segment (`engine/continuous/kernels.py`) knows `min`, `max` and `abs`.
- The proofs of `model/analysis/values.py` know `min`, `max` and `abs`.

**The tests (step 11).** These tests read the contracts, so they find a new function that the test
files do not know yet:

- `tests/core/test_ops.py` checks the number of arguments, each partial derivative against a central
  difference, and each direction of `monotone` on random points. Its helper `points` gives the
  arguments of each function, in its domain and away from its kinks. Add the new function to it.
- `tests/core/test_evaluation.py` compares the value of random nodes with a walk of the node
  (`tests/core/reference.py`). It fails until its random nodes, and that walk, have each operation.
- `tests/core/test_units.py` and `tests/core/test_intervals.py` check that each table has each
  operation. Add the cases of the new function: its unit, what its rule refuses, and its interval.
- `tests/draw/test_notation.py` fails until one of its models calls each function of `ARITY`. Its
  list `FUNCTIONS_OF_TESTS`, and the list of `tests/draw/latex_subset.py`, need the name too.
- `tests/core/test_expr.py` and `tests/model/test_expression_programs.py` make random expressions
  from lists of their own. No check fails when they lack the new function: add it.

**Where no single list exists.** Three lists name the functions of the engine: `expr.FUNCTIONS`
(which the typing reads too), the grammar's `FUNCTIONS` and `ARITY` of the notation. Two tests compare
them: `tests/core/test_ops.py` compares the first with the contracts, and
`tests/draw/test_notation.py` compares the grammar with the notation.

## A form that is no operation of the engine

Such a form is a word of the language that the lowering writes in another way, such as `since(e)`
([compiler.md](compiler.md#the-forms-that-are-no-operation-of-the-engine)). The list says where
`since` is today.

| Order | What to change | What fails when it is left out |
| --- | --- | --- |
| 1 | `model/language/expressions.py`: the word in the grammar's `FUNCTIONS`. A word that no thing can take as its name also goes in `RESERVED` of `model/language/lex.py`. | The grammar reads the word as a name of a value: `NAME is not a function of the language`. |
| 2 | `model/language/resolve.py`: `Resolver.resolve_tree` says what the argument is: an event (`EventRef`), the members of a list (`Terms`) or a value (`Ref`). | The argument is a `Problem`, or the typing refuses it. |
| 3 | `model/lower/expressions.py`: `Typing.call` checks the argument and gives the call with the names of the structure. | The code `build`: `unknown function NAME`. |
| 4 | `model/lower/expressions.py`: one function for the form, like `since_form`. Its docstring says what the file writes and what the structure holds. `desugared` calls it, and `WRITTEN` has the word. | The call stays in the text of the structure. The checks of the structure refuse it with the code `expression`: `Unsupported function or keyword arguments`. |
| 5 | The table at the top of `model/lower/expressions.py`, and its copy in [compiler.md](compiler.md#the-forms-that-are-no-operation-of-the-engine). | No check fails. |
| 6 | `draw/notation.py`: the node of the form (`Since`, `Count` and `Elapsed` are such nodes), with its case in `_call` and its letter in `CLOCKS`. `draw/typeset.py` has `CLOCKS` too, and `draw/triggers.py` the words of a trigger. | `tests/draw/test_notation.py::test_the_notation_knows_each_function_of_the_language` |
| 7 | [language.md](language.md). | No check fails. |
| 8 | `tests/model/test_desugar.py`: the value of the form against its meaning, on random states, and each use that has no meaning as an error. | |

A new kind of leaf of a resolved expression needs three things. They are its class in
`model/semantic.py`, its typed kind in `model/resolved.py`, and its case in `resolved.of_tree`.

A form can need a value that the structure keeps under a name of its own. `since` and `count` read
`e__count` and `e__time`, and `elapsed` reads `s__entered`. Such a name has these parts today:

- its suffix in `model/ir.py` (`COUNT`, `TIME`, `ENTERED`);
- its unit in `symbol_units` of `model/analysis/structure.py`;
- its value at the start in `_checked` of `model/analysis/values.py`;
- the clock that reads it in `_timer` of `model/analysis/structure.py`;
- `read_events` of `model/lower/starts.py`, which keeps an event that a part counts or times;
- the store of a run, which keeps the value (`engine/timeline/plan.py` and `run.py`).

## A clause of an event

An event line is `event name [once] [after D] [each W] [when C] [while K]:`. The list says where the
clause `each W` is today. A new clause needs the same parts.

| Step of the compiler | Where `each` is |
| --- | --- |
| The tokens | `model/language/lex.py`: the word in `RESERVED`, and in `NOT_UNITS`, so that it is no unit after a number. |
| The parser | `model/language/parse.py`: `Parser.event` has the form of the line, the order of the words and the message of each. It fills `Event.each` of `model/language/nodes.py`. |
| The resolver | `model/language/resolve.py`: `Resolver.event` has the rules of the clause and reads its expressions. `Resolver.sight` checks that a choice reads only what its actor sees. `Event.each` of `model/semantic.py` holds the result. |
| The lowering | `model/lower/builder.py`: `Builder.event_part` writes `each` and `each_path` into the rule. |
| The formatter | `model/language/format.py`: the word in `KEYWORDS`, so that the formatter keeps a line that continues after it. |
| The identity | `model/language/evidence.py`: `identity` leaves a field out of the hash when the line has no such clause, so that no other model changes its `model_hash`. |
| The typed part | `model/structure.py`: the fields `each` and `each_path` of `Rule`, their names in `Rule.OPTIONAL`, and the role `each` in `Rule.sources`. |
| The parts left out | `model/lower/starts.py`: `run_reads` and `idle_parts` read the names of the clause, so the parts that it reads stay. |
| The analysis of a structure | `model/analysis/structure.py`: `_rule_errors` checks its unit, and that it reads only values that change at moments. `_rearm_errors` knows that a window spends a crossing. |
| The analysis of a run | `model/analysis/values.py`: `_rule_expressions` gives its expressions to the prover of intervals. |
| The engine | `engine/timeline/plan.py`: the field `each` of its `Rule`. `engine/timeline/run.py`: `window`, `spent` and `trigger`. |
| The picture | `draw/notation.py` (`walk`), `draw/model_map.py` and `draw/triggers.py`. |
| The documents | [language.md](language.md), §2.6 and the list of the reserved words; the table of the rules in [engine.md](engine.md#rules); the roles of `Rule.sources` in [python-api.md](python-api.md). |
| The tests | `tests/engine/test_windows.py`. |

What fails when a part is left out:

- **The typed part.** When the builder writes the key and `Rule` has no field for it, the first read
  of `Model.structures` raises `StructureError`.
  `tests/model/test_structure.py::test_a_key_that_no_field_takes_is_an_error_that_names_the_part_and_the_key`
  checks that rule.
- **The model hash.** A new field of `nodes.Event` changes the `model_hash` of every model
  ([What holds for each kind](#what-holds-for-each-kind)).
- **The parser.** A word that `Parser.event` does not know is a `syntax` diagnostic, with the form of
  the line as its message.

**Where no single list exists.** Five functions name the expressions of a rule by hand:
`Rule.sources`, `run_reads`, `idle_parts`, `_rule_errors` and `_rule_expressions`. `Resolver.sight`
and the picture have lists of their own. No check compares these lists. So read each of them for a
new clause.

A clause that reads values that move between moments can make a new class of crossing. A new class
of crossing needs a structural argument for its detection
([CONTRIBUTING.md](../CONTRIBUTING.md#keep-the-language-and-the-engine-sound)).

## A policy of a share

A share has two policies today. With no `order`, its flows share the limit in proportion
(`proportional`). With `order f, g`, it serves the flows in that order (`priority`). The list says
where a policy is today.

| Step of the compiler | Where the policy is |
| --- | --- |
| The parser | `model/language/parse.py`: `Parser.share` reads `share VAR limit RATE [order f, g]`. `Allocate.serve` of `model/language/nodes.py` is the order, or None. `limit` and `order` are in `NOT_UNITS` of `model/language/lex.py`. |
| The resolver | `model/language/resolve.py`: `Resolver.allocation` finds the entity of each flow of the order. `Allocation.serve` of `model/semantic.py` holds the result. |
| The lowering | `model/lower/builder.py`: `Builder.rationing_part` writes `policy` and `order`. It refuses an order that does not name each flow of the stock one time. |
| The typed part | `model/structure.py`: `Allocation`, with `policy`, `capacity` and `order`. |
| The parts left out | `model/lower/starts.py`: `remove` takes a flow that is left out from the order. |
| The analysis of a structure | `model/analysis/structure.py`: `_group_errors` checks the unit of the limit and the order of a `priority` group. `_withdrawal_errors` checks that the flows of one stock are in one group. |
| The engine | `engine/continuous/fields.py`: `_ration` applies the limit of each group. `_priority_order`, `_proportional_order` and `_closed_form` serve the groups where a stock rests on a bound. |
| The picture | `draw/equations.py`: the words of each policy (`WORDS`). |
| The documents | [language.md](language.md), §2.5, and [engine.md](engine.md#flows-allocation-and-coupling). |
| The tests | `tests/engine/test_priority_at_a_face.py` and `tests/engine/test_coupled_queue_boundaries.py`. |

**Where no single list exists.** No module has the list of the policies. The words `proportional` and
`priority` are written in the builder, the analysis, the engine and the picture. `_ration` serves each
policy other than `proportional` in its `order`. The functions for a stock on a bound take the groups
of each of the two policies by name. So no check fails when the engine does not know a new policy.

A new policy changes the arithmetic of a run at a bound. Give it a property test with requests that
are no round numbers. In that test, the flows together take what is available, and no flow gets a
negative rate.

## A family of distributions

A value of an input or a `let` can be a distribution. An event can draw a distribution of numbers
when it fires ([language.md](language.md), §2.4 and §2.6). The list says where a family is today.

| What to change | What it is |
| --- | --- |
| `distributions.py`: `FAMILIES` | The record of the family: its parameters in their order, the parameters that are plain numbers, and the kind of its values. |
| `distributions.py`: `problems`, `quantile`, `support`, `central` | The checks of the arguments, the quantile function, the lowest and the highest value, and the central value. |
| `model/language/parse.py`: `DISTRIBUTIONS` | The words that start a distribution as the value of an input or a `let`. |
| `model/language/expressions.py`: `FUNCTIONS` | The families of numbers, so that an expression of an event can call them. |
| `model/ir.py`: `DRAWN` | The families of numbers that an event can draw, each with its parameters in their order. |
| `model/analysis/structure.py`: `PLAIN_PARAMETERS`, `_extra_unit` | The parameters of a draw of an event that are plain numbers, and the unit of the draw. |
| `model/uncertain.py`: `plain` | Whether a parameter of a family is a plain number. It names `categorical`, `bernoulli` and `beta`. |
| `engine/sampling.py` | The draw of an input. It names `bernoulli` and `categorical`, whose draws are no numbers. |
| `tests/engine/distribution_oracles.py`, `tests/engine/test_distributions.py` | The cdf of the family in mpmath, and its cases (`CASES`). |
| `tests/fixtures/distribution-texts.json` | The texts of the distributions as an edit document writes them. |
| [language.md](language.md), §2.4 and §2.6 | The list of the families. |

What fails when a part is left out:

- `problems` and `quantile` raise `ValueError`, `unknown family`, for a family with no case of its
  own.
- `support` reads `min` and `max` for each family but `beta`. A family with no such parameters needs
  its case there.
- `tests/draw/test_notation.py::test_the_notation_knows_each_function_of_the_language` fails when a
  family is in `DRAWN` and not in the grammar's `FUNCTIONS`, or the reverse.

**Where no single list exists.** `FAMILIES`, `DISTRIBUTIONS`, `DRAWN` and the grammar's `FUNCTIONS`
each list the families, and `PLAIN_PARAMETERS` repeats the plain parameters of `FAMILIES`. No test
compares `FAMILIES` with `DISTRIBUTIONS`, with `DRAWN` or with `PLAIN_PARAMETERS`. No test asks for a
case of each family in `CASES`.

The tests of a family follow [CONTRIBUTING.md](../CONTRIBUTING.md#testing-distributions): its
quantiles against its own cdf, and its mean and variance against the closed forms.

## A lag of an output

An output can have a lag: `lag 2 h`, `lag uniform(a, b)` or `lag mixture([0.9, 0], [0.1, 336 h])`
([language.md](language.md), §2.8). The list says where a kind of lag is today.

| Step of the compiler | Where the lag is |
| --- | --- |
| The parser | `model/language/parse.py`: `Parser.lag` reads the three forms. `Lag` of `model/language/nodes.py` has the `kind`, the `delays` and the `shares`. |
| The resolver | `model/language/resolve.py`: `Resolver.output_fields` reads each delay as an expression. `Lag` of `model/semantic.py` holds the result. |
| The lowering | `model/lower/builder.py`: `Builder.lag_part` writes the lag with its `type`. Each delay is a quantity in hours. |
| The typed part | `model/structure.py`: `Lag` and `LagComponent`. |
| The delays of a lag | `model/ir.py`: `lag_delays` gives the delay expressions of a lag, by its type. The parts left out, the analysis and the evidence trail read the delays through it. |
| The analysis of a structure | `model/analysis/structure.py`: `_outcome_errors` checks three things. Only a cumulative output has a lag. Each delay is a time that reads inputs only. The weights of a mixture add up to 1. |
| The analysis of a run | `model/analysis/values.py`: `_checked` checks that no delay is below zero and that the two delays of a `uniform` lag are in order. `quantity_claims` proves the claims of an output with a lag. |
| The report | `engine/report.py`: `lagged` gives the value of the output for each type. |
| The picture | `draw/notation.py`: `walk` gives each delay with the place `lag`. |
| The documents | [language.md](language.md), §2.8, and [engine.md](engine.md#outcomes-and-reports). |
| The tests | `tests/engine/test_reporting.py`. |

**Where no single list exists.** No module has the list of the types of a lag. The words `fixed`,
`uniform` and `mixture` are written in the parser, the builder, `lag_delays`, the analysis and the
report. Two of these readers do not refuse a type that they do not know:

- `lag_delays` reads each type other than `fixed` and `uniform` as a `mixture`;
- `lagged` reads each type other than `fixed` and `mixture` as a `uniform` lag.

So no check fails when one of them does not know a new type. A new field of a lag is different: the
typed part refuses a key that `Lag` has no field for.

## The two exercises

Each exercise added one feature by the steps of this page, on a copy of the code. Then steps were
left out, one at a time, and the tests of the changed files were run, to learn which check finds each
omission. The features themselves are not in the language: the exercises tested the page and the
tests. The copies were older than `core/arrays.py` and `core/derivatives.py`, so steps 5a and 5b of
a function were not part of an exercise.

### A function: `tanh`

The exercise changed 17 files:

- 6 files of the package: `core/expr.py`, `core/ops.py`, `core/evaluation.py`, `core/intervals.py`,
  `model/language/expressions.py` and `draw/notation.py`;
- 2 documents: [language.md](language.md) and [compiler.md](compiler.md);
- 9 test files: 8 that have a list of the functions or cases for each function, and one new file
  with the tests of the function in a model.

What the exercise found:

- **Steps that the table did not name.** The lists of `tests/draw/latex_subset.py`,
  `tests/draw/test_notation.py`, `tests/core/test_expr.py` and
  `tests/model/test_expression_programs.py`, and the counts in [compiler.md](compiler.md). The table
  has them now.
- **Five omissions were tried.** Four failed: the name left out of `expr.FUNCTIONS` (step 1), of
  `RUNTIME` (step 3), of the grammar's `FUNCTIONS` (step 6) and of `ARITY` (step 8). Steps 1 and 3
  failed at the tests of the function itself and at the tests of the models of
  `tests/draw/test_notation.py`; steps 6 and 8 failed at
  `test_the_notation_knows_each_function_of_the_language` and at those tests of the models. **One
  passed every test:** the name left out of `_FUNCTIONS` of `draw/notation.py`,
  which gives a function its own name in LaTeX. Without it the function is written with
  `\operatorname`, which is right for a function that LaTeX does not know, so no test can tell. The
  other steps (2, 4, 5 and 7a) were not left out one by one: each fails when Python reads the
  package or at the first test, as its row says.
- **Three wrong contracts passed before the tests were made stronger.** A `monotone` that said that
  the value never rises passed, because the helper `points` of `tests/core/test_ops.py` did not know
  the function, so no point moved. A wrong interval passed, because the random nodes of
  `tests/core/test_intervals.py` took their functions from a list of their own. A wrong rule for
  units passed, because no case named the function. The tests now read the functions from the
  contracts: `test_ops.py` asks that each argument rose at some point, `test_intervals.py` asks that
  each function of one argument was in a node that was sampled, and `tests/core/test_units.py` has a
  test of each function whose rule is `plain`. These three changes are in the tree.
- **A defect that was there before.** With the new random nodes, the prover of intervals raised
  `ZeroDivisionError` in a branch that no state reaches (`1 / (x + y)` after `x != 0`, with `x`
  fixed at 0). `refine` of `core/intervals.py` now reads nothing in an empty context. The fix and its
  two cases are in the tree.

### A clause of an event: `until U`

The clause ends an event: from the first moment at which `U` holds, the event never triggers again.
The exercise changed 24 files and added one:

- 16 files of the package: `model/language/` (`lex.py`, `nodes.py`, `parse.py`, `resolve.py`,
  `format.py`, `evidence.py`), `model/semantic.py`, `model/lower/` (`builder.py`, `starts.py`),
  `model/structure.py`, `model/analysis/` (`structure.py`, `values.py`), `engine/scheduler.py` (the
  rule engine of that time; its place is now `engine/timeline/`) and `draw/` (`notation.py`,
  `model_map.py`, `triggers.py`);
- 3 documents: [language.md](language.md), [engine.md](engine.md) and [python-api.md](python-api.md);
- 5 test files, and one new file with the tests of the clause (30 tests).

It added 156 lines to the files that were there. No file of the typed expressions (`core/`) changed,
and no engine file but the scheduler.

What a part that is left out does:

| Part left out | What fails |
| --- | --- |
| The word in `RESERVED` or `NOT_UNITS` (`lex.py`) | The test of the form of the line. |
| The word in `KEYWORDS` of the formatter | The test that the formatter keeps the clause. |
| The field left out of the hash when the line has no clause | The test that a model with no such clause keeps its `model_hash`. |
| `Resolver.event` does not read the clause | 32 tests of the clause. |
| `Resolver.sight` does not read the clause | The test that a choice reads only what its actor sees. |
| The resolver lets the start have the clause | The test of the form of the line. |
| The builder does not write the key | 24 tests of the clause. |
| `Rule` has no field | `StructureError` at the first read of the structures: 44 tests. |
| The role in `Rule.sources` | `tests/model/test_structure.py`, and the test that a structure keeps what only the clause reads. |
| `idle_parts` (`starts.py`) | 5 tests: a part that only the clause reads is left out of the structure. |
| The checks of `_rule_errors` (the unit; values that move) | The tests of what the compiler refuses. |
| `_rule_expressions` (`values.py`) | The test of a clause that can be outside its domain. |
| The scheduler | 17 or 18 tests of the clause. |
| A step that names the event does not read the clause | The test that a line does not trigger an event that has ended. |
| `notation.walk`, `model_map`, the words of the trigger | The tests of the picture. |
| **The name in `Rule.OPTIONAL`** | **Nothing.** A rule with no such clause has the key with no value, so no test reads a rule without the key. |
| **`run_reads` (`starts.py`)** | **Nothing.** `idle_parts` keeps the parts that the clause reads. |
| **The names of the trigger line in the picture** (`triggers.py`) | **Nothing.** |

The three rows in bold are omissions that no test finds. They are the lists by hand of
[A clause of an event](#a-clause-of-an-event), "Where no single list exists": read each of them for
a new clause. Each omission was judged by the 178 tests of the files that the exercise changed, and
not by the whole suite.
