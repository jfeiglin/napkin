## P1 rates read across independent sets

All 300 seeds ran on macOS at `be55c21`. The engine failed 184 seeds. The reference also failed 28 of those seeds. Both passed the remaining 116. Each variant carries the actual Sparse dependency order, independently integrated stock and rate reads, and the model for every discrepancy. [Case-by-case baseline](baseline.jsonl.gz).

The [two-level model](cross-set.scn) fills at 2 L/h for half an hour and at 0.25 L/h for the remaining 1.5 h. The correct final inventory is 11/8 L. The engine produced 4 L without the empty event and 2.25 L with it. All eight combinations of keyed or guarded selection, request or capacity, and event or uninterrupted run failed. Both interpreters passed the continuously varying linear request and capacity controls. [Eight direct failures](direct-red.log.gz).

Two readers retained for different times or inventories both observed a later probe's flow rate. A bare request evaluation for the Jacobian also observed 2 L/h where its supplied state gave 0.25 L/h. [Three snapshot failures](snapshots-red.log.gz).

The reference reached the correct contact but continued with an old downstream setting in two exact models. The [three-level rate chain](cross-set-three.scn) ends at 15/16 L and the [stock-driven descending lookup](keyed-stock-driver.scn) at 13/8 L. The reference returned 4 L and 2 L respectively. [Reference failures](ref-breaks-red.log.gz).
