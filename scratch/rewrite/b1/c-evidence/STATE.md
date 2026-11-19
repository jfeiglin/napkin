# C-E: evidence tools — state (in progress)

Brief: `briefs/c.md` (C-E) with `COMMON-B.md`; PLAN "Changes after G0" 10-13; `b1/c-report/STATE.md`.
Own: `tools/evidence/`, `tests/evidence/`, `tests/model/test_pages.py`. Not `napkin/`, not `tools/publish/`.

## Plan
1. `tools/evidence/trail.py` (new): record uses of the declared model (`uses`, `summary`, `entities`),
   what a value rests on (`rests_on`, over `program.proofs.reads`), and the evidence of a report's
   trail resolved in the library (`evidence`), with a command (`python -m tools.evidence.trail`).
2. `integrate.py`: pack integration and `--check` unchanged; `--coverage` rewritten over `trail.py`
   (no outcomes: D10; no initiation: the start of an incident left in S4); readers' documents read
   the whole package (`trail.package_document`).
3. `adopt.py`: its own unit helpers (`identity.declared_units`, `unit_names` are gone).
4. `manifest.py`: unchanged; `artifacts(root)` and `PATH` keep the publisher's interface (M).
5. Tests: `tests/evidence/support.py` writes synthetic packages in the new language; port each file;
   every test that reads the catalogue or the publisher goes to `tests/evidence/test_catalogue.py`
   (waits for M). `tests/model/test_pages.py`: names in words and the texts the pages read.

## Done
- `tools/evidence/trail.py` (new, with its command); `integrate.py` (coverage over trail.py, the
  readers' documents of whole packages); `adopt.py` (own unit helpers, package documents);
  `__init__.py`. `manifest.py`, `fetch.py`, `normalize.py`, `cache.py` unchanged.
- `tests/evidence/support.py` rewritten: `SERVICE`, `QUEUE`, `family`, `write_package`,
  `evidence_library`, and the pack helpers (moved from test_evidence_tools.py).
- Ported and passing: test_cache (3), test_evidence_tools (58, 1 skip: no Ghostscript),
  test_source_manifest (7), test_commands (36), test_adopt (7).
- In progress: test_evidence_report, test_index, test_assumption_disclosure, test_library_integrity,
  test_catalogue (new, M), tests/model/test_pages.py.

## Decisions
- (to come)

## For napkin/ (not mine)
- `library.model_document(path)` parses the entry file alone: the records of a package's modules and
  of a variant's package are missed, so `load_library(path)` without a document reports their local
  records unused and checks none of their references. It should read the files as `load_scenario` does.
