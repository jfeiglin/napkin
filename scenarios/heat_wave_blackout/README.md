# Electricity restoration during a heat wave

Start with an observed loss of electricity. The utility isolates the interruption, assesses it and completes its safety checks. Crews then restore a share of service as they finish each hour of switching work. Earlier outreach and powered cooling sites can protect residents while they wait.

Open [explore.ipynb](explore.ipynb) to compare early, standard and delayed cooling responses, inspection schedules, and the backup-power and access options. The notebook shows service and admissions through time, compares end-of-run readings and evaluates a selected sensitivity from the brief. It also plots them when Matplotlib is installed. [The migration record](MIGRATION.md) identifies the work-order inputs and the comparisons with the historical release.

Run a named response from the repository root with:

```sh
.venv/bin/napkin run scenarios/heat_wave_blackout/model.scn --run standard
```

The health estimates are conditional expectations for the populations and exposures in the model. The evidence and assumptions for each reading travel with its source or compiled artifact.

[Current recovery readings](results/readings.md) accompany this version. The methods, tables and evidence reviews in [results/](results/) are historical publications for the legacy model at `8488047`.

The [current brief](results/brief.md) reports completed comparisons. The optional inspection exercise admits reports on a fixed schedule or schedules a follow-up once the previous work clears. An acknowledged stop order withdraws future reports at detection. Unconfirmed orders require containment. The [paired spread](results/paired-spreads.json) compares response choices at matched intervals and workloads. [Timing inputs, sampling and historical coverage](MIGRATION.md#inspection-schedules)
