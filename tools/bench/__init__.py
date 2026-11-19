"""Measure the compiler and the engine on a set of workloads: python -m tools.bench
[--scenario ID] [--runs first|all] [--example] [--family NAME] [--sizes N,N] [--repeats N]
[--samples N] [--jobs N] [--survey] [--timeout SECONDS] [--out FILE].

The harness records times and memory, prints a short table and, with `--out FILE`, writes one JSON
document. It asserts no time: a gate reads the document and judges it. No test, renderer or tool
reads its numbers.

The workloads (`workloads.py`):

- the catalogue's models, found with `tools.catalogue.entries` and named with `--scenario ID`
  (repeatable; a package with variants gives each of its variants). The catalogue is opt-in, because
  its models are slow: without `--scenario`, no model of the catalogue is measured;
- the examples, with `--example`: each `examples/<name>/model.scn`, as `examples.<name>`;
- the synthetic families, with `--family NAME` (repeatable) at each size of `--sizes` (default 10,40):
  models made as text in a temporary folder, `<family>_<n>/model.scn` (`families.py`). The families
  are `instances`, `aggregate_output`, `aggregate_guard`, `aggregate_feedback`, `stiff`, `events`,
  `rationing`, `priority`, `compartments` and `formulas`, in the language of the rewrite, and the four
  families of copies again with their members from a table (`table_instances`,
  `table_aggregate_output`, `table_aggregate_guard` and `table_aggregate_feedback`); the docstring of
  each says what it stresses.

`--runs first` (the default) measures the first named run of each model (its default run when it names
none), and `--runs all` every run. With no workload, the command stops.

Three fresh processes measure each workload and run (`measure.py`), and the document holds, for each:

- `compile.cold`, from the first process: the seconds of `napkin.load_scenario`, the seconds that the
  compiler's modules took to load before it, and the peak memory of the process in MB. The compile of
  a model is measured once, for all its runs;
- `values.one_run.cold`, from the second: the time to the first result. The seconds from the start of
  the process to the end of the run (the imports, the compile and `napkin.run`), split in `parts`,
  and the peak memory;
- `values.one_run.warm`, from the third, after its compile: the seconds of each of `--repeats`
  (default 3) repeats of the run, their median and their minimum, the peak memory of the process, and
  the `size` of the run: its templates, members, values, flows and events, and the histories, the
  pieces and the trace entries of its record, by kind. This is the engine alone;
- `values.one_run.report`, from the third: what a report of one run costs, measured once: the report
  (`napkin.report`) of every named value at the start and the horizon, with the evidence trails and
  the near-ties;
- `values.one_run.where`, from the third: where the time of one more run and its report goes, under
  cProfile, in groups. A group is a role: `analysis` (what the compiler, the program's checker and its
  proofs find out), `expressions` (the evaluation of expressions, collections and reads), `field` (the
  rates: local sharing, the network, the declared solvers and the solve library), `solver` (the steps
  of the integrators and the roots), `linear_algebra` (factorizations, solves and matrix
  exponentials), `scheduler` (the timeline: the loop of a run, the moments, the occurrences, the
  triggers and the record), `reporting` and `other`. `measure.FILES` says which files have each role
  in this revision, and the document holds that list (`groups`), so the documents of two revisions
  compare by role when a change moves code between files. A function of C that factorizes or solves
  is `linear_algebra` whatever calls it. `own_seconds` of a group is the own time of its functions.
  `seconds` and `share` add the helpers: a function of no group (a library, the interpreter, another
  function of C) gives its time to the functions that call it. The profiler slows short functions
  more than long ones, so the shares are a guide and not a measurement;
- `values.every_run`, from the third, only with `--survey`: the seconds of one run of each run of the
  model, in the model's order, with its histories and its trace entries, and the name of the slowest;
- `values.batch`, from the third, only with `--samples N`: a Monte Carlo study of N samples of one
  run (`napkin.spread.spread`) on `--jobs` processes (default 1), of the values that the run names at
  its horizon. The run is the one that the record measures, or, with `--survey`, the slowest run of
  the model. `samples_per_second` is the samples over the whole study, its central run included. With
  more than one process, the study runs twice and the numbers are of the second: the first starts the
  processes of the pool (`first_seconds`). A run that draws nothing is skipped, and says so.

One run and a batch are apart, and cold and warm are apart, so no number adds two of them.

A measurement that fails is a record, `{"failed": "<ExceptionType>: <message>"}`, and the harness
goes on: a model that does not compile, a run that stops, a process that ends before its result, and
a process that takes more than `--timeout SECONDS` (default 600), which is stopped. The third process
saves each measurement as it makes it, so a slow study loses no warm run. A measurement that needs a
failed one is not tried: its record repeats the failure and names its stage (`from`). The command's
exit status is 0 when the harness itself worked, whatever failed in a workload.

The document also holds the commit of the checkout and whether its tree is dirty, the machine as the
run store keys it (`napkin.store.ENVIRONMENT`), the number of processors, and the settings. Each
process runs with the run store off, so every run is simulated.

The cost: each run of a workload takes three compiles and `--repeats` + 3 runs, one run of each run
of the model with `--survey`, and the samples of a study. A study on several processes runs twice,
and takes one compile more in each process. With `--runs all`, each more run of a model takes two
compiles more.
"""
