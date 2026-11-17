# Deaths, serious casualties and economic loss

Each scenario owns its consequence research in `scenarios/<ID>/evidence/research.md`, and its
independent checks in `scenarios/<ID>/tests/`. Its README describes the clinical chain, economic
accounts and mechanism family. The generated [scenario catalogue](../../../README.md)
links the available cases.

The calculations keep patient groups distinct, cap care by the service delivered and retain the
time of each outcome. Serious casualties count each person once, including deaths. Economic loss
uses incremental resource costs and lost output in a stated price year; transfers are not losses.

Every input identifies a source result, a transferred relationship, a chosen condition or an
accounting identity. Research notes retain the source population, units, geography, endpoint and
timing, then explain the local application and measurements still needed. Independent expectations
are authored outside engine and presentation code.

An accepted, independently checked conditional estimate keeps its inputs, exposed people, economic
scope, clocks, source transfers and revisions with the report. Source benchmarks retain the source
model's own conditions. A scenario's outcome does not turn its assumptions into measured facts.

`python -B -m tools.evidence.integrate --check --complete` re-extracts original acquired bytes and
matches every executable claim's excerpt. Scientific transfer judgements remain explicit in the
owning scenario's records.
