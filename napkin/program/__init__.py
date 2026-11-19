"""The program: the one contract between the compiler and the engine.

A program is a typed description of a model as it runs, with no text and no place in a file. The
front end lowers a model to a program; the engine, the proofs and the oracle read programs; tests
build them in Python. It imports nothing of napkin but `napkin.core`.

- `refs`: what an expression reads, each read a structured record (paths, reductions, draws, ...).
- `parts`: the records of the whole language: units, types, values, flows, events, solvers,
  displays, assertions, members, templates and the program.
- `config`: the run configuration: inputs, mode, seed, controllers, limits, budgets, numerics and
  the request of what to record.
- `record`: the record of a run: histories of pieces, the trace, the manifest.
- `check`: the resolver of paths and the invariants that an engine relies on, each with a code.
- `build`: the builders that make programs, with `Builder.finish`, which checks them.
- `canonical`: the canonical bytes of a program and of a configuration, for the key of a stored run.
- `reach`: which events can start and which values each named state can take under a configuration,
  each with its reason: proof metadata (D16), by which nothing prunes a run.
"""
