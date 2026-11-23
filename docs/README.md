# The documentation of napkin

This page lists each page of the documentation, in the order to read it. Each line says what the page
is for. The words **model**, **run**, **record** and the other terms have the meanings that
[the terms](language/README.md#terms) give.

A new author reads the guide first, then the language. A contributor also reads the engine, the
compiler, [CONTRIBUTING.md](../CONTRIBUTING.md) and the design.

## Start here

| Page | What it is for |
| --- | --- |
| [modeling-guide.md](modeling-guide.md) | Write a first model step by step, check each step, and follow the checklist of a model. |

## The language

| Page | What it is for |
| --- | --- |
| [language/README.md](language/README.md) | Learn what a model is, which files a package holds, the language on one page, and the terms. |
| [language/values-and-types.md](language/values-and-types.md) | Declare values, types, units, members, links, collections, formulas, distributions, tables and status displays. |
| [language/flows-and-solvers.md](language/flows-and-solvers.md) | Declare flows, routes, endpoints, requests and capacities, local allocation and declared solvers. |
| [language/events.md](language/events.md) | Declare events, stages, triggers and occurrences, and use breakpoints, checkpoints and edits. |
| [language/numerics.md](language/numerics.md) | Find how two numbers compare, what a scale changes, and which runs give the same numbers. |
| [language/evidence.md](language/evidence.md) | Write `record` declarations, cite them, and satisfy the datum rule and the evidence rule. |
| [language/changes.md](language/changes.md) | Find each word and form of the old language, and what replaced it. |

## The engine

| Page | What it is for |
| --- | --- |
| [engine/README.md](engine/README.md) | Follow one run from the program to the record: the plan, the moments and rounds, the record, the run store and the studies. |
| [engine/methods.md](engine/methods.md) | Learn the six methods that calculate the stocks between moments, the contacts and the exact stock ledger. |
| [engine/solver.md](engine/solver.md) | Learn how the engine forms the problem of a declared solver, selects the answer, and fails. |
| [engine/verification.md](engine/verification.md) | Find the checks of the engine, the test tiers, the generated corpus and the speed benchmarks. |
| [engine/owners.md](engine/owners.md) | Find the owner of each decision of the engine, and the evidence of each fix to an owner. |

## The tools

| Page | What it is for |
| --- | --- |
| [compiler.md](compiler.md) | Follow the chain from the text of a model to the program and its side table. |
| [cli.md](cli.md) | Use each command of `napkin`, its flags and its output. |
| [python-api.md](python-api.md) | Compile, run, read, play and study a model from Python. |
| [draw.md](draw.md) | Draw the static picture of a model with `napkin draw`, and write its `style.toml`. |
| [extending.md](extending.md) | Find what to change in the code for each kind of new feature. |

## The design

| Page | What it is for |
| --- | --- |
| [design/README.md](design/README.md) | Learn the principles of the design and the chain from the text to the record. |
| [design/decisions.md](design/decisions.md) | Read each ruling of the owner, as it applies today. |
| [design/measurements.md](design/measurements.md) | Read the proofs and the measurements that support the design. |

## Known issues and plans

| Page | What it is for |
| --- | --- |
| [known-issues.md](known-issues.md) | Find the known issues, what to do about each, and the possible future features. |
| [scoping/README.md](scoping/README.md) | Learn how a page plans a future feature before the work starts. |
| [scoping/solver-speed.md](scoping/solver-speed.md) | Read the plan for the speed of declared solvers, and its measurements. |

## The catalogue

These pages are in `scenarios/docs/`. They apply to the packages of the catalogue only.

| Page | What it is for |
| --- | --- |
| [catalogue.md](../scenarios/docs/catalogue.md) | Follow the rules that the tools of the catalogue apply beyond the rules of the language. |
| [conventions.md](../scenarios/docs/conventions.md) | Follow the conventions of the catalogue for the attacker and the defenders. |
| [capabilities.md](../scenarios/docs/capabilities.md) | Find the mathematical requirements that the families of the catalogue share. |
| [ai-operations.md](../scenarios/docs/ai-operations.md) | Learn how each case models the AI agent, and how it compares the AI with a human team. |
| [evidence/README.md](../scenarios/docs/evidence/README.md) | Record the sources, the claims and the assumptions of a package with the evidence tools. |
| [deviations.md](../scenarios/docs/deviations.md) | Compare the policies, units and outputs of the four studies with the earlier catalogue. |
| [recovery-ports.md](../scenarios/docs/recovery-ports.md) | Read the results of the port of each package from the earlier catalogue. |

The index of the packages is [scenarios/README.md](../scenarios/README.md).
