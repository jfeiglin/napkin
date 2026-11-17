# The live view of water_controls_wipe

This folder holds the package's own view: a page that shows the attack on the water systems of each place
and lets you play each run. The page has two views:

- **The map of the places.** It shows each of the 16 places, and the attack line to the chosen place.
- **The water systems of the place.** For each system it shows what its plants can make, what it buys and
  its stored water. It also shows the sales between the systems, the water that each system delivers to its
  homes, its boil-water advisories and the state of its hospitals.

Under the views, a chart shows the people without their normal water service and the people under a
boil-water advisory. The panel holds the place, the run, the time since the attack and the moments of the
run.

The engine calculates each place and run when the page first asks for it. A run that the run store holds
(`.cache/runs`) comes back in less than a second. A new run of the largest place, Washington, DC, takes
about 5 s.

## Run it

You need Node.js 20 or later, with npm. Run these commands from the root of the checkout, with the
repository's environment (CONTRIBUTING.md):

```sh
python -B -m scenarios.water_controls_wipe.ui setup    # install the page's packages into ui/web/node_modules
python -B -m scenarios.water_controls_wipe.ui serve    # build the page if it changed, then serve it
```

Then open http://localhost:8765/.

- `serve --port N` serves on another port, and `--jobs N` sets the number of worker processes (default 4).
- `dev` serves the engine and the page together, and the page reloads when you change a file of `web/src`.
- `test` runs the page's own tests.

The server answers only on this computer. It listens on 127.0.0.1, and it answers only requests that
name `localhost` or `127.0.0.1`. To let it answer another name of this computer, such as a preview proxy,
add `--host NAME`.

## What is here

| File | What it holds |
| --- | --- |
| `view.py` | What the page shows of a place and of one of its runs, from the model and the engine's run |
| `server.py` | The local server: it runs the engine in worker processes and serves the page |
| `__main__.py` | The helper: `setup`, `serve`, `dev` and `test` |
| `web/` | The page: React and TypeScript, built with Vite. `web/package.json` lists its packages |
| `web/src/places.json` | The point on the map of each place, as longitude and latitude |

The page's packages go only into `web/node_modules`. The repository's Python environment and the
`napkin` wheel get no new package.

## Where the data comes from

- **Every number** comes from the compiled model of the place or from the engine's run of it.
- **The parts of a place** are found from the templates that make them and from the links between them:
  - the systems (`Utility`);
  - the sales between them (`Tie`);
  - their homes (`Households`);
  - their hospitals (`Hospitals`).

  So the view keeps no list of systems.
- **The words** come from the model, from the package's pages (`tools/publish/pages.py`) and from each
  place's README.
- **The hospitals** come from the evidence. The view follows the record of each `Hospitals` count to its
  claim, and then to the join claims that place each hospital in the system's service area. Each hospital
  links to its page on Medicare Care Compare, by its CMS ID.
- **The map** is the US outline of the `us-atlas` package (`states-albers-10m`), which is made from the US
  Census Bureau's cartographic boundaries. `us-atlas` is under the ISC license. Each place's point is
  projected with d3's `geoAlbersUsa`, in the same frame as the outline. The points are for the view only,
  and no run reads them.
- **The font** is IBM Plex Sans, from `@fontsource/ibm-plex-sans`, under the SIL Open Font License 1.1.

## Tests

- **`../tests/test_ui_view.py`** checks that the view shows what each run holds. It compares:
  - the people counts with the engine's report;
  - the flows with each system's limits;
  - the hospitals with the model's counts.
- **`../tests/test_ui_server.py`** checks that the server gives the same frames as the view, and refuses
  what it does not serve.

Run these tests by path:

```sh
python -B -m tools.check --tests scenarios/water_controls_wipe/tests/test_ui_view.py \
    --tests scenarios/water_controls_wipe/tests/test_ui_server.py
```

`python -B -m scenarios.water_controls_wipe.ui test` runs the page's own tests. They check:

- how the page reads a series at a time;
- the scale and the ticks of the chart;
- the lanes of the sales;
- the markers on the map.
