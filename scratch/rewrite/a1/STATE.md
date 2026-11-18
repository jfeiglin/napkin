# A1 state (updated at each milestone; last: checkpoint 2, types.md written by the second agent)

## Second agent (took over after the stop)
- Found: no FINDINGS.md, types.md or typecheck.py on disk (the "draft" below was lost). make_report.py re-run: 0 failures.
- Done: `types.md` (types, read/write table, inference, literal units, the 13 models by hand).
- FINDINGS.md: written in full (rulings R-A1-01..32), but the harness refused the file write for a subagent; its whole text is in the handback message to the main session, to be saved as a1/FINDINGS.md. Parser examples of the rulings are in `rulings/*.scn`.
- Was next: `FINDINGS.md` with rulings R-A1-01..32 (numbers 01-04, 07-10, 14 fixed by citations in parser.py, hunt.py, refused.txt, census). Decision: typecheck.py skipped; FINDINGS says no checker ran.
- Scratch helper: /tmp/claude-0/-home-user-napkin/e09158c7-7039-5d6d-be85-61b3a193adaf/scratchpad/try.sh CONTEXT NAME < snippet (parses a snippet in a context).

## Done, and where
- `corpus/`: 27 `text` blocks and 3 `csv` blocks of the spec, byte for byte (`extract_corpus.py --check`). `MANIFEST.tsv` gives the place of each block (file, members, event). `inline.txt`: 154 inline pieces, by hand. `refused.txt`: 72 pieces that must be refused, each with a part of its message.
- `parser.py`: tokenizer (lex.py rules, each change marked `CHANGED`), precedence parser, lines and blocks. `python parser.py corpus/` gives 27 of 27 parsed. `--tree`, `--expr`, `--context` exist.
- `hunt.py` makes `ambiguities.md`: the 10 items of the brief, grammar rule and 117 cases, all as written.
- `check.py`: 11 checks, all pass (also `pytest check.py --confcutdir=. --rootdir=.`). `make_report.py` runs everything and writes `parse_report.md`, `ambiguities.md`, `census.md`, `census.json`. Run: `PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python make_report.py` (14 s).
- `census_names.py`: names, units and notation of the 23 present `.scn` files, with the old parser.
- `models/`: 13 whole models built from the spec blocks, plus `units.json` and the 3 csv. They parse. They are the fixtures of the type checker that is not written yet.
- `FINDINGS.md`: draft, all rulings written, results partly TODO. `types.md`: not written.

## Decisions taken (one line each)
- Unit = one word after number and one space, grammar `factor([/-]factor)*`, `^n` power; must end at space , ) ] : or line end. Same regex as `napkin/model/types.py:31`. `48 h/2` refused. No model changes.
- `-` stays the unit product: 19 declared units and 125 uses hold it (`person-years`). `{item}/h` dropped (0 uses in the catalogue).
- `<`: collection where a value starts, comparison after a value, type after a colon. Members of a literal are paths. Chains must point one way (0 chains in the catalogue).
- A line may end with `>` (needed by `x: <Pump> = <>`); `>=` after a collection type is split.
- `in` after `=` of a declaration is the range; after `=` of an assignment it is refused; membership needs brackets there.
- Capital first letter = template or enum member; small = value. Parser gives node `Case`. Census: no present name breaks.
- `status` is contextual (second token decides). `bool` reserved; `text`, `number` are type words only.
- Reserved list is `RESERVED` in parser.py; no present model name is in it. Function names are not reserved (`name(` is a call).
- `.start(...)` is a statement and gives no value. A trigger starts only its own event; several unnamed triggers allowed.
- `after D` with no colon = wait with no action. `until C` has no colon. A guard never wraps.
- Comments end a row; `\"` and `\\` are the only escapes; lines continue only inside ( and [.
- `move(s, d, a)`, `at T:`, `assert initially`, `not in`, `within`, `is` are refused with their own messages.
- `48h` check is in the parser, not the tokenizer: claim IDs such as `E-SC43-MEDSTAR-90MIN` need number+name tokens.
- Own nodes via `expr.made`: Quantity, Collection, Member, Method, Formula, Within, Case, Absent. Dotted names stay one `Ref`.

## In the middle of
- Writing `typecheck.py`: a small checker of the rules of types.md over `models/*.scn`, plus seeded errors (planned list is in FINDINGS.md under "Types: planned checks"). Nothing of it is on disk yet.

## Remaining steps, in order
1. `typecheck.py` + seeded wrong models; add its run to `make_report.py` and `check.py`.
2. `types.md`: types, read/write table by scope, inference rules, where a literal gets its unit.
3. Finish `FINDINGS.md` (fill TODO numbers from `make_report.py`; "Not covered").
4. Run `make_report.py` once more; final 300-word message through SubagentHandback.
If time is short: skip step 1, write types.md from the design notes in FINDINGS.md, say plainly that no checker ran.

## Facts learned that are in no other file
- `import napkin` without PYTHONPATH gives the checkout (editable install); `sys.path.insert(0, base)` in parser.py wins over it.
- `pytest` in this folder needs `--confcutdir=. --rootdir=. -p no:cacheprovider`, or the repo `conftest.py` breaks collection.
- Importing `napkin.model.language.lex` loads numpy and scipy (0.2 s); parser.py copies Token/Line/fold/tree instead (check 1 proves they are identical).
- `expr.made` interns own node kinds; a Quantity must hold its number as a `Const`, or `2` and `2.0` become one node.
- The old lexer's word list `NOT_UNITS` holds clause words (`size`, `limit`, `order`): any word that A5 puts after a bare number (`= 0.6 size 1`) must be reserved, or the new tokenizer reads it as a unit (83 present lines).
- The spec itself declares `flow use:` and a field `hour`: `use` cannot be reserved, and a value may share the name of a unit.
- The library declares `fraction` and `ratio` as dimensionless units (344 uses as types); `duration` is a type word for `h` (`napkin/model/types.py:22`).
- All present distributions are bounded (`napkin/distributions.py:6`): `normal(mean, sd, min, max)`. The spec's `normal(2, 3)` is new.
- Dead end: making the tokenizer treat `<` as a bracket for line continuation. It cannot know comparison from bracket.
- Dead end: a lexer error for `48h`; it broke two claim IDs of the catalogue.
