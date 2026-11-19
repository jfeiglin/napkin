# Re-audit fix B: time, and evaluation that recurses (track b1/audit2-b)

Brief: `briefs/audit2.md` part B, `briefs/COMMON-B.md`, D's "For B". Owns engine/timeline/{triggers,
moment,occurrences,run,chance,plan,collections}.py, new tests/engine files.

## Where each cause acted (listed before any change)
Time (04): a time built from durations, or compared with another time.
- occurrences._schedule `due = now + delay`; occurrences.due + moment.rounds (round 1 took due <=
  t + crossing, later rounds <= t; `next_due() != t`); triggers.fire `rearm_at = now + D`;
  conditions `t >= rearm_at` (exact: row 04); next_timer; triggers._exact_root (`t` against what
  holds) and the line's root (`since`, `elapsed`); _contact `now + crossing`; run.loop
  `now < horizon`; run.discrete; run.keyed_changes; run.next_moment (contact within crossing).
Recursion (15): walks through formulas, reductions, keyed and dynamic reads.
- run.Run.value (~140 links); collections.reduced/looked_up/dynamic_value call it per entry;
  plan.expanded <-> expansion <-> lookup_reads <-> _members_part (~500 links); plan.ordered;
  plan._fixed; triggers._truth, _atoms, _weights, _affine; moment.near_ties; record (agent C).
- Not the graph (bounded by one expression or path): plan._renamed, _uses, folded, _step,
  _statements; collections._answered, Ends.keeps/reads; moment.execute.
Moments (13): chance.described, normal and lognormal with bounds (mass a difference of ndtr: 0/0).

## Done
- Time: `moment.Clock`, called by every path above (moment.py docstring). Exact: a duration's
  expression in exact arithmetic (`core.units.rational`, exact scales), its sum with the time exact,
  rounded once (`later`); roots of comparisons whose only moving read is the time, exact
  (triggers._exact_root). Due: at most `crossing` after a moment's time as it begins (`due`; later
  rounds exact); the horizon is due at the first moment within it; a known moment due at a contact
  or a way's event is that moment, at its time (run.next_moment). Saved state unchanged (floats).
- Moments: Gauss-Legendre in the tail that holds the interval (`_tail`, `_points`, `truncated`,
  `log_mass`); lognormal by shifted masses, or by its points where narrow; closed forms with no
  cancellation (triangular, loguniform `_excess`, beta).
- Recursion: one driver, `plan.walked` (generators yield what they need; a compiled evaluation
  raises `plan.Pending` and runs again, its reads kept): the start (`Run._starting`), the present
  (`Run._derived`, `_evaluated`, `_ask`: a reduction asks for all its entries at once),
  `plan._expansion_of`, triggers `_truth_of`, `_atoms_of`, `_weights_of`, `_affine_of`,
  `near_ties.decided`; `plan.ordered` and `_fixed` are loops.
- D's For B: exact `unit.scale` (plan.py); occurrence references bound at the entry (`_referred`),
  D's xfail dropped; a constant key over natural keys reads its entry alone (`_chosen`).
- Tests: test_clock.py (144; 46 fail with float sums), test_bounded_moments.py (mpmath, 50 digits),
  test_deep_graphs.py (1,500 to 3,000 links, recursion limit 400), test_references_and_keys.py.

## Decisions
- Time: both parts of one clock: exact alone cannot place a time that carries a computed value's
  roundoff; a tolerance alone leaves a summed time a roundoff from the written one (a reader at
  0.3 h misses 0.30000000000000004 h, chains drift). A third of an hour has no decimal: its chain is
  at the right moment, a roundoff off in time. Key times of `.at(t)` on fixed keys stay exact.
- Present: a derived value is computed once per read of the present (shared by its readers).
- Changed expectation: test_roundoff_properties: a delay's time is the exact sum of the decimals
  that write the doubles (the oracle's `number`), within k - 1/2 ulps for k delays (was k/2, binary).

## For A (the oracle)
- Engine times are the floats of the oracle's exact times for decimal durations (0.1 day = 2.4 h);
  a moment due at a contact or at a way's event takes the known time.

## For C (the reader)
- record._Values.at recurses (row 15): make `at(name, t)` = `walked(self._at(name, t))`, `_at`
  reading with a `read` that raises `plan.Pending(r)` for a derived name not in `self.done`, yielding
  `self._at(r, t)` and evaluating again; a reduction asks for all entries at once (`Run._ask`).

## Status
- done. Final command: 4553 passed. `-m deep` occurrences + random draws: 3000 passed. ruff clean.
