# Publishing the current catalogue

`python -m tools.publish --check` renders every current catalogue entry and verifies the
following files byte for byte. Use `--write` to update them.

| File | Coverage |
|---|---|
| `results/readings.md` in each runnable package or variant | All named runs through the horizon. Start and terminal instantaneous readings with the references exercised at those times. The brief chooses the displayed values and featured order. |
| `results/source-dossier.json` in each runnable package or variant | The current model hash, owned external sources and claims, their verification records and which claims its declarations reach. A package with entirely inline evidence has zero external sources. |
| `scenarios/docs/evidence/source-manifest.json` | The shared library and every active catalogue owner's sources, including retrieval metadata where available. |

Select one package or variant with `--scenario ID`, repeating the flag for several. A package
with variants selects its runnable variants. Scoped publication checks their readings and
dossiers. Use `--only readings`, `--only dossier`, or a whole-catalogue `--only manifest` to
select a single format. `--model PATH` renders only readings for a model outside or inside the
catalogue. Both checking and writing build all selected output before touching a publication.

`tools.check --scenario ID` invokes the same scoped publication check. `tools.check --spreads`
and `tools.check --release` also run every selected current `[[spread]]` with its actual edits,
named runs, seed, and sample count. The publisher exposes that check as `--sample-spreads`. It
can take substantially longer than the ordinary publication check. The release command also
runs its deep tests, stored-run replay, release metadata checks and wheel test.

The historical briefs, methods, assumption inventories, source-verification dossiers, run
tables, HTML and campaign results describe the earlier study. They retain their original
paths and ownership. The active publication result covers the files in the table above.
The earlier release and its publication tools are available at revision `8488047`.
