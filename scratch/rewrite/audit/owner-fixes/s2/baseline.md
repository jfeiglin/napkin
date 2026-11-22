# S2 baseline — exact comparison bands and authoring ranges

On macOS arm64 with Python 3.13.16, 579 of the 600 cases failed and 21 passed.
Each family ran all 300 seeds in three disjoint batches of 100 at
`9a1cf1a423b376e564ec4ccf80ff6d8568fc8f1d`. All rows used the clean engine and reference
at that revision. Every reference reading in the gap family matched its independently computed
expectation. All 23 vector errors retain their tracebacks. Independent runs of the other fields,
scalar aliases and solver constraints preserved their observations for those seeds.

| Family and observation | Affected seeds | Differences | Attribution |
| --- | ---: | ---: | --- |
| Exact gap inside its band | 25 | 300 | S2. A declared floor and the literal binding must both remain accessible. The gap at the closed edge rounds to the other side. |
| Exact gap outside its band | 279 | 3,295 | S2. A small decimal residual at a large origin can disappear before the comparison. |
| Stored conditional initializer checked against a singleton range | 25 inside, 279 outside | 100 inside, 1,106 outside | S2. The wrong conditional arm produces the opposite admission decision for the two singleton ranges. |
| Text event parameter with a small inversion | 300 | 600 | S2. The parameter compiler rejects an inversion within the field's closed band in both hour and minute spellings. The ordinary field and builder accept it. |
| Builder field and event parameter with a larger inversion | 300 | 1,200 | S2. Both forms pass builder validation in each spelling. Running the returned program detects the inverted interval. |
| Vector rate in minute spelling | 23 | 23 | New POINT for the owner. The scalar integer used by the vector expression exceeds NumPy's supported integer width for `isfinite`. |

Of 300 gap cases, 279 failed. All 300 range cases failed. A seed contributes multiple observations
when several readers or spellings disagree. The alternate template row retained its expected
decision in each successful read.

## Reduced reproductions

- In [closed-edge.scn](closed-edge.scn), the equality band contains the exact residual
  `0.000000001 h`. The reference returns true for the inclusive comparison. The engine returns false.
- In [cancelled-gap.scn](cancelled-gap.scn), the exact residual `0.00000005 h` exceeds the band.
  The reference returns true for the strict comparison. The engine returns false.
- In [initializer-bounds.scn](initializer-bounds.scn), the reference stores 7 within `[7,7]`.
  The engine stops with a bounds error.
- [parameter-bounds.scn](parameter-bounds.scn) is rejected by the text compiler even though the
  inversion is half the applicable band. [builder-bounds.py](builder-bounds.py) demonstrates that
  both builder declaration forms accept an inversion of twice the band at `Builder.finish()`.
- Seed 31 exposed a separate error when the authored `479999999999.999999460 min` produced a
  Python integer of `23999999999999999973` in the vector evaluator. The reduced
  [vector-integer.scn](vector-integer.scn) computes one litre per hour by dividing two finite
  quantities of magnitude 2⁶⁴. The reference returns 1. The engine raises `TypeError` even though
  the model contains no comparison. [Reduced traceback](vector-integer-traceback.txt)

## Complete results and retry

[All 600 outcomes](baseline.jsonl.gz) include the case ID, source revision, generator digests,
elapsed time, mismatches and any error tracebacks. The generator's SHA-256 is
`bcdfbb18cc247df1ccfb5fffea469f60c829629622143fb101cbf6f533606db9` and the archive's SHA-256 is
`2047ba51452902a674f2488ce818d96bd775f7c3f5dc2e2beddf7531d0ea9411`.
The following command retries only the unsuccessful gap cases for the first 100 seeds.

```sh
.venv/bin/python -B -m scratch.rewrite.audit.owner_cases run \
    --failed-from scratch/rewrite/audit/owner-fixes/s2/baseline.jsonl.gz \
    --family s2/gap --start 0 --stop 100 --out /tmp/s2-gap-retry.jsonl
```
