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

## Linux verification

Linux used the locked environment with Python 3.12.14 and four pytest workers. The regular run at `f465679` finished with 12,901 passes, 38 failures and one skip. Its 300-seed corpus passed. All 38 failed IDs passed at `7eb6dae`, giving 12,939 passed and one skipped after reconciliation.

The deep run used `93ebabf`. The first session ended before its JUnit file closed. Its verbose log preserved 69,201 passing node IDs. The remainder selected the other 42,642 IDs. Before the next session limit, pytest closed its JUnit with 42,616 further passes. The final 26 passed. Together the three disjoint selections account for all 111,843 passing tests, all 2,000 seeds and all 88,000 transformation cases. The reconstructed first-segment XML records the test outcomes. Per-test timings from that segment were lost. Of the 44 transformations, nine can emit an optional near-tie property and 35 return before its writer. [Interrupted-run evidence procedure](linux/recovery/README.md).

The native continuation reports contain 35,958 transformation cases (36,775 comparisons) and zero truncated comparisons. The original session could not retain native per-test properties for the other 53,225 comparisons. The [guard-only recovery](linux/recovery/README.md) is prepared. Its supplemental Linux measurements are still outstanding. The Linux ZIP contains each selected node, the raw primary and continuation logs, all original failures and the native and reconstructed JUnit files. Its SHA-256 is `761bcc665591e8a0b6e4fe0cc62492746b73165ceb7178b444860991c5954f06`. [Per-segment counts](linux/test-summary.json), [Linux verification receipt](linux/verification-receipt.log), [cloud chat and archive](codex://threads/6b035730-ad88-83ed-a863-49038ba5a078).

The original Linux publisher verified the standalone defensive reading. It reported one stale heat reading and three stale static source dossiers. All four complete differences consisted of one model fingerprint each. Applying the Linux differences to the original Git files produced the exact bytes committed at `4b372a0` for every affected output. [Linux publisher diffs](linux/publisher.diff), [per-file SHA-256 comparisons](linux/publisher-reconciliation.json).

Both failed-only Linux publisher commands exited 0 at `4b372a0` with the locked packages and Python 3.12.14 in a separate local Linux aarch64 VM. The heat reading printed `All 1 committed summaries match a fresh render`. The three static dossiers printed `All 3 committed summaries match a fresh render`. These retries used a cache local to that VM. [Heat reading output](linux/publisher-retries/heat-reading.log), [three dossier outputs](linux/publisher-retries/three-static-dossiers.log), [checkout receipt](linux/publisher-retries/checkout.json).

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
