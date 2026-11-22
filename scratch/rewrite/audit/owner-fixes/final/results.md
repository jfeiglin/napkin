# Audit verification

The [failure index](failure-index.md) maps each owner’s original failures to passing case IDs, generator hashes and commits. The [ownership register](../../engine-finalized-simple.md) identifies the old and new decision sites, their readers, the reference-only fixes and the point-fix pattern searches.

## Mac regular and deep

| Tier | First run | First result | Failed-only retry | Final outcome by original test ID |
|---|---|---|---|---|
| Regular | `f465679`, 907.02 s | 12,899 passed, 39 failed, 2 skipped | All 39 passed at `7eb6dae` in 28.77 s | 12,938 passed, 2 skipped |
| Deep | `7eb6dae`, 1,991.38 s | 111,791 passed, 52 failed | All 51 corpus cases passed in 3.47 s. The heat-wave case passed in 48.92 s on the source committed at `93ebabf`. | 111,843 passed |

The 300 regular seeds exercised one transformation each. Deep ran all 44 transformations on every one of 2,000 seeds. Neither run truncated any comparison, including the second displacement checked by the roundoff transformation. [Regular first run](mac/regular.xml.gz), [regular retry](mac/regular-retry.xml.gz), [deep first run](mac/deep.xml.gz), [deep corpus retry](mac/deep-51-retry.xml.gz), [heat-wave retry](mac/heat-full-outreach.xml.gz), [reconciled counts](mac/reconciled-results.json), [final deep coverage](mac/deep-reconciled-corpus.log.gz).

Mac skipped a Linux-only process-lifetime check that reads `/proc`, and an example-edit check that collected an empty parameter set. Both skips are recorded by name in the original regular JUnit.

The 300 regular corpus tests used 39.135 summed worker-seconds. An earlier four-worker run at `caecf10` used 38.977 worker-seconds on 300 seeds. The current full selection exceeded the historical 180-second wall-time budget. Two passing heat-wave catalogue tests overlapped and took 804.092 and 626.899 seconds individually. The older 160.299-second suite included neither test. The combined regular-and-deep run at `b433a4d` stopped before either returned a result. [Timing measurements and JUnit digests](mac/regular-timing.json).

## Mac publication

Fresh renders of the heat-wave and IV-fluid studies matched their briefs and readings after refreshing the model fingerprint in the heat-wave reading. The standalone defensive reading matched on its first check. The catalogue-wide source dossier and manifest comparison found three stale model fingerprints. All three dossiers matched on retry. [Commands, commits and exits](mac/publication.json), [heat and IV first output](mac/catalogue-pages.log.gz), [heat reading retry](mac/heat-readings-retry.log.gz), [defensive reading](mac/defensive-readings.log.gz), [static first output](mac/sources.log.gz), [static retry](mac/sources-drift-retry.log.gz).

The [explicit pytest selection](pytest.args) covers the engine, tools, selected live scenarios and catalogue metadata. The publication comparison executed the heat-wave and IV-fluid studies and the standalone defensive response. For the rest of the catalogue it checked static source dossiers and the manifest. Unrestricted live catalogue publication remains unverified.

## Mac speed

The baseline was `6202824d6d567c34ac46da7b018e66a9c28588b3` and the final candidate was `4b372a0a5c39fb7f1e2b9233599b0219f4d95bc7`. The driver alternated the order across three matched pairs with single-threaded BLAS. Every median candidate/baseline ratio passed the 1.05 limit.

| Workload | Median run and record | Median build, plan, run and record |
|---|---:|---:|
| Sparse tanks | 1.035992 | |
| Component tanks | 0.983316 | |
| Events | 0.972325 | |
| Declared solver | 0.800905 | 0.825793 |

[Three-pair timings for each row](mac/final-speed.md) · [Raw samples, schedules, calibrations and command outputs](mac/final-speed-raw.zip).

## Generated bound stops

The reversible-tank generator recorded 135 Component bound failures and 11 declared-solver trial-budget stops in the original owner run. The deep tier added two Component stops. Every stopped variant has an individually minimized model. All 148 reached their horizons on the corrected source. [for the owner: stop near simultaneous bounds, fix or diagnostic?](../s9/stops.md) · [First 146 models](../s9/minimized-stops.zip) · [Two deep models and analytic outcomes](deep-bounds/stops.md).
