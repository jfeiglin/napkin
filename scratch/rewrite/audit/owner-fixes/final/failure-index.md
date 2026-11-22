# Phase 1 failure index

The ten structural owners ran **9,000 family/seed IDs** on macOS. **7,799 failed and 1,201 passed** on the respective baselines. Five point owners ran another **1,500 IDs**, with **1,182 failures and 318 passes**. All **10,500 IDs** match a passing verification row with the same generator digest. Each baseline ledger retains its passing controls and all reported differences for each failed ID. Counts below are IDs, so several observations or variants may contribute to one failure.

**Baseline provenance.** S1 ran all 900 IDs against the original engine and reference at `b433a4d`. The owner-by-owner process ran subsequent families on the revision available before their repair. The “tested” column gives that revision. “Red list” gives the commit that preserved the evidence. The staged results do not establish how many of the later IDs would fail on the original revision. Separate direct checks reproduced three P4 cases and the P6 short bend on `b433a4d`. [P4 original-base checks](../p4/baseline.md) · [P6 original-base check](../p6/baseline.md)

## Structural owners

Each family ran seeds 0–299. The counts beside family names identify failed IDs. For a partial family, the linked red ledger gives the individual seeds in its `id` field and their `status`. The notes link differences to reproductions and the affected readers.

| Owner | Tested | Red list | Failed / tested | Affected families | Repair commits | Evidence |
|---|---|---|---:|---|---|---|
| S1 stage reads | `b433a4d` | `e449649` | 900 / 900 | scalar 300, selection 300, ordering 300 | `ddd7801` | [Notes](../s1/baseline.md) · [Red](../s1/baseline.jsonl.gz) · [Green](../s1/verified.jsonl.gz) |
| S2 comparison bands | `9a1cf1a` | `caa796d` | 579 / 600 | gap 279, range 300 | `5a51953` (23 vector errors), `d3a680b` | [Notes](../s2/baseline.md) · [Red](../s2/baseline.jsonl.gz) · [Green](../s2/verified.jsonl.gz) |
| S6 written numbers | `2faca9e` | `bf35dc2` | 900 / 900 | units 300, cells 300, CLI 300 | `b108c6c` | [Notes](../s6/baseline.md) · [Red](../s6/baseline.jsonl.gz) · [Green](../s6/verified.jsonl.gz) |
| S3 switch sides | `9c8188b` | `a247a0f` | 730 / 1,200 | Component 148, Sparse 143, MovingDeclared 139, selection 300 | `8ec5b13`, reference `8b8a90a` | [Notes](../s3/baseline.md) · [Red](../s3/baseline.jsonl.gz) · [Green](../s3/verified.jsonl.gz) |
| S4 stock accounting | `51277c9` | `6222254` | 900 / 900 | inventory 300, capacity 300, edits 300 | `1d5d8dc`, reference `b7fde0e` | [Notes](../s4/baseline.md) · [Red](../s4/baseline.jsonl.gz) · [Green](../s4/verified.jsonl.gz) |
| S9 stock bounds | `ca5a674` | `67e011b` | 213 / 600 | reversible 199, simultaneous 14 | `f239660` | [Notes](../s9/baseline.md) · [Red](../s9/baseline.jsonl.gz) · [Green](../s9/verified.jsonl.gz) |
| S5 scope and collections | `7f308d1` | `222ee15` | 1,173 / 1,200 | scope 300, authoring 300, kinds 300, filter 273 | `40a80c3`, reference `41faa16` and `42f56ba` | [Notes](../s5/baseline.md) · [Red](../s5/baseline.jsonl.gz) · [Green](../s5/verified.jsonl.gz) |
| S7 solver scales | `97a7b3e` | `0018df2` | 304 / 600 | objective 121, flow 183 | `47852cb` | [Notes](../s7/baseline.md) · [Red](../s7/baseline.jsonl.gz) · [Green](../s7/verified.jsonl.gz) |
| S8 record history | `e0a549f` | `97a42db` | 900 / 900 | identity 300, numerics 300, history 300 | `dedb45c` | [Notes](../s8/baseline.md) · [Red](../s8/baseline.jsonl.gz) · [Green](../s8/verified.jsonl.gz) |
| S10 citations and reachability | `e003d1a` | `14215ec` | 1,200 / 1,200 | network 300, solver 300, arguments 300, reach 300 | `6121149`, `826f39b` | [Notes](../s10/baseline.md) · [Red](../s10/baseline.jsonl.gz) · [Green](../s10/verified.jsonl.gz) |

S4’s failed-move history case belongs to both the exact ledger and S8’s history compaction. The S9 ledger counts 146 individual stopped variants within its reversible family. Each maps to a minimized model, the original source hash and the observed diagnostic. S10’s first verification still had 300 solver-family differences over the origin of a declared flow’s request. Its second repair closed them, and all 1,200 passed at `7a37ffc`. [S4/S8 shared case](../s4/history-observation.md) · [S9 stop index and models](../s9/stops.md) · [S10 intermediate and final evidence](../s10/verification.md)

## Point owners

Five points used 300-seed families. The other three used named direct tests. The [copy register](../../engine-finalized-simple.md) gives the pattern search, its findings and the verification for every point.

| Owner | Tested | Red list | Failed / tested | Affected seeds or cases | Repair commits | Evidence |
|---|---|---|---:|---|---|---|
| P1 cross-set rate reads | `be55c21` | `8106ca2` | 184 / 300 | The reference also failed 28 of these IDs. Eight request/capacity spellings and three delayed-reader or Jacobian probes failed directly. | `4937425`, reference `a75f116` | [Notes](../p1/baseline.md) · [Red](../p1/baseline.jsonl.gz) · [Green](../p1/verified.jsonl.gz) |
| P2 replay | Parent `c55c3ea` of the test-only red commit | `3b6c501` | 6 / 8 direct | Shifted and original edit stops in memory and on disk, an unwitnessed edit, and a legacy checkpoint | `e003d1a` | [Failed nodes](../p2/baseline.log.gz) · [Verification](../p2/verified.log.gz) |
| P3 repeated work | `e2a24f2` | `7a37ffc` | 16 / 16 direct | Five operation counts at 32, 64 and 128 items, plus reuse of unchanged endpoint members | `553215c` | [Counts and nodes](../p3/baseline.log.gz) · [Verified counts](../p3/verified.log.gz) |
| P4 unsound lag | `f28abb4` | `2a84c5f` | 300 / 300 | Every seed granted lag on falling minima, maxima, a fixed-time lookup, and the first of two overlapping stocks. | `0ac7920` | [Notes](../p4/baseline.md) · [Red](../p4/baseline.jsonl.gz) · [Green](../p4/verified.jsonl.gz) |
| P5 study request | `e2a24f2` | `f28abb4` | 264 / 300 | Nine direct failures include central path selection and fixed-seed sample budgets. | `ec4220e` | [Notes](../p5/baseline.md) · [Red](../p5/baseline.jsonl.gz) · [Green](../p5/verified.jsonl.gz) |
| P6 lag integration | `ee36192` | `4a5c4a2` | 134 / 300 | 132 missed recorded values. Seeds 220 and 265 failed only the integral comparison. | `39e2de1` | [Notes](../p6/baseline.md) · [Red](../p6/baseline.jsonl.gz) · [Green](../p6/verified.jsonl.gz) |
| P7 single-pass report selection | `2a84c5f` | `481fab1` | 300 / 300 | Every seed failed six iterator/generator subcases, including the unknown-path error. | `8156882` | [Notes](../p7/baseline.md) · [Red](../p7/baseline.jsonl.gz) · [Green](../p7/verified.jsonl.gz) |
| P8 categorical overflow | `b108c6c` | `de355fa` | 10 / 21 direct | Equal-weight seeds 0, 1, 3, 4, unequal-weight seeds 0–4, and the eligible-boundary test. All 52 chance tests passed after repair. | `03c5b0f` | [Draws, exact reference and named outcomes](../p8/baseline.json) · [Verified result in register](../../engine-finalized-simple.md) |

## Additional failures and reproductions

- Reference creation numbers and reversed equal-key literals have their own red examples. Commits `d2a5b27` and `9a1cf1a` fixed them separately. S2’s 23 vector errors share one native-integer finiteness check. Its reduced example divides two finite integers of size 2⁶⁴. [Reference keys and tie controls](../reference-keys.md) · [Vector model](../s2/vector-integer.scn)
- Checkpoint and solver tests found a second rounding of written range endpoints. Seed 37 exposed a missed stock crossing between adjacent clock values. Seed 875 exposed an exact-zero test assumption at balanced throughflow. Their respective changes were `42feae7`, `ee36192` and `e2a24f2`. [Range reproductions](../exact-range/verification.md) · [Clock handoff](../clock-edit/findings.md) · [Throughflow controls](../balanced-face/baseline.md)
- Independent text/builder comparisons at `bdf91d7` found 300 failing study IDs (implicit distribution support), 300 numeric IDs (exact range admission), and 300 collection-kind IDs (constant natural keys). The fixes were `18e4745`, `0cb25d6` and `f465679`, respectively. These comparisons postdate the owner baselines. [Study baseline](../authoring-parity/records-baseline.jsonl.gz) · [Study verification](../authoring-parity/support-verified.jsonl.gz) · [Numeric baseline](../authoring-parity/number-solver-baseline.jsonl.gz) · [Numeric verification](../authoring-parity/number-solver-verified.jsonl.gz) · [Collection comparison and verification](../s5/collection-parity.md)
- The later deep sweep found 49 additional S3 family/seed failures and two S9 failures, with the individual IDs recorded before repair. `f5cde5e` corrected the switch departure and `c9762e9` corrected the two bound contacts at seeds 437 and 1553. [Failed IDs](mac/deep-corpus-failures.args) · [Switch findings and model](deep-switch/findings.md) · [Bound findings and models](deep-bounds/stops.md)
