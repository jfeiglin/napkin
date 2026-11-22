# S1 baseline — reads after a write in the same stage

All 900 cases ran on macOS arm64 with Python 3.13.16 at
`b433a4d710b10ff10c858edeae01cce72a6afcc2`. The engine and reference trees matched that commit.
Every case failed in the engine. The exact reference agreed with the independently expected
values and identities in every case. Each of the 600 broadcast cases also passed the engine
control that inserts a zero-hour wait after the write.

| Family | Seeds | Failed | Smallest observed difference | Owner |
| --- | --- | ---: | --- | --- |
| Scalar stage reads | 0–299 | 300 | The direct read of the newly defined 2 returned 2. Its comparison `> 1` returned false. Replacing a narrow-floor definition with a wide-floor one also left its equality test false. | `Comparisons._binding` consults the committed definition through `Plan.comparison_quantity`. The stage owns the pending definition. |
| Broadcast selection | 0–299 | 300 | After raising the cutoff to 2, the engine started ranks 1 and 2. Only rank 2 qualified. | `Moment.queue` calls `Run.kept_entries` without the stage's writes. |
| Broadcast ordering | 0–299 | 300 | After raising the first member's rank from 1 to 3, the engine started it first. The last member wrote 2. The reference started the changed member last and its write was 3. | `Moment.queue` reads each ordering key using `Run.value` without the stage's writes. |

Every scalar seed disagreed on twelve observations covering comparison, equality, membership, conditional
value, `if` guard, `switch` guard, nested formula, subtraction, inherited floor, move recipient,
move source and captured start argument. Each direct scalar read passed. The ledger retains all
twelve actual/expected pairs separately. The four reduced models next to this report run to 1 h
using `h` as the time unit. Their tests observe `box.direct` and `box.qualifies` in
`definition.scn`, `box.equal` in `floor.scn`, the ordered `Machine.act` starts in
`selection.scn` and `ordering.scn`, and `dispatcher.winner` in `ordering.scn`.

[Complete outcomes](baseline.jsonl.gz) has one JSON record per unique family/seed, including
the SHA, source digests, timing and traceback. The archive's SHA-256 is
`7b8b8b9d3bdd817b1722bb4542568ce5b332baed58985e6ad3ce8d0386a2a8a0`.
Each family ran in three disjoint batches of 100. To retry a failed batch or three individual
cases from the repository root, use fresh output filenames.

```sh
.venv/bin/python -B -m scratch.rewrite.audit.owner_cases run \
    --failed-from scratch/rewrite/audit/owner-fixes/s1/baseline.jsonl.gz \
    --family s1/scalar --start 0 --stop 100 --out /tmp/s1-scalar-retry.jsonl
.venv/bin/python -B -m scratch.rewrite.audit.owner_cases run \
    --id s1/scalar/0 s1/selection/0 s1/ordering/0 --out /tmp/s1-three-retries.jsonl
```
