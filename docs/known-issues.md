# Known issues and possible future features

This page lists the known issues of the engine, the tools and the notebook of the catalogue, and the
features that could come next. Each row says what we know now. A row goes when its issue is fixed or
its feature is done: the change that does it removes the row and says so in
[CHANGELOG.md](../CHANGELOG.md).

## Known issues

| Issue | Effect | What to do now | Possible fix |
| --- | --- | --- | --- |
| **The notebook uses internal names.** `scenarios/heat_wave_blackout/explore.ipynb` uses `napkin.store` (`store.use`, `store.default_directory`) and `napkin.engine.edits_for`. Neither is in the public API (`_EXPORTS` in `napkin/__init__.py`, [python-api.md](python-api.md)). | A change to these names can break the notebook, and no test finds it. | Run the notebook after a change to `napkin/store.py` or `napkin/engine/`. | Make these names public. Add the smoke test of the notebooks (below). |
| **No test runs the notebook.** | The notebook can fail at a path of a model that a change removed or renamed. | Run the notebook by hand after a change to its model. | Add the smoke test of the notebooks (below). |
| **The libraries of the notebook have no pinned versions.** Jupyter and Matplotlib are not in `requirements.lock` or `pyproject.toml`. | A new version can change how the notebook draws its chart. Without Matplotlib, the notebook prints its table and draws no chart. | Install a Jupyter host and Matplotlib, if a chart does not draw. | Add an optional extra `notebook` with pinned versions, and pin them in a lock file. |

## Possible future features

A feature that needs more than a row has a page of its scope and its plan in the folder
`docs/scoping/`, and its row links to that page.

| Feature | What it gives | What it needs |
| --- | --- | --- |
| **Faster declared solvers** ([scope and plan](scoping/solver-speed.md)) | Named precision profiles (`default`, `fast`) in the identity of a run, a looser tolerance of fair sharing, and a path by an interior-point algorithm. Each keeps the books, the equal shares and the bounds exact, with a fallback by name. Answers for need x1.45 and x1.7 at 30,000 places. | Three speedups that change no answer are done. The rest needs an exact polish of an interior-point answer at scale, the approval of the profiles by the owner, and an answer for the open cases. |
| **A notebook for each other package of the catalogue** (`scenarios/<package>/explore.ipynb`) | A reader changes the inputs that the story turns on and sees the outcomes. Each notebook shows what matters for its own case, as the first one does. | One notebook at a time, written for its case. |
| **A public API for what the notebook uses** | `store.use`, `store.default_directory` and `edits_for` become part of the public API, so a notebook or an application uses no internal names. | Entries in [python-api.md](python-api.md), and tests of these names as public functions. |
| **A smoke test of the notebooks** | A test that finds each notebook of the catalogue, checks that the committed file has no outputs, and runs it without a browser. | nbclient and ipykernel in the requirements of the tests. |
| **Pinned libraries for the notebooks** | The same versions of Jupyter and Matplotlib for each reader. | An optional extra `notebook` in `pyproject.toml` and the versions in a lock file. |
| **Shared helpers for the notebooks** | One copy of the code that the notebooks repeat, for example the function that runs named runs through the run store and checks that each run reached its horizon, and the table that compares two runs. | More notebooks that repeat that code first. The helpers go in `tools/`, read names from the model only, and name no package. |
| **Small spreads in a notebook** | The spread of the outcomes of a spread of the package (`spreads/<id>.json`), with fewer samples, while the reader waits. | The time of one run times the number of samples, shown before the start. The reader starts the spread. |
| **Charts of values that the model does not name** | For example, a chart of the temperature that people feel at home without power. | A named value with a label in the model first, so that the chart reads a value with its status and its evidence. |
| **The edit document as a file** | A button that saves the edit document of the settings of the notebook, for `napkin run --edits`. | A place to save it outside the checkout, so that the button adds no files to the repository. |
