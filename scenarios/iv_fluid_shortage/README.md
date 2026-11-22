# IV-fluid supply and recovery

One hypothetical manufacturer supplies a network of 100 hospitals. For 60 days the model follows two 600 L/day hospital reserves, outside supply, the manufacturer's finite qualification work and the 24 hours required to ship newly released fluid. The inputs describe a scenario for comparing service responses. Clinical risk assumptions and monetary estimates have not been calibrated to this network.

## Run the scenario

```sh
python -m napkin run scenarios/iv_fluid_shortage --run subpar --at 0h,360h,528h,1440h --value other_care_reserve.stock,other_care_reserve.deficit,resuscitation_patients.unserved
python -m napkin run scenarios/iv_fluid_shortage --run subpar_persistent --at 696h,888.25h,1248.25h --value deliveries.state,resuscitation_reserve.held,release_team.work_done
```

The early, standard and limited responses set hospital procurement delay, rescue capacity, containment time, qualification pace and records-service recovery. A procurement order can add a finite records task. Qualified release waits for procurement, containment, permission to release and completion of the team's work.

A separate input, `records.released_lot`, describes the first lot at release. A `CLEAR` lot can ship. A `NEEDS_CHECK` lot starts an independent product check a quarter-hour after release. On confirmation, the hospitals set aside the affected fluid still in their reserves. The team must finish product reconciliation and the records service must be available before it can release replacements. Product-check and release delays can be edited. The model accounts for all fluid already used, still available, held or sent elsewhere.

The seven historical run IDs are retained. `subpar_persistent` and `subpar_persistent_human` compare two first-lot conditions with the same standard response and finite qualification work. The historical suffix identifies a saved configuration. The current model takes lot quality as an input. It calculates recovery and supply from that condition.

## Reading the results

The resuscitation reserve supplies complete urgent courses. A fraction of patients who miss a course qualify for outside rescue. The remaining patients contribute to the modeled excess deaths and serious surviving cases. The other reserve supplies essential care and contributes separately to postponed procedures and economic losses. The clinical estimates are expected counts. Lagged clinical reports become available once the record covers the six-hour delay.

The legacy package, publication and its original assumptions are preserved at commit `8488047`. Files from that publication in `results/` describe that historical scenario. The current run command above reads this package's checked program. The [current readings](results/readings.md) show instantaneous stock and outcome values at the start and the horizon. To apply the clinical reporting delay on the command line, add `--lag high_risk_patients.casualties=6h..6h` to a run selecting that outcome.


## Migration checks

The pinned legacy engine and current engine ran in separate processes. The comparison sampled 17 times from hour 0 through 1,440 for all seven named runs and four edits to staffing and product checks, hospital buffer and rescue capacity, release permission, and procurement delay. The 3,349 intermediate physical readings matched within 1e−6 absolute or 1e−8 relative tolerance. The legacy model omits held-lot stocks in six configurations. Each of the 204 corresponding current readings was zero.

All 88 event lists matched, including events that did not fire before the horizon. Of 3,553 reported outcome observations, 3,520 matched numerically. The other 33 are the three six-hour clinical readings at hour zero in each of eleven configurations. The legacy model reported zero before the reporting window existed. The current reporter identifies the missing prehistory. Deaths, serious surviving cases, and their sum use the same physical delay.

| Response and first lot | First release (h) | First receipt (h) | Hold (h) | Replacement receipt (h) |
|---|---:|---:|---:|---:|
| Early, routine | 252 | 276 | — | — |
| Standard, routine | 504 | 528 | — | — |
| Limited, routine | 840 | 864 | — | — |
| Early, additional work, clear | 336 | 360 | — | — |
| Standard, additional work, clear | 672 | 696 | — | — |
| Standard, additional work, check | 672 | 696 | 888.25 | 1,248.25 |
| Limited, additional work, check | 1,120 | 1,144 | 1,336.25 | Beyond horizon |

The fixed observations cover these conditions and response edits. Changing the reported condition of the released lot is a new scenario input. Containment and records-service recovery are counted as defensive milestones. A check and any associated recovery work follow the particular lot through to replacement. Neither calibration of the selected inputs nor a causal attribution of a lot discrepancy follows from this comparison.

The two balance assertions express the original tolerances as signed intervals around zero, which the continuous checker can locate directly. The tests also exercise simultaneous procurement and work completion, zero extra work, delayed release, physical lot holds and clinical probability checks. The legacy observations live in `tests/legacy-recovery.json.gz`; that file includes the source SHA, named runs, edits, sample times and legacy readings. To run all package tests from the repository root:

```sh
python -m pytest --no-focused -m 'deep or not deep' scenarios/iv_fluid_shortage/tests/test_*.py
```
