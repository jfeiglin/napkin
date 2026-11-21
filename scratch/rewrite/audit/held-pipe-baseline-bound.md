# Lower bound on the 30,000-pipe baseline

One fresh execution of the frozen full-record benchmark used baseline `6202824`, workload commit `0f0fcb2` and arguments `30000 --full-record-only`. An interrupt reached the original `Run.run` call at 75.003919458 seconds, before it returned. The official run-and-record clock includes both constructing the run and executing `run()`, so it exceeded **75 seconds**. The benchmark produced no final baseline physical readings or exact total. The separate 12,653-second process cutoff from the earlier pilot includes setup and uses another clock. [Raw bounded measurement](held-pipe-baseline-bound.json)

The single new process, including setup and shutdown, took approximately 83 seconds. There was no warmup. Single-threaded BLAS and the disabled run cache match the guard protocol. A separate instrumented baseline held-network process was running on another core. The supervisor limited the child to 175 seconds. The measured script was committed at `9f3e699`, and its source digest is in the JSON. [Measurement and comparison code](held_pipe_bound.py)

For candidate `e027caa`, all twelve physical checks passed and full run plus record took 24.019215125 seconds. Dividing by the certified baseline lower bound gives **F/B < 0.320257** for those measurements. The exact ratio remains unknown. Reuse the bounded measurement with the completed release sample. The command checks the frozen workload digest, inputs, BLAS settings, machine, Python version, twelve observations and candidate output checksum before reporting a bound.

```sh
.venv/bin/python -B scratch/rewrite/audit/held_pipe_bound.py --compare \
  scratch/rewrite/audit/held-pipe-baseline-bound.json \
  PATH_TO_RELEASE_GUARD/guard/held-pipes.1.F.json
```

The original measurement used the following command. The checked-in JSON suffices for a new comparison.

```sh
.venv/bin/python -B scratch/rewrite/audit/held_pipe_bound.py \
  --baseline .work/engine-finalized-baseline --harness .work/engine-finalized-held-protocol
```
