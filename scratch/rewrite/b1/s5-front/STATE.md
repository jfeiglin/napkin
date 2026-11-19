# S5-F: the front end, sixth slice (solvers) — state (done)

Brief: `scratch/rewrite/briefs/s5.md` (S5-F), with `COMMON-B.md`, `s0-front.md`, `s1.md`..`s4.md`.

## Done

- semantic.py: `SolverOf`, kind `UNKNOWN`, `DeclaredBinding`, `DeclaredRelation` (a constraint or an
  objective), `DeclaredSolver`, `solver_parts`; `Scope.solver`; inputs and unknowns in `syntax`
  under the solver's path; `solver`, `binding`, `unknown`, `determined`; a caller reads unknowns
  (`this.staffing.care`); writes refused (`result_write`); `elapsed`/`delayed` of one refused
  (`history`). `Later` deleted: nothing raised it once solvers lowered (S6/C parts stay `Deferred`).
  `yes`/`no` as a name hints "true or false".
- lowering.py: `solver_of` (build.given/solve_for/unknown/constraint/minimize/maximize), then
  `solvers.problems(program)` after `finish()`, located by origin.
- solvers.py (new): over the program, per solver: classes KNOWN/AFFINE/CONVEX/RELATION through
  formulas (template's and members' own); codes `solver_form`, `nonlinear`, `participant`;
  `two_solvers` member by member (union of flows and stores; event flows too; ends through a
  parameter skipped), only with two or more solver instances; a member-free entry walked once.
- tests/program/examples.py mended (napkin/program/ itself unchanged): network flows and pump power
  without `unit=` (builder gives `Wh/h`, `kWh/h`), readings `0.5`, kW cells `0.008`/`0.006`, strength
  `0.001`. Values unchanged. tests/program + tests/reference 633 passed; test_programs.py 114 on the
  committed engine, 131 on the engine agent's copy.
- tests/language/test_solvers.py (86): 17 examples to their bytes, reordered tables, format, `in`,
  forms accepted, each refusal code with its line. test_yes_no.py (12): front-end port of
  tests/engine/test_binary_controls.py (its edit cases wait for S6; its 0/1 quantity has no form).
- Old S5 refusals removed or moved (test_events, test_lowering, test_semantic -> a status display
  (C), tests/commands/test_compile.py -> a property set by its path (S6)).
- Brief's command: 1715 passed. Ruff check and format clean on every touched file.

## Decisions

- D1 Examples mended to their sources (flows in their stores' unit per hour; cells as written).
- D2 Codes: solver_form, nonlinear (also yes/no and enum unknowns), participant, two_solvers,
  solver_input; solve_for/two_writers/result_write/history reused.
- D3 A rate read in a solver is its own (no other solver's, no local one): else `participant`;
  a constraint or objective that reads nothing determined is `participant` too.
- D4 two_solvers = the oracle's components (any shared store), not only binding ones.
- D5 No static check of stale reads (D5): the engine's, at run time.
- D6 A positive part of a positive part (also `max` of a route leg) is refused, as the oracle has none.

## For the main session

- tests/engine/test_binary_controls.py stays dormant for its edit cases (S6); then delete it.
