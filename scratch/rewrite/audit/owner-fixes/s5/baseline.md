## S5 collection scope, selection and authoring

At engine and reference revision `7f308d15d2813ef4d68c2fd5615d6b34aab58987`, 1,173 of 1,200 IDs failed on macOS. All 27 passing IDs belong to the unchanged-threshold control. Each family ran all 300 seeds and finished. Every comparison with a discrepancy includes the generated source or builder reproduction. [Complete baseline ledger](baseline.jsonl.gz).

| Family | Failed IDs | Observations |
| --- | ---: | --- |
| Lexical scope | 300 | Seed 0 exposed nine differences across ten cases. The text selected the global site with weight 3 instead of the parameter’s site with weight 8. The artifact also updated a global table row in place of the linked garden. Every independently authored builder program and its reference execution matched the expected values. |
| Authoring | 300 | The full seed exposed 27 disagreements across 51 programs. These include invalid start argument and distribution domains, collisions with built-in occurrence fields, and valid enum initializers and retained overrides. |
| Collection operations | 300 | Twelve of 27 probes per seed failed. A structured program bypassed text refusals to check the engine and the reference independently. The cases exercise active flows, occurrence history, zero-based keys and projections on both sides of a key operation. |
| Changing filters | 273 | A threshold change affected a trigger, a waiting event, keyed selection and a flow request. All 27 no-change controls passed. The first case counted [2, 2, 2] going forward and [1, 1, 1] reading backward. The expected forward count is [2, 1, 1]. The second case delivered 6 L instead of 5 L. [Trigger and wait](trigger-and-wait.scn), [flow and lookup](flow-and-key.scn). |

The reference resolved a filter’s sink and a new key’s request on the originating pump after projecting to its flow. The dedicated builder reproduction failed twice and passed the control that sets the key before projecting. [Pytest failures](reference-projected-red.log.gz).
