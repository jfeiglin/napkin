# Brief: what T left, and what the main session found after it

Read `briefs/COMMON-B.md` first (its rules hold, but for where L works, below), then `PLAN.md`,
"Changes after G0", items 10, 24, 25 and 26, then `briefs/audit3.md`, "What every agent does, this
time": its five rules hold for you. `b1/audit3-t/STATE.md` is what T did and found. Your state file
is `scratch/rewrite/b1/audit3-<agent>/STATE.md`.

## C: a moment's own changes, every reader, and a switch at a moment

Works in `/home/user/napkin`. Owns `napkin/engine/timeline/{ways,run,moment,occurrences,triggers,
saved,component}.py`, `napkin/engine/continuous/`, `tests/reference/{run,evaluate}.py` and new files
in `tests/engine/` and `tests/reference/`. L owns the sharing code: ask for a change there through your
state file.

The rule (PLAN, changes 25 and 26; spec.md:542-544): in a moment the stages commit first and the
flows are shared again after. A rate that the settling decides (a flow's `actual_rate`, a leg's, a
`served_fraction`, an endpoint's inflow or outflow, a declared solver's result), read before that
settling, is the one of the last settling; where something that it depends on changed since then,
it is stale, and the read stops the run by name, with the advice. The owner was asked with "its
store just hit a bound" as an example of such a change, and change 26 applies the same answer to
every change that the next settling takes up:

1. **The clock at the moment.** A keyed read by the time at its key time, and a branch (on the time,
   or on a stored value) in what the rate depends on whose condition changes at the moment's time,
   make the rate stale in that moment's stages, as a store that met its bound there does. Today the
   engine stops for the first and reads the new rate for a branch on the time; the oracle reads the
   old rate, without a word, for both, and for a branch on a store
   (`scratch/rewrite/audit/clock/clock.py`, run with `PYTHONPATH=$PWD`). The engine and the oracle
   must agree: both stop at the same time and for the same reason, or both give the same values.
2. **Every reader.** A firing's capture or start argument that is read after an earlier firing of
   the same conditions changed what a rate depends on (a start whose flow joins one of its stores)
   is a read before the settling: it stops the run too, in the engine and in the oracle. Find every
   other place where a run reads a rate between a change and the next settling, whoever reads it,
   and list them before you change one.
3. **A switch that a stage's time meets.** A branch on a store whose crossing falls on the time of a
   moment fails the run with a wrong message, "the rates switch back and forth", when the store is a
   roundoff short of the switch there; a stage at that time need not read anything
   (`scratch/rewrite/audit/clock/coincide.py`: 2 L at 2 h fails, 1 L at 1 h runs). It fails on
   `8b3a01a` as well. The rule: a run is the same whether a crossing falls on a moment or not; its
   values are the oracle's. Find the mechanism (a segment that starts a roundoff short of a switch
   that it is crossing) and treat it once, wherever a way starts a segment at a switch, as the
   ways already treat a store a roundoff short of its bound.

Rule test: random small models (T's generator is in `tests/engine/test_stale_rates.py`; extend it or
write your own) with branches on the time and on stores, keyed reads by the time, thresholds, rates
and stage times chosen so that crossings, key times and stages fall on one another as often as near
one another, with firings that start flows; against the oracle, straight and with a stop and an edit,
resumed in place and from the saved state. It must fail on the code as it is.

## L: local sharing where the engine and the oracle disagree

Works in its own worktree, `/home/user/napkin-L`, at the commit that holds this brief: run every
command there with `PYTHONPATH=$PWD` and `/home/user/napkin/.venv/bin/python`, and change nothing in
`/home/user/napkin`. Owns `napkin/engine/timeline/{network,selection,plan,sparse,lines,family,
declared}.py`, `napkin/engine/allocation.py`, `napkin/engine/solve/`, `tests/reference/network.py` and
new files in `tests/engine/`. C owns `component.py` and `run.py`: ask for a change there through your
state file, or make it in your worktree and say so there, line by line.

T found these on the code as it is (its STATE, "For the main session"):

1. A route against its request out of a full store: `s0` 10 L in [0, 10 L], SOURCE -> s0 at 0.5 L/h
   with a capacity of 4 L/h, a route s0 <-> s1 with a request of -2 L/h and a capacity of 1 L/h,
   `s1` 0 L in [0, 100 L], and any stage at 2 h: at 2.5 h `s1` holds 1.0 L in the oracle, which
   stops the route at 2 h, and 1.25 L in the engine.
2. A `[0, 0]` junction between a route and a flow with legs into a full store: the engine fails
   "local sharing moves it past its bound at 0 h" (seed 752 of an earlier generator of T's).
3. A ring of stores that local sharing has no answer for: the engine refuses it when it starts the
   sets, before the setup, and the oracle after the setup. Say whether the refusal follows from the
   structure alone; if a setup can change the answer, both refuse at the same point.
4. An endpoint that only a stage's allocation names (it has no setting) has no request in a run with
   flows of occurrences: "has no value yet" (`plan.end_of` at run time, `run.py:497`).

For each: work the spec's answer by hand from its text ("Local allocation", the routes, the
junctions, "Flows created during a run"), say which side departs from it, and fix that side's
mechanism; where the spec does not decide, write the question under "For the owner" and leave both
as they are. Then the rule test: random networks with routes between any kinds of store (stocked,
empty, full, `[0, 0]` junctions), flows with legs into full stores, priorities and allocations that
stages set, read only after a wait (no stale reads), against the oracle in values. T's generator
joins routes only between stocked stores; yours does not. It must fail on the code as it is.

## When you finish

Your report, as in `audit3.md`, with each changed test expectation listed and why.
