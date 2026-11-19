# C-E: evidence tools — state (in progress)

Brief: `briefs/c.md` (C-E) with `COMMON-B.md`; PLAN "Changes after G0" 10-13; `b1/c-report/STATE.md`.
Own: `tools/evidence/`, `tests/evidence/`, `tests/model/test_pages.py`. Not `napkin/`, not `tools/publish/`.

## Done
- `tools/evidence/trail.py` (new): `uses`, `summary`, `entities`, `part_uses`, `rests_on`, `evidence`,
  `reached`, `disclosures`, `package_tree`, `package_document`, `built`, and the command
  `python -m tools.evidence.trail MODEL PATH... [--run NAME]`.
- `integrate.py`: pack integration and `--check` unchanged; `--coverage` over `trail.py` (no outcomes:
  D10; no initiation: the start of an incident left in S4); readers' documents of whole packages.
- `adopt.py`: own `unit_names`/`declared_units`; each library read with its package's records.
- `__init__.py` (five commands). `manifest.py` unchanged: `artifacts(root)`, `PATH` feed the publisher (M).
- `tests/evidence/support.py`: `SERVICE`, `QUEUE`, `family`, `write_package`, `evidence_library`,
  `fixture_claim` and the pack helpers (moved from test_evidence_tools.py).
- Ported, passing: test_cache 3, test_evidence_tools 58 (+1 skip, no Ghostscript), test_source_manifest
  7, test_commands 37, test_adopt 7, test_evidence_report 4, test_index 10, test_assumption_disclosure 3,
  test_library_integrity 24.

## In progress
- tests/evidence/test_catalogue.py (new, waits for M); tests/model/test_pages.py; final runs.

## Decisions
- E1 Evidence of a run = the trail's parts and their records; `reached` from exercised parts only,
  `possible` from the rest. A value's part also takes its member's own line (or its table column)
  and the settings of the run's options (every option for `rests_on`).
- E2 Coverage drops outcomes (D10: the caller selects values; `trail` answers per value) and the
  initiation line; it reads models with `allow_unused` so a pack's new claims show as unused.
- E3 Disclosures replace the study's evidence warnings for a reported value: each claim not verified
  and each assumption not confirmed of the exercised parts.
- E4 test_scientific_spec.py is left as it was (dormant, M): its subject (an input's
  `range_rationale`/`control` notes) has no form in the new language.

## For napkin/ (not mine)
- `library.model_document(path)` parses the entry file alone: modules' and a variant's package's
  records are missed, so `load_library(path)` without a document reports their local records unused.
  Worked around in `trail.package_document`; `load_scenario` takes no library (`trail.built`).
- `proofs.reads`: a flow's request or capacity that a stage assigns does not follow that stage, so a
  trail misses the event (seen with `this.serve.request = 0 people/h` in a stage).
- `report._Trail.cites` reads the template part's records only, not a member's own line or an option.
- The datum check (`evidence.datum_errors`) has no caller: a datum must name data of its claim, but a
  value is not compared with it. Provenance diagnostics have no line; the walker's paths of unnamed
  parts are indexes (`service.members[7]` for `service.status.case[0]`, `notes[11]`).
