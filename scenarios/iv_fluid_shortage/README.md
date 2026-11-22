# IV-fluid supply and recovery

One hypothetical manufacturer supplies a network of 100 hospitals. For 60 days the model follows two 600 L/day hospital reserves, outside supply, the manufacturer's finite qualification work and the 24 hours required to ship newly released fluid. The inputs describe a scenario for comparing service responses. Clinical risk assumptions and monetary estimates have not been calibrated to this network.

## Run the scenario

```sh
python -m napkin run scenarios/iv_fluid_shortage --run subpar --at 0h,360h,528h,1440h --value other_care_reserve.stock,other_care_reserve.deficit,resuscitation_patients.unserved
python -m napkin run scenarios/iv_fluid_shortage --run subpar_persistent --at 696h,888.25h,1248.25h --value deliveries.state,resuscitation_reserve.held,release_team.work_done
```

The early, standard and limited responses set hospital procurement delay, rescue capacity, containment time, qualification pace and records-service recovery. A procurement order can add a finite records task. Qualified release waits for procurement, containment, permission to release and completion of the team's work.

A separate input, `records.released_lot`, describes the first lot at release. A `CLEAR` lot can ship. A `NEEDS_CHECK` lot starts an independent product check a quarter-hour after release. On confirmation, the hospitals set aside the affected fluid still in their reserves. The team must finish product reconciliation and the records service must be available before it can release replacements. The manufacturer schedules a credential reset when records service is restored. A confirmed discrepancy immediately revokes the credentials even if the scheduled reset is still pending. In the public trace, `manufacturer.credentials_reset` marks the scheduled reset and `release_systems.credentials` shows the current credential state. Product-check and release delays can be edited. The model accounts for all fluid already used, still available, held or sent elsewhere.

The seven historical run IDs are retained. `subpar_persistent` and `subpar_persistent_human` compare two first-lot conditions with the same standard response and finite qualification work. The historical suffix identifies a saved configuration. The current model takes lot quality and the initial review workload as inputs. It calculates recovery and supply from those conditions. Automated access, record changes and initial disruption from the historical model are outside the executable recovery scenarios.

## Reading the results

The resuscitation reserve supplies complete urgent courses. A fraction of patients who miss a course qualify for outside rescue. The remaining patients contribute to the modeled excess deaths and serious surviving cases. The other reserve supplies essential care and contributes separately to postponed procedures and economic losses. The clinical estimates are expected counts. Lagged clinical reports become available once the record covers the six-hour delay.

The legacy package, publication and its original assumptions are preserved at commit `8488047`. The historical methods and assumptions in `results/` describe that publication. The current run command above reads this package's checked program. The [current readings](results/readings.md) show instantaneous stock and outcome values at the start and the horizon. To apply the clinical reporting delay on the command line, add `--lag high_risk_patients.casualties=6h..6h` to a run selecting that outcome.


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

## Timing of independent quality reviews

Three additional runs compare how the manufacturer responds to incoming quality notices. Emergency procurement opens intake. The first notice arrives after the editable `quality_review.first_delay` (zero by default), so changing procurement timing shifts the intake clock and its first notice together. `quality_review.notice_limit` sets the maximum count including that first notice. The three named runs use two. In the fixed schedule, each subsequent notice arrives after the selected interval. In the follow-up schedule, that interval starts when the preceding review finishes. The intake window starts at procurement and excludes notices at or after its closing hour. Each admitted notice pauses qualification or subsequent shipments until the team clears its current backlog. An expected future notice has no effect before it arrives. A change in qualified shipments reaches the hospitals 24 hours later. The physical lot hold is tracked separately and must also clear before hospital deliveries can resume.

| Median run | Notice arrivals (h) | Review starts (h) | Documentation cleared (h) | Qualified release (h) | Confirmed product hold (h) |
| --- | --- | --- | ---: | ---: | ---: |
| `fixed_quality_review` | 72, 312 | 72, 408 | 744 | 744 | 960.25 |
| `expedited_quality_review` | 72, 312 | 72, 312 | 480 | 672 | 888.25 |
| `followup_quality_review` | 72, 648 | 72, 648 | 984 | 984 | 1200.25 |

The expedited team reviews two work-hours per hour under the same fixed schedule and work requirements as the standard team, which reviews one work-hour per hour. It clears its two notices at hour 480. Ordinary qualification work still keeps the manufacturer from releasing the first lot until hour 672.

The authored `quality_reviews` spread draws the work for a notice uniformly from 288 to 384 work-hours and its interval factor uniformly from 0.75 to 1.25, giving a 180–300 h gap with the 240 h nominal interval. Each draw uses the same workload and gap across the three responses. `quality_review.followup_effort` scales the work of each follow-up notice. `quality_review.intake_window` controls intake closure. The spread reports the mean and the 5th and 95th percentiles of the six paired differences in clearance time and shortage duration. The seven original run IDs use routine documentation and retain their previous release conditions. [Paired comparison results](results/paired-spreads.json)

```sh
python -m napkin sample scenarios/iv_fluid_shortage --run fixed_quality_review --value quality_review.cleared_at,other_care_reserve.shortage_days --samples 6 --seed 23
```
