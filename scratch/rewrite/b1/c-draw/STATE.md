# C-D: draw over the declared model — state

Brief: `scratch/rewrite/briefs/c.md` (C-D), with `COMMON-B.md` and PLAN "Changes after G0" 10-14.
Own: `napkin/draw/`, `napkin/model/views.py`, `tests/draw/`. Not `commands/draw.py` (C-K's).

## Plan (milestones)

1. `draw/text.py` gains `in_words`; new `draw/things.py`: what the picture reads of a `Compiled`
   (cards, kinds by use, reads resolved to cards, runs and reach, the library, written texts).
2. `style.py` over `things` (TOML reading unchanged).
3. `triggers.py`: words of conditions over the typed form; event lines of the new events.
4. `model_map.py`: `picture` (cards, stocks, pipes, machines, triggers, arrows, groups, facts).
5. `notation.py` (build from the typed form), `symbols.py`, `equations.py`, `panels.py`,
   `references.py` (new evidence).
6. Tests: each old file ported; catalogue tests in `tests/draw/test_catalogue.py` (wait for M).

## Decisions (D-n of C-D)

- D1 Draw reads a `Compiled`; the style file is looked up beside its entry file
  (`declared.files[-1]`), none for a text.
- D2 A card is an entity written once, a member written by hand, or a table (its rows share one
  card, `copies` = rows). A template has no card. The top level has no card: no arrow to it.
- D3 Kinds by use (change 14): a stored number at an end of a flow, leg, route or move is a stock,
  a tally when nothing drains it; a stored value that nothing writes is `fixed`; else `state`.
- D4 A machine is a stored enum value; a transition is an assignment in a stage, from the states
  that its stage's guard and enclosing branches allow (and the triggers', when every start of the
  event is a trigger and the stage is its first step after 0 h).
- D5 `--run` leaves out the events that reach (D16) proves cannot start under the run's
  configuration; joined, an event is drawn when it can start in one run or more. The runs are the
  named runs, else the default run.
- D6 No `versus`, no `output`, no `delayed`, no braces in texts (`filled` and `map_payload` go).

## Done

(nothing yet)

## In progress / next

Milestone 1.
