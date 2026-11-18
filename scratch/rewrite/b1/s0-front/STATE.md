# S0-F: the front end, first slice — state

Brief: `scratch/rewrite/briefs/s0-front.md` (with `COMMON-B.md`).

## Plan (modules)

- `napkin/model/language/problems.py`: `Problem` (code, message, line, column, file), `LanguageError`.
- `language/lex.py`: rows → logical lines and tokens (trailing `#` comments, `\"` `\\` escapes).
- `language/nodes.py`: the tree (expressions, types, every line of the spec); places compare=False.
- `language/parse.py`: one tree for one text. Units by D12 are a structural *unit run* after a number
  (`Quantity.unit` = ((op, name), ...)); the declared model splits it at the first name that is no unit.
- `language/format.py`: tree → text; stable; brackets a quantity before `* name`.
- `language/evidence.py`: the projection of records that `napkin/model/evidence.py` walks.
- `language/modules.py`: role, package, `library` line, the files of a model (`use` lines).
- `napkin/model/semantic.py`: the declared model (typed IR, paths = program origins); later-slice
  constructs kept as `Deferred` parts.
- `napkin/model/lowering.py`: declared model → `napkin.program.build` → `finish()`; refuses Deferred.
- `napkin/model/compile.py`: `compile_text`, `load_scenario(path)` → (declared, program, configuration).
- Deleted (old front end): language/{expressions,front,resolve,tables}.py (tables return in S1).

## Done

- (nothing yet)

## Decisions

- D-1 Unit run is structural; meaning is plain arithmetic either way (D12), a name is a unit when the
  library has it and the run has not stopped. `scale` is reserved (else `8 scale ...` reads a unit).
- D-2 Comments are kept for the formatter but do not take part in tree equality.

## Next

- write the modules above, then tests in `tests/language/`.
