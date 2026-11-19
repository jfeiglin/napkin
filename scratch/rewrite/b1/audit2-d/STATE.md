# Audit 2, agent D: units and lifetimes in the front end — state (in progress)

Brief: `briefs/audit2.md` part D, `COMMON-B.md`. Re-audit rows 12, 14, 15, 17, 22. Owns napkin/model/,
napkin/core/units.py, tests/language/, tests/model/; for occurrence references, program/parts.py,
refs.py, build.py, check.py.

## Where each cause acts (listed before any change; semantic.py unless named)
U. Units read by spelling, or by binary floats, not by dimension and exact scale:
- literals: `quantity`, `expression` (bare numbers), `cell` (table cells), `_cell_number`: a decimal
  is a float, and every check below reads it as `Fraction(float)` (0.1 day > 2.4 h);
- scales: `Units.__init__` takes `Fraction(scale)` (a float scale 0.01 is binary), `Resolver.scale`;
- ranges and bounds: `finish` (declaration), `unknown` (domain), `param` (event parameter) through
  `reversed`; `bound`; `within` (initializer, member's own value, cell, option/edit constant);
  `support` (an input that draws); the membership test `n.Within` in `expression` (no check at all);
- distributions: `distribution` with `_converted` (a float converted in floats), then `_broken`;
- `constant` (options, edits: already exact via `Fraction(str)`), `scenario.hours` (horizon,
  resolution, float conversion), runs.py `_value` (edit JSON numbers, through `constant`);
- sqrt: `call` reads powers of the spelling (`h*day`, `ratio` refused); `power` (`**`): a spelling
  times n, exponent must be an `int` instance (`2.0` refused), dimension test for plain bases;
- `product`, `per_hour`, `num`, `declared_type`: compose spellings (dimension and scale exact: OK);
- comparisons and checks by dimension already: `alike` (+ - compare if min max clip in), `duration`,
  `transfer`, `flow`, `rate_setting`, `column`, `keyed` (.at key), `ends_alike`; but `compatible`
  compares `Dist`, `FlowOf`, `EndOf` by `==`, so with their spelling;
- outside the compile path: `evidence.datum_matches` (float scale, rel 1e-12, library only),
  `types.py`/`uncertain.py` (float helpers of tools/publish); program/check.py `_exact` reads a
  float constant as binary (not mine); the engine folds `q` in floats (`0.1 day == 2.4 h` is false
  at run time; ranges are checked with a tolerance there, so no run check flips).
L. Lifetimes: `Occ` is a type of reads only; `declaration` lets a local hold one, lowering `_type`
  gives it TEXT, so `job.crew_size` fails in program/check.py; an entity value or a formula of Occ is
  not refused; `assignment` (formula targets), `rate_setting` (flow and endpoint settings assigned
  in a stage) install a formula that reads the invocation's locals into a longer-lived owner.
K. Keyed reads: `keyed` (.at) types a lookup over its whole source; `Order.starts` ('lookup') walks
  every member of the source, so a fixed key over natural keys reads every entry; the engine's
  `plan.expanded` does the same for a formula (B's).
E. Datum: no compile step compares a value with the datum its record cites (`compile.load_scenario`
  has the library; `support.py` holds the evidence rule; `tools/check.py` filters `no_record`).

## Done
(nothing yet)

## For B / For C / For A / For the main session
(to fill)
