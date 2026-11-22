# Scenario ports from the historical catalogue

The scenario branch starts at engine handoff `05d25e7`. Historical comparisons use `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. The comparison for each package specifies what its inputs mean. Recovery responds to current stocks, observations and event conditions. A capacity edit, a delayed report or a different operator decision can change subsequent events.

| Package | Event and model relationship | Historical comparison |
| --- | --- | --- |
| Reservoir | The operator's decision changes the gate. Subsequent spill and risk time depend on the resulting water level. | 273 readings, including the analytical sweep and both operator choices. [Report](reservoir-package-migration.md) |
| IV supply | Lot condition is supplied at release. Quarantine consumes the affected reserves, prompts reconciliation and changes when qualified supply can return. Clinical impacts follow inventory and demand. | Seven fixed and four edited runs. All 3,349 comparable physical readings and 88 lists of recovery events matched. Three lagged clinical outputs in each run have unavailable prehistory at hour zero, where the old report supplied zero. [Package results](../../../scenarios/iv_fluid_shortage/README.md) |
| Defensive response | Observed incident workload changes the desired attention level. Actual attention adjusts over time and affects the remediation rate. | Four supplied workloads, five observables and ten times. All 200 matched the corresponding historical equations. The largest absolute attention difference was 5.09 × 10⁻¹¹. [Package comparison](../../../scenarios/cyber_learning_loop/README.md) |
| Water utilities | An initial service interruption creates the repair jobs in the same stage. Regaining control depends on crews and parts. Running out of stored water can start an advisory. Clearing it requires restoration, supply and the laboratory delay. | All 768 readings matched. The fixture covers eight civilian outcomes at 0, 24, 72, 168, 720 and 2,160 hours in all sixteen places. Ten independent analytical cases check the queues, water balances, relief and losses. [Water tests](../../../scenarios/water_controls_wipe/tests/test_service_recovery.py) |
| Heat and power | The model follows interrupted supply, restoration work, utility checks, heat exposure, cooling and care. | 33 endpoints across the three published responses matched the archived display precision. [Package migration and edited-response checks](../../../scenarios/heat_wave_blackout/MIGRATION.md) |

## Interpreting the comparisons

The water fixture uses the historical Delayed response run without further incidents. A separate Juneau test delays the initial report until 4 h. Recognition follows at 28 h. With a measured 160 work-hours reported at 200 h, the model reopens the repair queue and returns to manual operation. Automatic service resumes at about 204.21 h and the second laboratory clearance follows 48 h later. Without that field report, there is one restoration and one clearance. The test also accounts for every posted work-hour. [Edited incident and paired control](../../../scenarios/water_controls_wipe/tests/test_service_recovery.py)

An edited heat run starts private relocation at hour zero, simultaneous with the observed outage, and starts outreach at hour one. The test observes positive relocations during the first hour and reads the number of people whom outreach protects at hour one. It caught a same-time ordering error in which relocation stood down before the outage finished starting. Stand-down now depends on the restoration event. [Opening-stage and outreach test](../../../scenarios/heat_wave_blackout/tests/test_briefs.py)

Water comparisons allow relative error of 10⁻⁸ with an absolute floor of 10⁻⁸ in the reported unit. Aggregated repair queues allow 10⁻⁵ work-hours absolute at zero because each component queue has a 1,000-work-hour comparison scale. Both source and candidate must reach the horizon before their observations count. Reproduce the historical inputs and output values independently as follows.

```sh
python scratch/rewrite/a5/check_water_recovery.py /path/to/legacy-checkout --jobs 4
python -m pytest -q --no-focused -m deep scenarios/water_controls_wipe/tests/test_service_recovery.py -n 6
```

The historical catalogue also generated disruptions by choosing future attacker actions. The recovery packages accept an initial incident, reported setbacks, lot condition or aggregate workload as appropriate. The response changes when these inputs change. The original attacker policies and their counterfactual comparisons belong to the historical study. Current published readings report the supplied recovery cases. The Washington, DC uncertainty comparison uses the current random sampler, with the legacy delayed-response PERT ranges and a documented early-response comparison. Two matched draws for each response completed 2,160 hours. The 50-draw study per response was outside this verification run. [Washington sampling inputs and commands](../../../scenarios/water_controls_wipe/variants/washington_dc/README.md)

## What the port caught

In Jamestown, a literal transcription of a synchronous effect introduced an intermediate round in which controls had failed but the repair queue was still empty. That allowed an unwarranted restoration and produced zero lost water service. The migrated outage stage now creates the queue with the loss of controls. The first 24 h account for 2.4973326 million US gallons of unmet demand, as in the historical run.

In Washington, DC, a full downstream store kept a positive residual on its books while allocation still held it at its boundary. A numerical method used that physical residual to select the refill branch. At six minutes the published purchase rate was 2.726 million L/h, while the purchase ledger implied 5.520 million L/h. Selecting branches from the allocation velocity restored the 2.726 million L/h rate and its matching ledger entry. In the completed production run the cumulative shortage was 59.3250148 million US gallons at 2,160 h. At 72 h, 1,121,613 residents were under advisory. Both values agree with legacy. [Method and reference regression](../../../tests/engine/test_held_branch_velocity.py)

Lehigh uncovered a second branch issue. The advisory was already active, yet the scheduler kept forecasting the stock comparison in a pressure-loss guard that first required potable status. This advanced the clock one representable tick at a time. Ignoring a branch while a held condition rules it out lets the run reach its horizon. Changing the held condition re-enables the forecast. [Trigger regression](../../../tests/engine/test_inactive_guard_contacts.py)

Artifact-only runs of the reservoir and Juneau recovered 15 source readings and the same 27 ordered event starts in fresh processes with scenario-file access disabled. The water dashboard reads the selected time from the same run, including fractional hours. [Dashboard](../../../scenarios/water_controls_wipe/ui/README.md)

## Reproducing the example migration gate

The checker archives both revisions and runs each in its own Python process. It now checks the reservoir under `examples/`, which is the package users run. Twelve piano draws matched at 0, 4,380 and 8,760 hours. Twelve reservoir configurations matched at seven times, and the 24 sampled and analytical controls passed. The checker rejected both an incorrect final tuning count and a run that failed exactly at its horizon. [Paired comparison and rejection checks](../a5/paired_migrations.py)

```sh
python scratch/rewrite/a5/paired_migrations.py --candidate HEAD
```
