# S4a-E state: the engine, part one of S4 (occurrences and time)

Brief: `briefs/s4.md` (S4a-E) with `COMMON-B.md`, `s0-engine.md`, `s1.md`..`s3.md`; `b1/s3-engine`.
Baseline before S4a: `tests/engine tests/core` 1684 passed in 84 s (-n 2).

## Design (decided)
- Plan grows at run time: `plan.occurrence(receiver, event, index, args)` adds an occurrence's
  values (params, locals, builtins started/done/active, status) and flows under engine names
  `R.E#n.<name>`; paths of an event resolve with a frame (`Local` -> engine name). The reader
  replays the starts of the trace (args in the start entry) into its plan, so a record suffices.
- Dynamic collections (`.occurrences`, endpoint `.flows` when the program has event flows),
  `.at(t)` of occurrences and `since(e)` are derived values evaluated at a time from the live
  membership (run) or from `started`/`active` histories (reader).
- Ways take moments by **rebuild of touched sets**: a moment's settle reads the state of every
  touched set (a store written, a setting's read written, a flow joined/left, a read rate
  changed), retires it from its instance, recomputes connected sets of the region, and builds new
  instances at tau (family and lines: one new instance per dependency level; component and sparse:
  one per set). Untouched sets go on. Levels: a set whose settings read rates of another comes after.
- Global loop: ways expose `peek()` (next internal event), `step()` (commit it), `cut(tau)`
  (component/sparse commit a pending segment/step up to tau). Next moment = min(discrete times,
  contacts). An internal event that changes what a watched condition reads makes a moment there.
- Conditions: atoms (comparisons) on moving values hold within the tolerance of what they read;
  contacts predicted on trajectories (closed form when linear, else sampled + bisection); a
  strict atom whose difference moves is a diagnostic when watched (as the oracle).

## Done
- (nothing yet)

## In progress
- M1: plan accepts events/setup/enums; occurrences, stages, rounds, discrete triggers, clocks.

## Steps that remain
- M2 writes to stores in ways, continuous triggers; M3 occurrence flows joining/leaving;
  M4 reader; M5 oracle compare + random generator; M6 ports/deletes; M7 benchmark.
