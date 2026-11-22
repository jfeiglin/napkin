# Publishing the current catalogue

`python -m tools.publish --check` renders every current catalogue entry and verifies the
following files byte for byte. Use `--write` to update them.

| File | Coverage |
|---|---|
| `results/brief.md` in each runnable package or variant | Horizon readings side by side for each declared comparison. Each numeric pair shows the signed difference (run minus baseline) in the reading’s unit, and percentage change when the baseline is positive and its scale supports ratios. When there are no pairs, the page summarizes the featured or first run. |
| `results/readings.md` in each runnable package or variant | All named runs through the horizon. Start and terminal instantaneous readings with the references exercised at those times. The brief chooses the displayed values and featured order. |
| `results/source-dossier.json` in each runnable package or variant | The current model hash, owned external sources and claims, their verification records and which claims its declarations reach. A package with entirely inline evidence has zero external sources. |
| `scenarios/docs/evidence/source-manifest.json` | The shared library and every active catalogue owner's sources, including retrieval metadata where available. |

Select one package or variant with `--scenario ID`, repeating the flag for several. A package
with variants selects its runnable variants. Scoped publication checks their briefs, readings and
dossiers. Use `--only briefs`, `--only readings`, `--only dossier`, or a whole-catalogue `--only manifest` to
select a single format. `--model PATH` renders only readings for a model outside or inside the
catalogue. Both checking and writing build all selected output before touching a publication.

`tools.check --scenario ID` invokes the same scoped publication check. `tools.check --spreads`
and `tools.check --release` also run every selected current `[[spread]]` with its actual edits,
named runs, seed, and sample count. The publisher exposes that check as `--sample-spreads`. It
can take substantially longer than the ordinary publication check. The release command also
runs its deep tests, stored-run replay, release metadata checks and wheel test.

A brief declares comparison pairs in presentation order. Each table names two model runs.
A two-run `featured` list puts that pair first, baseline first in the table.

```toml
featured = ["standard", "nearby"]

[[comparison]]
run = "nearby"
against = "standard"
```

### Sampled comparisons

Add both comparison runs to the same `[[spread]]` and list the readings in its `outputs`. The spread
selects its edits, number of draws and study seed. With `--sample-spreads`, the publisher writes or
verifies `results/paired-spreads.json` for each selected scenario that has at least one such pair.

```sh
python -m tools.publish --write --sample-spreads --scenario ID
python -m tools.publish --check --sample-spreads --scenario ID
```

Each receipt identifies the input edit file by SHA-256 and records the model revision, study seed
and number of draws. The publisher matches each baseline draw to the alternative draw with the
same sample seed. Shared draw sites use the same random numbers when the model executes them in
both runs. The receipt reports the mean and linearly interpolated empirical 5th and 95th
percentiles of each outcome and of the signed differences calculated within each pair of draws.
The percentiles describe variation across simulated outcomes. Relative changes use each draw's
baseline, and every draw must have a positive baseline on a ratio scale. A refused, stopped or
incomplete study causes the sampled command to fail before it writes any results.

The historical methods, assumption inventories, source-verification dossiers, run
tables, HTML and campaign results describe the earlier study. They retain their original
paths and ownership. The active publication result covers the files in the table above.
The earlier release and its publication tools are available at revision `8488047`.
