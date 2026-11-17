"""What two links into one class cost today, and what a list in a line of a template does."""
import sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from napkin.engine import timeline
from napkin.model import hybrid
from napkin.model.ir import ModelError
from baseline import HEAD, RECORD

BODY = '''Place:  @shape
    "A place."
    input level: fraction = 1 in 0 to 100  @shape

Route:  @shape
    "A route."
    let a: Place
    let b: Place
    input capacity: fraction = 5 in 0 to 100  @shape
    let drop: fraction = a.level - b.level  @shape
    var up = true  @shape
    event fail once when up and drop >= capacity:  @shape
        "The route fails."
        up = false

places: Place from "places.csv"
routes: Route from "routes.csv"

output down: fraction = sum(Route.drop)  @shape
    "Sum of the drops"
    signed
'''
LISTED = BODY.replace('    input level: fraction = 1 in 0 to 100  @shape\n', '    input level: fraction = 1 in 0 to 100  @shape\n    let total: fraction = sum(Route.capacity)  @shape\n')

def write(folder, body, places, routes, seed=0):
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    (folder / 'model.scn').write_text(HEAD + body + RECORD)
    (folder / 'places.csv').write_text('level: fraction @shape\n' + '\n'.join(f'{x:.3f}' for x in rng.uniform(0.5, 2, places)) + '\n')
    a = rng.integers(1, places + 1, routes); b = rng.integers(1, places + 1, routes)
    rows = ['a,b,capacity: fraction @shape'] + [f'places.{i},places.{j},{c:.3f}' for i, j, c in zip(a, b, rng.uniform(1, 10, routes))]
    (folder / 'routes.csv').write_text('\n'.join(rows) + '\n')
    return folder / 'model.scn'

for places, routes in ((100, 200), (200, 400), (400, 800)):
    path = write(Path(f'two_{routes}'), BODY, places, routes)
    t = time.perf_counter()
    try:
        core = hybrid.compile(path)
        t1 = time.perf_counter() - t
        t = time.perf_counter(); plan = timeline.Plan.of(core); result = timeline.run(plan)
        print(f'{routes} routes with two links: {len(core.families)} families, compile {t1:.2f}s, plan+run {time.perf_counter() - t:.2f}s, steps {result.counts["steps"]}')
    except Exception as exc:
        print(f'{routes} routes: {type(exc).__name__}: {str(exc)[:300]} ({time.perf_counter() - t:.2f}s)')
try:
    hybrid.compile(write(Path('listed'), LISTED, 10, 20))
except ModelError as exc:
    print('a list in a line of a template:', str(exc)[:300])
