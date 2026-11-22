# S6 baseline for authored numbers

At `2faca9ec4432d19a23f4ec4d8236bee6efd1c7aa`, the three synthetic families each ran seeds 0 through 299 on macOS arm64, Python 3.13.16. Every one of the 900 family/seed cases completed and failed at least one assertion. The separate observations account for 7,500 differences. Each family ran in its own process with BLAS, OpenMP and vecLib limited to one thread. The engine and reference matched the pinned commit throughout.

| Independent observation | Differences | Seed 0 example and expected behavior |
| --- | ---: | --- |
| Local unit scale precision | 900 | Both adjacent authored scales became 1. A value of 1 hx at scale 1.00000000000000001 passed a 1 h upper bound. It should be refused like its equivalent spelling in hours. |
| Shared vocabulary scale loading | 1,800 | Loading either adjacent scale raised an uncaught expression error for each of three independent declarations. Both decimal scales are positive, finite and valid. |
| CSV underflow lost its sign or magnitude | 300 | A cell containing −1e−325 passed bounds [0, 1]. Its negative text counterpart was refused. |
| CSV overflow escaped as an implementation error | 600 | Unbounded cells containing 1e400 or −1e400 each raised a Python ValueError. Both need a diagnostic at the authored cell. |
| The diagnostic rounded away the offending number | 1,200 | A value of 1.00000000000000001 h was reported as 1.0 h. A negative value of −1e−325 h was reported as −0.0 h. These counts cover both compiler and table diagnostics. |
| Distribution support comparison lost precision | 300 | A uniform distribution with an upper endpoint of 1.00000000000000001 h passed a 1 h upper bound. The whole support must be inside the range. |
| Interactive edit checked the rounded value | 600 | Both −1e−325 and 1.00000000000000001 were accepted at a checkpoint for a value with range [0, 1]. Both should be refused and leave the checkpoint unchanged. |
| Sample exceedance compared a rounded threshold | 600 | Of samples 0 and 1, both exceed −1e−325, and one exceeds 0.99999999999999999. The CLI's evaluation returned shares of 0.5 and 0 respectively. |
| Sample threshold accepted a nonfinite execution value | 1,200 | Positive overflow, negative overflow, NaN and Infinity all reached the exceedance calculation. Each needs a normal CLI diagnostic. |

Every row maps to S6. The two loader exceptions have their original tracebacks in this directory. The ledger also records accepted and refused outcomes as the actual and expected results of each differing observation. The independent controls cover equality, the interior side of a bound, failed-edit atomicity and the reading after a valid edit is saved and resumed.

## Reproduction and evidence

The `local-unit`, `vocabulary`, `negative-cell`, `overflow-cell`, `distribution` and `message` directories each contain a standalone model. Load the named model with `napkin.model.load_scenario`. The `cli` model has two exact readings and a checkpoint at `box.pause.step[0]`. For example, from this directory, `napkin sample --samples 2 --jobs 1 --value box.n,box.one --exceed box.n=-1e-325 --exceed box.one=0.99999999999999999 --json cli` reported zero of two above each threshold. The specified answer is two of two for each. To reproduce the bounded edit, use `napkin play --break 'box.pause.step[0]' cli`, then enter `box.n=-1e-325`.

`baseline.jsonl.gz` retains one line per ID with the incoming SHA, generator checksums, engine/reference diff checksum, status, mismatches, traceback and elapsed time. An independent pass checked that the 900 IDs occur exactly once, all revisions and generator hashes match, all engine/reference diff checksums are null and each failed result names the correct seed and family. The ledger SHA-256 is `c1323bad3e76bc1705f612c4840c0279fb187e1146a4f1562e4f88c80426980e`. Reproduce any seed independently using `python -B -m scratch.rewrite.audit.owner_cases run --id s6/units/0 s6/cells/0 s6/cli/0 --out NEW.jsonl` from the repository root.
