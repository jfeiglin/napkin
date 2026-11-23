# The recovery ports from the earlier catalogue

This note records how each package of the earlier catalogue came to the current language, and the
checks of that port. It records the state at commit `6f4134a`. The branch of the packages starts at
the engine handoff `05d25e7`. The comparisons with the earlier catalogue use commit
`8488047dbb7eafee1f5582cf59839c6bea0cf8cd`.

The comparison of each package says what its inputs mean. Recovery reacts to the current stocks, the
observations and the conditions of the events. Thus an edit of a capacity, a later report or another
decision of an operator can change the events after it.

| Package | Events and model | Comparison with the earlier catalogue |
| --- | --- | --- |
| Reservoir | The decision of the operator changes the gate. The spill and the time at risk after it depend on the level of the water that results. | 273 readings, also the analytical sweep and both choices of the operator. The report is `docs/migration/reservoir.md` at commit `e60e438`. |
| IV supply | An input supplies the condition of a lot at its release. Quarantine uses the reserves that the lot touches, starts a reconciliation and changes when qualified supply can come back. The clinical results follow the inventory and the demand. | Seven fixed and four edited runs. All 3,349 physical readings that compare and all 88 lists of recovery events agreed. In each run, three clinical values with a lag have no history at 0 h. There the earlier report gave zero. [Package results](../iv_fluid_shortage/README.md) |
| Defensive response | The observed workload of incidents changes the attention that the team wants. The actual attention moves toward it over time and changes the rate of remediation. | Four supplied workloads, five values and ten times. All 200 readings agreed with the earlier equations. The largest absolute difference in attention was 5.09 × 10⁻¹¹. [Package comparison](../cyber_learning_loop/defensive_response/README.md) |
| Water utilities | A first interruption of service makes the repair jobs in the same stage. The return of control depends on the crews and the parts. When the stored water runs out, an advisory can start. To clear the advisory, the model needs restoration, supply and the delay of the laboratory. | All 768 readings agreed: eight civilian values at 0, 24, 72, 168, 720 and 2,160 hours in all sixteen places. Ten independent analytical cases check the queues, the water balances, the relief and the losses. [Water tests](../water_controls_wipe/tests/test_service_recovery.py) |
| Heat and power | The model follows the interrupted supply, the restoration work, the checks of the utility, the heat exposure, the cooling and the care. | 33 endpoints of the three published responses agreed at the archived display precision. [Package migration and edited-response checks](../heat_wave_blackout/MIGRATION.md) |

## How to read the comparisons

The water fixture uses the earlier run "Delayed response" without more incidents. A separate test of
Juneau delays the first report until 4 h, and recognition follows at 28 h. A field report of 160
work hours at 200 h opens the repair queue again, and the system goes back to manual operation.
Automatic service starts again at about 204.21 h, and the second clearance of the laboratory follows
48 h later. Without that field report, the run has one restoration and one clearance. The test also
counts each posted work hour. [Edited incident and paired control](../water_controls_wipe/tests/test_service_recovery.py)

An edited heat run starts private relocation at 0 h, at the same time as the observed outage. It
starts outreach at 1 h. The test finds positive relocations in the first hour, and it reads the number
of people that outreach protects at 1 h. This test found an error in the order at one time: the
relocation stood down before the outage finished its start. The stand-down now depends on the
restoration event. [Opening-stage and outreach test](../heat_wave_blackout/tests/test_briefs.py)

The water comparisons accept a relative error of 10⁻⁸, with an absolute floor of 10⁻⁸ in the reported
unit. The sums of the repair queues accept 10⁻⁵ work hours absolute at zero, because each queue has a
comparison scale of 1,000 work hours. An observation counts only when both the earlier and the new
run reach the horizon. To make the earlier inputs and values again, do these steps:

1. Make a checkout of the archive commit: `git worktree add /path/to/archive ARCHIVE_SHA`.
2. In that checkout, run the script `scratch/rewrite/a5/check_water_recovery.py` with a checkout of
   commit `8488047`.
3. In the current checkout, run the deep tests of the water recovery.

```sh
python scratch/rewrite/a5/check_water_recovery.py /path/to/legacy-checkout --jobs 4
python -m pytest -q --no-focused -m deep scenarios/water_controls_wipe/tests/test_service_recovery.py -n 6
```

The earlier catalogue also made disruptions: it chose future actions of an attacker. The recovery
packages accept a first incident, reported setbacks, the condition of a lot or an aggregate workload.
The response changes when these inputs change. The earlier policies of the attacker and their
comparisons belong to the earlier study. The current readings give the supplied recovery cases.

The uncertainty comparison of Washington, DC uses the current random sampler. It uses the PERT ranges
of the earlier delayed response, and a documented comparison of the early response. Two matched draws
of each response completed 2,160 hours. The study of 50 draws for each response was not part of this
check. [Washington sampling inputs and commands](../water_controls_wipe/variants/washington_dc/README.md)

## What the port found

In Jamestown, a literal copy of a synchronous effect made an intermediate round. In that round the
controls had failed, but the repair queue was still empty. Thus the run restored the service without
cause, and it lost no water service. The migrated stage of the outage now makes the queue together
with the loss of the controls. The first 24 h now give 2.4973326 million US gallons of unmet demand,
as in the earlier run.

In Washington, DC, a full store downstream kept a positive residual on its books while the allocation
held it at its bound. A method of the engine used that physical residual to select the refill branch.
At six minutes, the published purchase rate was 2.726 million L/h, but the purchase ledger implied
5.520 million L/h. The method now selects the branch from the allocation rate, and the rate of
2.726 million L/h and its ledger entry agree. In the completed run, the cumulative shortage was
59.3250148 million US gallons at 2,160 h. At 72 h, 1,121,613 residents were under an advisory. Both
values agree with the earlier run. [Method and reference regression](../../tests/engine/test_held_branch_velocity.py)

Lehigh found a second error of branches. The advisory was already active, but the scheduler still
forecast the stock comparison of a guard against a loss of pressure. That guard first needed a
potable status. Thus the clock moved forward one representable tick at a time. The scheduler now
ignores a branch while a held condition excludes it, and the run reaches its horizon. A change of the
held condition starts the forecast again. [Trigger regression](../../tests/engine/test_inactive_guard_contacts.py)

The follow-up at commit `c328fbb` checks a much slower change. An inflow and an outflow that almost
balance leave a small physical surplus. At first, the stock is inside its comparison band of zero. As
the transfers add up, the stock crosses the edge of that band, and the dependent meter changes from
1 L/h to 2 L/h. The methods Component, Sparse and MovingDeclared each record 1 L/h just before the
located switch and 2 L/h at it. Their totals at 2,000 h agree with the independent result of 3,000 L
to within 0.000002 L. The same check runs from a saved checkpoint.
[Cross-method regression](../../tests/engine/test_held_branch_velocity.py)

The script `scratch/rewrite/a5/artifact_parity.py` at commit `ARCHIVE_SHA` compares a run from the
source with five new consumers of the compiled program. Each consumer has only the program and the
saved configuration of the run in its folder. File access controls refuse the model text and the
data of the package, also the local units and the evidence. For each reading, the check compares
the value, the unit and the exercised citations. It also compares the definitions of the evidence,
and the names and the times of the events in their order.

| Case | Readings | Event starts, in order |
|---|---:|---:|
| Reservoir through 120 h | 6 | 1 |
| Juneau recovery through 220 h | 9 | 26 |
| IV release, product review and confirmed lot discrepancy through 32 h | 15 | 9 |
| Defensive pressure through 4 h, with formula switches at 1 h and 3 h | 10 | 0 |
| Heat recovery through 0.75 h, with a safety hold from 0.25 h to 0.5 h | 10 | 3 |
| **Total that agreed** | **50** | **39** |

The water dashboard reads the selected time from the same run, also a time with a fraction of an
hour. [Dashboard](../water_controls_wipe/ui/README.md)

## Do the migration check of the examples again

The script `scratch/rewrite/a5/paired_migrations.py` at commit `ARCHIVE_SHA` checks the examples. It
archives both revisions and runs each in its own Python process. It checks the reservoir in
`examples/`, which is the package that users run. Twelve draws of the piano tuners agreed at 0, 4,380
and 8,760 hours. Twelve configurations of the reservoir agreed at seven times, and the 24 sampled and
analytical controls passed. The script refused both a wrong final count of tunings and a run that
failed exactly at its horizon. Run it in a checkout of the archive commit:

```sh
python scratch/rewrite/a5/paired_migrations.py --candidate HEAD
```

## The check of the catalogue

At commit `6f4134a`, the catalogue had 19 entries in four packages, with the water recovery in 16
places. All 60 named runs of that time completed. The publisher made the 19 reading files, the 19
evidence dossiers and the source manifest again, byte for byte. [Current catalogue](../README.md)

The last numerical change is commit `c328fbb`. Commit `7f08701` makes the assertion of the rate at a
located exit of a comparison band stricter. The full deep tier passed 25,929 tests in 869.63 seconds
on ten workers. Each heat case passed, also four runs with changed inputs that had shown errors of
allocation or of the model. The archived comparison still uses the original display precision.

The full regular tier passed 11,839 tests on four workers, with one macOS skip of a Linux test of
process information. The budget check measured 178.411 seconds against a limit of 180 seconds. It
confirmed all 300 rotated seeds with no truncated comparison. When each test case went to a worker
separately, the tier took 214.397 seconds on the same computer. When each test file stayed on one
worker, the water tests used their completed regional run again. Both timings cover the same cases
and assertions. Thus `tools.check` uses scheduling by file for the full regular tier.

```sh
python -m tools.publish --check --jobs 4
python -m pytest --no-focused -n 4 --dist loadfile -m 'not deep' --junitxml=regular.xml -o junit_family=xunit1
python scratch/rewrite/audit/port_corpus_results.py regular regular.xml --full-suite
python -m pytest --no-focused -n 10 --maxschedchunk=4 -m deep scenarios tests
```

Run the script `scratch/rewrite/audit/port_corpus_results.py` in a checkout of commit `ARCHIVE_SHA`.

The speed campaign of six workloads belongs to the earlier engine handoff. Its ratios apply to the
revisions that its report names. The check on the branch of the packages covered the runs of the
catalogue, the parity, the publication and the time of the test suite. The report of the engine
timing and of the measured commits is `scratch/rewrite/audit/engine-finalized-results.md` at commit
`ARCHIVE_SHA`.
