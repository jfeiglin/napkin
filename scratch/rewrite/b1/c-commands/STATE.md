# C-K: commands, API and tools — state (in progress)

Brief: `briefs/c.md` (C-K) with `COMMON-B.md`; PLAN "Changes after G0" 10-14; C-R, C-D, S6-F STATE.
Baseline b0b1d32 (stage C report committed, 5,151 live tests).

## Order of work
1. `napkin run` on the report: --run, --edits, --lag, status displays, near-ties; the two G1 flaws.
2. `napkin draw` on `Things(compiled).runs`; `napkin compile` checks the stylesheet; the four
   stylesheet tests again in tests/commands/.
3. `napkin new` and `tools/new.py` in the new language.
4. API: `napkin/__init__.py` (no `sample_result`), `engine/__init__.py`, tests/test_api.py CLOSURE;
   `napkin/package.py`, tests/test_package.py, test_nested_packages.py.
5. `tools/compare.py` small over the record; `tools/bench/families.py` over programs.
6. `napkin sample` and `play` once C-S (`b1/c-studies/STATE.md`, "For C-K") is ready.
7. tests/release/wheel_smoke.py; the old tests/test_cli.py, test_cli_tables.py go (ported).

## Done

## Decisions

## Not done / for others
