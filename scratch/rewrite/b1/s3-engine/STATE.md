# S3-E state: the engine, fourth slice (reversible routes, flows with legs) — IN PROGRESS

Brief: `briefs/s3.md` (S3-E), with `COMMON-B.md`, `s0-engine.md`, `s1.md`, `s2.md`.
The last slice: `b1/s2-engine/STATE.md`.

## Steps
1. Carry-over A: `bench.py moving 30000 35000` fails at t = 41.94 h ("break a hard row"); find
   the cause, mend, or name the part.
2. Carry-over B: speed of lines (`bench.py held 30000 35000`, 87 s); profile, mend what is cheap.
3. Routes: one signed coordinate, legs `forward`/`backward` in the network.
4. Legs: one served fraction through local sharing; zero legs.
5. Plan: paths `.forward`, `.backward`, `.served_fraction`, legs in `priority(...)`, `.source/.sink`.
6. Examples + oracle; random networks with routes and legs (`test_local_sharing.py`).
7. Ports: test_coupled_queue_boundaries, test_chattering, test_closed_form_short,
   test_roundoff_properties.
8. Benchmarks, last message.

## Done
(nothing yet)
