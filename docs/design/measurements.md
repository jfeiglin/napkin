# Measurements and proofs

This page gives the proofs and the measurements that support the design. A measurement is of one
case on one machine. It shows a capability and a cost, and it is not a guarantee. The work on speed
is separate from the behavior that [decisions.md](decisions.md) settles. The words in **bold** type
have the meanings that [the terms](../language/README.md#terms) give.

[docs/engine/verification.md](../engine/verification.md) gives the tests that check the engine
today. [docs/scoping/solver-speed.md](../scoping/solver-speed.md) gives the measurements of the
declared solvers at 3,000 and 30,000 places.

## What a proof establishes

A proof of the compiler covers each permitted way in which a value can change
(`napkin/program/proofs.py`, `never_falls`). The proof is conservative: a change that it cannot
settle counts as a fall. So "never falls" is proved, and "can fall" says only that no proof showed
the opposite.

- A tally that has only additions that are not negative can have a reporting lag. A shared
  **stock** that another **occurrence** can drain needs a proof that covers that withdrawal too.
  Without a proof that the value never falls, a lag is not valid ([D10](decisions.md#d10)).
- Evidence can document separate populations, or explain why an estimate is absent. A citation
  does not prove a numeric invariant.
- A proof over a model with occurrences covers each place that can write the value. These places are
  each flow of an **entity** or of an **event**, and each statement of each **stage**. A stock that
  an event can drain never counts as a value that never falls.
- An **edit** at a **breakpoint** is one more writer of the value. An edit that breaks the proof
  withdraws the proof for the edited **run** ([change 15](decisions.md#change-15)).

**Conservation** concerns the balances of stocks. For each internal transfer, the source loses the
amount that the destination gains. Material in active occurrences still counts at the horizon. A
model can conserve each unit while a delivery waits forever, so finite completion is a different
property.

### Cannot fire, and did not fire

For a **configuration**, the compiler keeps what it can prove about which events can start
(`napkin/program/reach.py`, [D16](decisions.md#d16)). This includes conclusions from the finite
transitions of events and enum states. "This event cannot fire with the plant closed" and "this
event could fire, and did not fire in this run" answer different questions. A trace gives only the
second. The first is proof information for callers and evidence displays. Nothing prunes a run by
it.

## What the experiments established at G0

Six prototypes tested the design outside the engine before the build (gate G0, 2026-11-18). They ran
on one machine: 4 shared cores, Python 3.13, and SciPy 1.18.1 with HiGHS 1.12.0. Their results
show capabilities and costs at that time. After G0, the build added the parser, the type checker,
the engine and an independent reference interpreter (`tests/reference/`).
[docs/engine/verification.md](../engine/verification.md) gives the tests that compare them today.

The scripts and the results of the six prototypes are in `scratch/rewrite/` at commit `af5428b`
([the archive](README.md#archive)). The folders are `a1`, `a2`, `a3`, `a4a`, `a4b` and `a5`.

### The notation

A prototype parser read all 27 code blocks of the previous version of the spec and 154 pieces of
inline notation. It refused the 72 pieces that the spec refuses, each with its message. That parser
used an earlier rule for units and had no `if` in a stage. No type checker ran at G0: a person
applied the type rules to 13 small models by hand.

### The rules of execution

A small reference interpreter, in exact fractions, reproduced the numbers of 31 worked cases from
the previous version of the spec and from its review. It calculated the sharing for a whole
connected set of flows at once. The rule of G0 is local sharing at each endpoint
([change 2](decisions.md#change-2)). None of the 31 cases has two sharing endpoints in a row outside a
**solver**, so the cases do not tell the two rules apart. At G0, the two-junction example had only a
calculation by hand. The interpreter also carried an absent value through arithmetic, and gave a
stale solver result with a warning. G0 replaced both rules ([D4](decisions.md#d4),
[D5](decisions.md#d5)).

### The solver

A prototype of the selection order, on one kept instance of HiGHS, gave each expected answer of the
spec for a solver:

- the staff hours
- the pump
- the provider
- both rows of the case with two bottlenecks
- the rates and levels of the worked network in W and in kW.

| What was measured | Result |
| --- | --- |
| The fair-sharing step alone, 3,000 places, four cases with 552 to 1,880 claims short | 50 to 172 linear programs; 1.1 to 4.4 s |
| The fair-sharing step alone, 30,000 places, one case with 4,315 claims short | 467 linear programs; 128 s |
| The same size with a heavier shortage | It failed partway: a later program was infeasible |
| The final distance step after fair sharing, 3,000 places, in the prototype | 38 s with the QP algorithm of HiGHS. The algorithm of the prototype did not converge |
| The final distance step with inequality rows, 200 small random cases | It agreed with an exact reference to 7e-9 |
| The solve library of the build, the four cases at 3,000 places, the whole selection order | The final distance step after fair sharing converged in 2.1 to 5.3 s (98 to 177 Newton steps), with no fallback. The QP algorithm of HiGHS, its exact fallback, did not finish on these faces in this run |
| Flows that join and leave a kept problem: 2; then 1.5 each; then 2; then none | Each answer equal to that of a problem formed again. At 30,000 places, 300 flows joined in 0.90 s, against 6.12 s for a problem formed again |
| A flow that takes more than its **request**, in a bridge of five **routes** | Total unmet 4.65, against 9.20 with each use capped at its request |

These results show specific capabilities and costs. They do not show that each network of 30,000
places finishes in a given time. They are the reason that the two costly steps have budgets and
stop by name ([D0](decisions.md#d0), [change 4](decisions.md#change-4)).

### The scale of the engine

A layout with pools of rows, links by row id and one sparse network moved a known quantity between
two rows of one table. It put the debit and the credit on the correct two stocks, before and after a
new order of the rows. The table engine before the rewrite refused that model. With its refusals
removed, it gave a wrong answer.

The same layout ran 30,000 places and 35,000 routes to 48 hours in 1.4 s, with rates that change
only at events. For a rate that reads a moving quantity, one connected component of the engine
before the rewrite took 8 to 16 s at 200 stocks. At 600 stocks it took 683 s in one case, and it
used all of the memory in two cases. A sparse integration of 60,000 stocks reached 48 hours in 32 s
while no stock rested at a bound.

These numbers belong to one implementation. They are not limits of the language. A large valid
model can take longer, or stop with an explicit failure of time, memory or accuracy. Its size never
changes its equations or freezes a moving rate ([D3](decisions.md#d3)).

### Members that come and go

A prototype ran occurrences whose flows join and leave a shared network. It gave the numbers of the
spec for the table of current flows, the frozen request, the shared limit and the **trigger** at
hour 10. When the prototype did not treat a join as a change of what the trigger reads, the trigger
fired at hour 6. The tank then held 12 L.

The prototype kept the total of each endpoint as an exact sum. With that, each rate was equal to
that of a problem formed again, in 59 of 59 checks. A running floating-point total differed after
9,451 of 10,000 joins and leaves. In Python on a busy machine, 100,000 starts and finishes with
1,000 active occurrences took 53 s under a shared limit that does not bind. Under one that binds,
they took 118 s. At G0, the rule that a proof covers the flows of events rested on that design and
on two runs.

### The catalogue

A translator changed 6,691 of the 6,960 logical lines of the models of that time mechanically
(96.1%). Then six models had a full translation by hand. A check of meaning passed on each. It
covered each number with its unit, each text, the kind of each name, and the outputs that the old
compiler proved cumulative. The same check refused a translation that was wrong on purpose. That
translation changed the accumulated unserved volume of the water model into a formula of the present
shortfall. At G0, no translated model had run, and the translations used spellings that G0 replaced
([change 1](decisions.md#change-1)).

## Delivery experiments on the engine before the rewrite

At commit `13b0969`, the engine before the rewrite ran experiments of delivery in memory. They used
channels declared in advance, and a gate for the delayed start. Both deliveries requested 10 L/h.
The figures are litres for each delivery and hours to finish.

| Case | Delivered at 1 h, A / B | Finish, A / B |
| --- | --- | --- |
| Separate batches of 20 L | 10 / 10 L | 2 / 2 h |
| A shared supply of 40 L with a total throughput of 10 L/h | 5 / 5 L | 4 / 4 h |
| The same shared supply, with B starting at 1 h | 10 / 0 L | 3 / 4 h |

For the delayed start, the totals of A and B at hours 2, 3 and 4 were 15/5, 20/10 and 20/20 L. The
checks of conservation passed, and the traces of completion agreed. These results show delivery with
flows declared in advance. The experiment did not include flows created during a run, or the
throughput of a solver.

The proofs and the readers of the timeline of that engine assumed a fixed model structure. Its
general continuous path built a dense matrix of stocks by flows. These limits matter when a reader
compares the delivery results with the examples of flows that a run creates.

## The speed of the engine after the last audit

The last audit measured four workloads of the engine against a baseline. Each median ratio was
below the limit of 1.05.

| Workload | What is timed | Median ratio, candidate / baseline |
| --- | --- | --- |
| Sparse tanks | Run and record | 1.036 |
| Component tanks | Run and record | 0.983 |
| Events | Run and record | 0.972 |
| Declared solver | Run and record | 0.80 |
| Declared solver | Build, plan, run and record | 0.83 |

A ratio below 1 means that the candidate is faster than the baseline.

- **The baseline** is commit `6202824`. **The candidate** is commit `4b372a0`.
- **The machine** was macOS 15.1 on arm64, with Python 3.13.16 and one thread for each library of
  linear algebra.
- **The driver** is `tools/bench/port_benchmark.py`, in its phase `final`. It ran three matched pairs
  for each workload, with the order alternating: the baseline first, then the candidate first, then
  the baseline first.
- **The ratio** of a pair is the time of the candidate divided by the time of the baseline. The table
  gives the middle of the three ratios.

The workloads are scripts in `tools/bench/port/`:

| Workload | Script and arguments | What it calculates |
| --- | --- | --- |
| Sparse tanks | `s1-engine/bench_moving_tanks.py --tanks 12 --hours 12 --method sparse` | 12 independent tanks fill from `SOURCE` for 12 h, with a request that reads the moving water. The Sparse **method** runs each tank. The script checks each reading against the closed form. |
| Component tanks | The same, with `--method component` | The same tanks on the Component method |
| Events | `s4a-engine/bench.py 1200 48 12` | 1,200 places to 48 h. A clock starts an event at each place every few hours, and each occurrence owns a flow of 1 L/h for one hour. |
| Declared solver | `s5-engine/bench.py 3000 3500 1500` | A network of 3,000 places, 3,500 routes and 1,500 sources with one declared solver that minimizes the total unmet need. At 24 h a stage cuts the supply to 0.8, and the solver solves again. The run goes to 48 h. |

The seconds of each pair, baseline / candidate:

| Measurement | Pair 1 | Pair 2 | Pair 3 |
| --- | --- | --- | --- |
| Sparse tanks, run and record | 1.890 / 1.970 | 1.901 / 1.970 | 1.908 / 1.975 |
| Component tanks, run and record (two runs in each batch) | 1.100 / 1.081 | 1.105 / 1.095 | 1.109 / 1.075 |
| Events, run and record | 230.0 / 223.3 | 229.4 / 223.1 | 227.3 / 222.5 |
| Declared solver, run and record | 8.161 / 6.582 | 8.246 / 6.604 | 8.206 / 6.559 |
| Declared solver, build, plan, run and record | 9.376 / 7.799 | 9.459 / 7.811 | 9.424 / 7.773 |

The table of the campaign, its raw samples, schedules and calibrations are in
`scratch/rewrite/audit/owner-fixes/final/mac/` at commit `af5428b`: `final-speed.md`, and
`final-speed-raw.zip` (SHA-256
`e32c9df76d73c497db0f5f051bd2ff1791e9135db0347967ffa384064d5009cc`).

## A stock at its bound

An experiment made a trigger wait for the solver to report that a stock reached its bound.
A tank started with 1 L. Its outflow rate was its remaining volume divided by 1 h. Its exact
volume stays positive at every finite time. At `rtol = 1e-6` and `atol_factor = 1e-7`, the
polynomial inside a Radau step reached zero at 24.767623278 h. The empty-tank event fired.
The exact volume at that time was 1.7521e-11 L.

The same experiment covered 24 water runs and six displayed values per run. Each absolute
tolerance factor was one tenth of the relative tolerance. At `rtol = 1e-7`, all 144 displayed
values matched the contact experiment at `rtol = 1e-9`. At `rtol = 1e-6`, eight Cape May runs
showed an economic loss of $36,000. The tight setting showed $35,000 in each run.

In another test, a stock stayed 1e-12 L above its lower bound. The trigger waited for contact.
The same comparison in a stage guard and a public formula returned true, and a flow switch let
1 L move. A design that uses bound contacts must give triggers, stage guards, solver switches
and historical readers the same answer at the same time and round.

## Joining adjacent formula fits

We tested joining fitted formula pieces across ordinary solver-step boundaries. The experiment
kept event times, contacts, jumps and previously observed starts. For each candidate it fitted
one polynomial over the combined span and checked the error on both original segments.
Both runs used the tight defaults and a disabled run store. The table gives CPU time for the
whole simulation, including checks on candidates that the recorder rejected.

| Case | Existing boundaries | With joins | Record pieces before and after |
| --- | ---: | ---: | ---: |
| Workforce prototype, 5 years | 8.904 s | 9.322 s | 45,586 → 27,882 |
| Heat wave, 200 h | 54.358 s | 58.031 s | 85,354 → 71,250 |

The traces matched in both cases. In heat wave, a change of 3.628e-12 in a fitted rate
was multiplied by about 931 people. At 39.188080006 h the stored value of
`confined_65_to_74.die_well.capacity` differed by 3.378e-9, above its 1e-10 allowance.
The public reading there was identical. The recorder retains its existing formula boundaries.

## Composing a sum of many stock histories

Revisit this design when a real model has a fixed sum over about 50 collection members.
Across 210 catalogue runs, the largest such sum had five members, in Washington DC.
All catalogue reductions together used 5.60 CPU seconds. The immediate benefit is in
the synthetic `instances` benchmark.

For each interval between input changes, express the members' recorded polynomials in the
same time coordinates. Add their coefficients in the existing pairwise sum order. When one
member changes, recompute its path to the root. Use the configured tolerance and the sum's
own scale to bound the numerical error, including cancellation. At a change or cutoff, read
the landed values with the ordinary evaluator. The evaluator also handles missing coverage
and any interval where the arithmetic cannot establish the error bound. In particular,
a moving stock can carry an exact rational remainder. The ordinary fitter preserves how the
stock uses that remainder between postings. The recorder still owns observed starts and the
piece budget.

At 100 cells, a complete run took 71.29 CPU seconds. Its record matched the reference for all
84,000 pieces and 717 trace entries. The two global sums took 25.30 CPU seconds across 292
observations in a separately instrumented run. Replaying their actual inputs took 1.68 CPU
seconds for composition, including changes to previously observed inputs. Applying the native
fitter to 1,878 affected intervals, reading 2,094 landed points and finding those intervals
added 1.22 CPU seconds. This gives a **projected whole-run saving of 31.4%**. A fallback for
an entire observation would retain 24.70 seconds of the original sum work. The interval
fallback accounts for the difference.

The engine still uses its existing sum implementation. The 31.4% figure is an external
replay estimate. A production speedup remains unverified. Before adopting the design, time
the whole engine, verify small collections and compare the first budget excess across a
checkpoint, including postings that land exactly at the cutoff.

## Recording a moving solver at an unrelated moment

We counted incoming history writes on the 25-cell `instances` case at `367040c`. Each cell
has its own solver. The budget check before a moment asked every moving cell for its history.
This caused all 900 writes inside an open step. The other 742 writes came when a cell completed
its step. Formula assembly subsequently read those pieces.

The solver now books each incoming physical transfer at the same time as before. A reader
at a moment can use the dense solution directly. When the solver completes or retires a step,
it writes that step's history. A checkpoint takes its own copy of the accepted prefix. A terminal
failure keeps the prefix that the solver has already booked. The public record and the
checkpoint expose a curve only through the accepted cutoff.

Before an ordinary moment, the recorder first tries to prove that all the pieces will fit.
Its bound includes requested formulas and their inputs. If necessary, it uses the openings
of the prepared solver steps to tighten the bound. If the bound still cannot prove room,
the recorder assembles the actual histories in a private copy and applies the usual first-excess
rule. Both that copy and the final record use the same fitted coefficients and piece starts
for a given solver step. Checking the budget does not post a second transfer or insert a
new boundary into the live trajectory.

A private check keeps the rows that it counted for each open step. When the solver later
writes those rows, the recorder compares the step, row positions, and exact posted values.
It can reuse counts for intervals that end strictly before the first difference. A shorter
publication, a replacement step or a reordered posting limits the reuse. A restored run
starts without this information. The checkpoint format stays the same.

On the 25-cell case the solver fitted 817 whole steps and no partial step. The budget
check fitted 437 of those steps first. Each completed step reused its earlier fit.
There were no live history writes from the budget check.

On the five real piece limits, every live record was byte-identical to its own unlimited
record trimmed to that limit. In Juneau, 923 pieces covered 109.692307680 h, up from
103.2 h. The new record had 18 fewer charged starts through the later cutoff. The other
four limits stopped at the same time as before. In the occurrence-alias fixture, every
limit from 1 through 182 preserved the first excess, charged starts, trace and coverage.
At limit 51, both records were byte-identical and stopped at 1 h. The largest difference
in a curve inside a cutoff was 7.11e-15 L, in `yard.sink` immediately before 3 h.

The 5-year workforce prototype illustrates the cost of an inconclusive bound. All 103
checks with a pending step required an exact private record. Those private checks used
6.20 CPU seconds in a separate instrumented run. The isolated whole run went from
8.95 to 14.84 seconds and saved two pieces, from 45,577 to 45,575.

For the `instances` measurements, each process used one numerical-library thread and
the run store was off. Each pair gives the measurements before and after the change.
Times are in CPU seconds. The function times include their callees and overlap.

| Work | 50 cells | 100 cells | 200 cells |
| --- | ---: | ---: | ---: |
| Complete profiled run | 14.87 → 11.38 | 60.60 → 41.32 | 287.67 → 192.97 |
| Sparse solver history fit, `Sparse._record` | 5.40 → 1.16 | 20.87 → 2.62 | 78.80 → 5.94 |
| Budget check, `Recorder.check_budget` | 10.63 → 5.65 | 51.57 → 24.78 | 268.58 → 136.31 |
| Assembly of the two collection sums | 4.17 → 3.12 | 25.02 → 14.93 | 164.46 → 80.41 |
| Stored pieces | 28,013 → 21,213 | 84,000 → 56,400 | 280,007 → 168,807 |

At 200 cells, the budget check used 50.59 CPU seconds to bound the piece count in
`Recorder._fits_bound`. Complete assembly of the two sums grew 4.79× and 5.39×
with successive doublings. The solver's own history fit grew 2.26× and 2.27×.
