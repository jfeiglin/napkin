# Brief A4a: the engine at scale

Folder: `scratch/rewrite/a4a/`. Read `briefs/COMMON.md` first. A second agent has brief A4b
(members that come and go, and the map of the present engine code). Do not do its work.

## Question

How does the new planner cut a model into parts, which way does each part run, and what does a run
record? Three things must be shown or measured, not argued.

## Read

- `scratch/rewrite/PLAN.md`: "The approach in six choices" (choices 1 to 3), "A4", "Gate G0" (the
  item on what a run records), and slices S0 to S2.
- `scratch/rewrite/spec.md`: "Flows and algebraic solvers" (the flows, the endpoints, the worked
  network with its three CSV files), "Solver and execution contract", "Open design questions"
  ("Continuously changing inputs"), and the last paragraph of the spec.
- At the base commit: `docs/engine.md`, sections "One moment", "Between moments: the solver",
  "Flows, allocation and coupling", "Tables and tiers", "The run store".
  `napkin/engine/timeline/plan.py` (spaces at 474-545, the refusals at 497, 707, 782, 925, 974),
  `napkin/engine/timeline/component.py`, `reports.py`, `napkin/engine/continuous/system.py` (the
  dense matrix at 152), `napkin/engine/runtime.py` (`Trajectory`), `napkin/engine/report.py`
  (`lagged` at 164), `napkin/store.py` (`key` at 391), `napkin/model/hybrid.py:1-44`.
- `scratch/networks/README.md`, `two_links_trial.py`, `twolinks_model.py`, `baseline.py`, `net.py`.

Work on a copy of the package, never on the checkout:
`git -C /home/user/napkin-base archive HEAD napkin tests | tar -x -C YOUR_TEMP_FOLDER`. Keep each
change as a `.patch` file in your folder.

## Tasks

1. **A real transfer across rows. Do this first.** A table of places: each place has a stock. A
   table of routes: each route row has an `origin` and a `destination` that resolve into the places
   table. One route moves a known quantity from its origin's stock to its destination's stock. Show
   the debit and the credit on the right two stocks. Then reorder the place rows in the file, with
   the links written by row id, and show the same named results.

   The earlier trial did not show this. It read inputs through two links by stand-in rows and ran
   no transfer. If the present table path can run the transfer with a small honest change, make
   that change in your copy. If it cannot, say exactly what blocks it, and show the transfer with a
   standalone layout of your own: two pools of rows, links by id, one sparse network across them.
   That layout is then your proposal for the new engine.

   Then the same with 30,000 places and 35,000 routes: the cost to build and to run.
2. **The rule for connected sets.** Say exactly what joins two members into one set: a flow
   between their stocks, an endpoint that shares, a flow with legs, a rate that reads a moving
   value of the other, a solver that sets rates of both. Each set runs in one of three ways:
   - as one component on the continuous engine (today's general tier);
   - on arrays, for a family of like rows (today's fast tier);
   - with rates from the sparse solver at each moment, held between moments. This is allowed only
     when nothing that the rates read moves between moments.

   Measure where the lines are. Up to what size is one component acceptable, with its dense matrix
   and its allocation inside each evaluation of the rates? Use the present general tier on
   synthetic models that grow. What does a request that moves continuously cost in a small set and
   in a large one? Write the message for each thing that the engine must refuse at scale.
3. **What a run records.** The proposal: the record holds histories, not readings: for each
   recorded value its exact pieces over the run (a constant, a line, a numeric segment that can be
   read at any time), and the trace. A small model records every named value, as `Trajectory` does
   today. A large model records what the request names. A report then computes a lag over a window
   from the pieces. Say what `Trajectory` and the record of the table path (`record=True`) hold
   today. Give the format of a piece. Measure the size and the cost of the record with 30,000 rows,
   when the request names ten reductions over the table and five rows. Say what the key of a stored
   run must cover, and when a stored run can serve a request.

## Rulings that you owe

The layout of the data for links and flows across tables. The rule for connected sets. The limits
that you measured, and the message at each. What a run records, and the rule for the reuse of a
stored run.

## Exit

Your patches and scripts, `measure.py` (makes your whole table again), and `FINDINGS.md` with a
layout note: the arrays, the indexes, and how a planner goes from a model to the three ways of
running.
