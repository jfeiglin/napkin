## S4 exact inventories and external edits

All 900 case IDs failed on macOS at clean engine and reference revision `51277c92e7e9ddbc46bdc799e4f4701c724d2e29`. The [full ledger](baseline.jsonl.gz) includes each subcase's mismatches and the digest of its generator.

| Seeds | Family | Result against the analytic ledger |
| ---: | --- | --- |
| 300 | Inventory | Per seed, six of eight engine subcases failed. The two idle-pipe increment/decrement controls passed. Exact bounded assignment, exact plain assignment and a stock-dependent opening all lost inventory. The reference matched across all eight. |
| 300 | Capacity | All seven engine subcases failed for every seed. These include source and destination shortages at two magnitudes, exact decimal capacity, and preservation of the remainder from an opening or a transfer. All seven reference subcases matched. |
| 300 | Edits | Before-first-move, between-stage and within-stage edits each ran on both a move-only stock and an idle-pipe control. The harness collected 48,126 divergent engine observations across live, restored, record and CLI reads, plus 591 divergent reference external-ledger observations. |

[Minimal reference example](reference-edit-before-first-move.scn): edit `box.stock` to 5 L at the first stage stop, then transfer it. The reference delivers 5 L but omits the +5 L external posting. The inventory and capacity generator records the runnable model with every differing subcase. The edit generator reconstructs each model from seed, stop position and idle-pipe flag.
