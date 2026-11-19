# Re-audit fix B: time, and evaluation that recurses (track b1/audit2-b)

Brief: `briefs/audit2.md` part B with `briefs/COMMON-B.md`. Owns engine/timeline/{triggers,moment,
occurrences,run,chance,plan,collections}.py and new files in tests/engine/.

## Where each cause acts (listed before any change)
Time (04): a time built from durations, or compared with another time.
- occurrences._schedule `due = now + delay` (stages, `after D`, delays after a settling)
- occurrences.due + moment.rounds: round 1 takes due <= t + crossing, later rounds <= t;
  `next_due() != t` asks for another round
- triggers.fire `rearm_at = now + D`; conditions `t >= rearm_at` (exact: row 04); next_timer
- triggers._exact_root (`t` against what holds: triggers and gates on the time); the line's root
  `now + start/(start-end)*(until-now)` (`since(e)`, `elapsed(x)`); _contact `now + crossing`
- run.loop `now < horizon`; run.discrete; run.keyed_changes (exact lookup of key times);
  run.next_moment (a contact within crossing before a known moment joins it)
- `.occurrences.at(t)`, `since` (keys: `started` = a moment's time), `elapsed` (changed_at)
Recursion (15): walks through formulas, reductions, keyed and dynamic reads.
- run.Run.value (~140 links); collections.reduced/looked_up/dynamic_value call it per entry
- plan.expanded <-> expansion <-> lookup_reads <-> _members_part (~500 links); plan.ordered
  (visit); plan._fixed (through keyed reads)
- triggers._truth, _atoms, _weights, _affine; moment.near_ties (decided)
- record._Values.at (agent C)
- Not the graph (bounded by one expression or path): plan._renamed, _uses, folded, _step,
  _statements; collections._answered, Ends.keeps/reads; moment.execute
Moments (13): chance.described, normal and lognormal with bounds (mass as a difference of ndtr,
0 in a far tail, then 0/0); uniform, triangular, pert, loguniform: closed forms (to check).

## Status
- in progress: the list above; nothing changed yet
