# Audit 2, agent D: units and lifetimes in the front end — state (done)

Brief: `briefs/audit2.md` part D, `COMMON-B.md`. Rows 12, 14, 15, 17, 22. Owns napkin/model/,
napkin/core/units.py, tests/language/, tests/model/; for occurrence references program/parts.py,
build.py, check.py (refs.py unchanged).

## Where each cause acted (listed before the changes; semantic.py unless named)
U (by spelling or binary float): literals (`quantity`, `expression`, `cell`); scales (`Units`); ranges
`finish`/`unknown`/`param` via `reversed`, `bound`, `within` (inits, members, cells, `constant`),
`support`, the test `in [lo, hi]` (unchecked); `distribution`+`_converted`+`_broken`; `scenario.hours`;
sqrt in `call` and `power` (powers of the spelling, `2.0` refused); `compatible` (`Dist` by `==`);
the run's `q` (core `normalize`, float product: `0.1 day == 2.4 h` false). By dimension already:
`alike`, `duration`, `transfer`, `flow`, `rate_setting`, `column`, `keyed`, `ends_alike`.
L: `declaration` (an Occ local lowered as TEXT, so `job.f` failed in check.py; Occ not refused
elsewhere); `assignment` and `rate_setting` (a formula reading the invocation installed for the run).
K: `keyed` and `Order.starts` read every member of a lookup's source; engine `plan.expanded` too.
E: nothing compared a value with its cited datum (`compile.load_scenario` holds the library).

## Done (one mechanism each)
- U: `core.units.rational` (a float is the decimal that writes it) and exact scales
  (`UnitRegistry.exact_scale`); `normalize` converts once, rounded once. Front end: `exact_value`
  (canonical Fraction of what the model fixes), read by `interval` (ranges, domains, parameters, the
  interval of a test: reversed is `range` wherever it stands), `within`, `support`, `_converted`,
  `_broken`, `constant`, the horizon (exact hours); `raised` for sqrt and `**` (dimension powers times
  the exponent, whole; exponent a literal read exactly; unit from the operand's names, else
  `unit_for`); `compatible` by dimension inside `Dist`/`Many`.
- K: `Resolver.chosen`/`created`: a fixed `.at` over instances or a literal is the member's id (in
  the program too); `Order.chosen`/`known`/`select` per member (where on links, a member's own
  collection, `by` of stored starting values written out).
- E: `support.cited_data` (code `datum`) from `load_scenario`: exact, within half the datum's last digit.
- L: `Resolver.lifetime`/`own_place` (code `lifetime`); Occ only as an event local (`occurrence`),
  fixed (`fixed_write`); `parts.OccurrenceType`, `build.occurrence_of`, check.py (`step`, `init`,
  `type`, `assign`, `local_order`), lowering `_type`/`initial`.
- Rule tests: model/test_units.py `test_respelling_...` (hypothesis); language/test_collections.py
  `test_a_fixed_key_reads_...` (against the run's own lookup); language/test_events.py
  `test_a_formula_reads_only_...` (every place x read). Rows: test_semantic.py (12, 22, cyber line
  840), test_collections.py (15), test_evidence_rule.py (17), test_events.py (14), test_units.py (run).
- Changed expectation: tests/core/reference.py `q` is the decimal times the exact scale, as the
  oracle (`tests/reference/from_program.py`) already reads it. Messages: see the final report.

## Decisions
- Runs convert literals exactly (core), since a run's `==` is a comparison too.
- A test's interval is checked when both ends are fixed when the model compiles; an end that only a
  run knows is tested as written (the program has no membership operation to fail on).
- Precision of a datum: half a unit in its last written digit. `by` keys count only as starting values.

## For B
- plan.py `occurrence()`: bind a local of `OccurrenceType` when its occurrence enters, in written
  order, to the occurrence that its init path names (`frame.names[name] = ('occurrence', id)`; no
  Value, no record); a read steps from it as from `.at(t)`, frozen after it finishes; then drop the
  xfail of tests/language/test_events.py `test_a_saved_reference_keeps_naming_...`.
- plan.py:473 pass `unit.scale` (exact) to `UnitSystem`, so 1/60 h converts exactly.
- `expanded`/`_keyed`: a key that is a constant over fixed natural keys reads its entry alone (a
  member's own collection keeps the lookup); a distribution value starting from another's path
  (allowed by the program) is refused as a type error.
## For C
- proofs.py:227 pass `unit.scale`; the record and the report hold no value of an occurrence reference.
## For the main session
- tools/check.py:218 refuses `no_record` only: refuse `support.DATUM` too (`item.code in (CODE, DATUM)`).
