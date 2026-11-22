# IV-fluid supply and recovery

A manufacturer pauses IV-fluid shipments. Hospital reserves, procurement and outside supply cover demand while the release team qualifies its systems and reviews lots. The model follows fluid, work, patient courses and costs for sixty days.

One hypothetical manufacturer and a network of 100 hospitals.

Readings at 1440 h. [Run readings and evidence](readings.md).

## subpar_persistent_human against subpar_persistent

| Reading | Unit | subpar_persistent | subpar_persistent_human | Change (run − baseline) | Change (%) |
|---|---|---:|---:|---:|---:|
| high_risk_patients.deaths | people | 0 | 0 | 0 | — |
| high_risk_patients.casualties | people | 0 | 0 | 0 | — |
| loss_bn | USD2025_bn | 0.03187 | 0.03142 | -0.00045 | -1.41199 |
| other_care_reserve.shortage_days | days | 29 | 14 | -15 | -51.7241 |
| release_work_done | work_h | 1008 | 672 | -336 | -33.3333 |
| resuscitation_reserve.deficit | L | 1086.25 | 0 | -1086.25 | -100 |
| other_care_reserve.deficit | L | 17400 | 8400 | -9000 | -51.7241 |
| fluid_sent_elsewhere | L | 7680 | 14880 | 7200 | 93.75 |
| procedure_loss | USD2025_bn | 0.00087 | 0.00042 | -0.00045 | -51.7241 |
| people_needing_courses | people | 18000 | 18000 | 0 | 0 |
| resuscitation_patients.unserved | people | 543.125 | 0 | -543.125 | -100 |
| timely_courses | people | 17456.9 | 18000 | 543.125 | 3.11124 |
| manufacturer.hours_out | h | 1440 | 1440 | 0 | 0 |
| quality_review.completed | 1 | 0 | 0 | 0 | — |
| quality_review.cleared_at | h | 0 | 0 | 0 | — |

## followup_quality_review against fixed_quality_review

| Reading | Unit | fixed_quality_review | followup_quality_review | Change (run − baseline) | Change (%) |
|---|---|---:|---:|---:|---:|
| high_risk_patients.deaths | people | 0 | 0 | 0 | — |
| high_risk_patients.casualties | people | 0 | 0 | 0 | — |
| loss_bn | USD2025_bn | 0.03196 | 0.0321097 | 0.000149687 | 0.468359 |
| other_care_reserve.shortage_days | days | 32 | 36.9896 | 4.98958 | 15.5924 |
| release_work_done | work_h | 1008 | 911.75 | -96.25 | -9.54861 |
| resuscitation_reserve.deficit | L | 1446.25 | 1198.75 | -247.5 | -17.1132 |
| other_care_reserve.deficit | L | 19200 | 22193.8 | 2993.75 | 15.5924 |
| fluid_sent_elsewhere | L | 6240 | 3845 | -2395 | -38.3814 |
| procedure_loss | USD2025_bn | 0.00096 | 0.00110969 | 0.000149687 | 15.5924 |
| people_needing_courses | people | 18000 | 18000 | 0 | 0 |
| resuscitation_patients.unserved | people | 723.125 | 599.375 | -123.75 | -17.1132 |
| timely_courses | people | 17276.9 | 17400.6 | 123.75 | 0.716275 |
| manufacturer.hours_out | h | 1440 | 1440 | 0 | 0 |
| quality_review.completed | 1 | 2 | 2 | 0 | 0 |
| quality_review.cleared_at | h | 744 | 984 | 240 | 32.2581 |

## expedited_quality_review against fixed_quality_review

| Reading | Unit | fixed_quality_review | expedited_quality_review | Change (run − baseline) | Change (%) |
|---|---|---:|---:|---:|---:|
| high_risk_patients.deaths | people | 0 | 0 | 0 | — |
| high_risk_patients.casualties | people | 0 | 0 | 0 | — |
| loss_bn | USD2025_bn | 0.03196 | 0.03187 | -9e-05 | -0.281602 |
| other_care_reserve.shortage_days | days | 32 | 29 | -3 | -9.375 |
| release_work_done | work_h | 1008 | 1008 | 0 | 0 |
| resuscitation_reserve.deficit | L | 1446.25 | 1086.25 | -360 | -24.892 |
| other_care_reserve.deficit | L | 19200 | 17400 | -1800 | -9.375 |
| fluid_sent_elsewhere | L | 6240 | 7680 | 1440 | 23.0769 |
| procedure_loss | USD2025_bn | 0.00096 | 0.00087 | -9e-05 | -9.375 |
| people_needing_courses | people | 18000 | 18000 | 0 | 0 |
| resuscitation_patients.unserved | people | 723.125 | 543.125 | -180 | -24.892 |
| timely_courses | people | 17276.9 | 17456.9 | 180 | 1.04186 |
| manufacturer.hours_out | h | 1440 | 1440 | 0 | 0 |
| quality_review.completed | 1 | 2 | 2 | 0 | 0 |
| quality_review.cleared_at | h | 744 | 480 | -264 | -35.4839 |
