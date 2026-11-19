# C-D: draw over the declared model — state (done)

Brief: `scratch/rewrite/briefs/c.md` (C-D), with `COMMON-B.md` and PLAN "Changes after G0" 10-14.
Own: `napkin/draw/`, `napkin/model/views.py` (unchanged: S4's API serves draw), `tests/draw/`.

## Done

- New `draw/things.py`: the one reader of a `Compiled` (cards, kinds by use, reads resolved to
  members through links and collections, runs and reach, the library, texts from the tree).
- Ported over it: style.py (model half), triggers.py, model_map.py, notation.py (build from the
  typed form, `Keys`, `walk`; nodes and LaTeX kept), symbols.py, equations.py, panels.py (model
  half; data() and the LaTeX fragment kept), references.py (new evidence), text.py (`in_words`).
  layout.py: no `versus`. svg.py, typeset.py, icons.py, defaults.py unchanged.
- Gone: system_map, map_payload, texts_of, filled, card_title, event_line, to_node, literal,
  Since/Count `ending`, tests/draw/system-map.json.
- Tests (by file; none over 10 s, so no `deep`): icons 44, layout 48, svg 27, typeset 83,
  notation 101, references 34, style 163, symbols 56, triggers 32, trigger_levels 42, model_map 10,
  picture 37, equations 16, panels 77 (+1 skipped: no TeX engine), drawn_panels 34; tests/core 395.
- Helpers: tests/draw/models.py (WORKS, compiled, package with a shared library, fixture_claim);
  latex_subset.py (events without outcomes). test_catalogue.py: every catalogue check, for M.
- Dormant: every file of tests/draw/ can leave tests/dormant.txt but test_catalogue.py (M).

## Decisions (D-n of C-D)

- D1 Draw reads a `Compiled`; the stylesheet is beside its entry file (`declared.files[-1]`).
- D2 A card: an entity written once, a member written by hand, or a table (rows share it, `copies`
  = rows). A template has no card; the top level has none, so nothing points to its values.
- D3 Kinds by use (change 14): a store at an end of a flow, leg, route or move is a stock, a tally
  when nothing takes from it; a stored value that nothing writes is `fixed`; else `state`.
- D4 A transition starts from the states that its stage's guard, its branches and a case of a
  switch on the state allow, and the triggers' when every start is a trigger and the stage is the
  first, after no delay.
- D5 `--run` and the join leave out what reach (D16) proves cannot start; the runs are the named
  runs, else the default. "only with/not with" names options that set an input.
- D6 A flow's line is `request(f) = r`; its capacity is a bound `f ≤ c` (`|f|` for a route); an
  endpoint is a share (`outflow(S) ≤ c`, `priority(...)`); legs move at one served fraction; a jump
  keeps the case of its switch as its outcome. No implicit lower bound 0.
- D7 Keys nest for parts (`site.restore.labor`, `grinder.refill.amount`); a read that only a run
  resolves (a keyed collection) is its words in the math (`Text`).
- D8 A solver's solve_for is a change ("solves"). An event line: its triggers with resets, its
  callers and the setup, its steps (stages, gates, waits, branches, switches), its runs.
- D9 `Things.library` reads the library again from the entry file: `Compiled` does not keep it.

## For others

- C-K: commands/draw.py reads `model.runs` (old): the runs are `Things(compiled).runs`; its
  command tests of the stylesheet (3 in test_style, 1 in test_trigger_levels) were dropped here.
- Model owners (optional): `Compiled.library` would save draw a second read of the library.
- M: tools/publish imported `model_map.filled` (gone) and style helpers (kept). F: docs/draw.md.
