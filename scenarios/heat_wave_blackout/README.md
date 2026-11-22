# Electricity restoration during a heat wave

Start with an observed loss of electricity. The utility isolates the interruption, assesses it and completes its safety checks. Crews then restore a share of service as they finish each hour of switching work. Earlier outreach and powered cooling sites can protect residents while they wait.

Open [explore.ipynb](explore.ipynb) to compare the three cooling responses. The notebook reads service and admissions at nine times through Napkin’s public Python API. It also plots them when Matplotlib is installed. [The migration record](MIGRATION.md) identifies the work-order inputs and the comparisons with the historical release.

Run a named response from the repository root with:

```sh
.venv/bin/napkin run scenarios/heat_wave_blackout/model.scn --run standard
```

The health estimates are conditional expectations for the populations and exposures in the model. The evidence and assumptions for each reading travel with its source or compiled artifact.

[Current recovery readings](results/readings.md) accompany this version. The older brief, methods, tables and evidence reviews in [results/](results/) are historical publications for the legacy model at `8488047`.
