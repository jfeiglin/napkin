"""Baseline: what the current hybrid engine costs at network scale (no found values)."""
import sys, time, cProfile, pstats, io
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from napkin.engine import timeline
from napkin.model import hybrid

HEAD = '''scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 7 days
    scope "Nothing: the model is synthetic."

'''
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'

BODY = '''Place:  @shape
    "A place."
    input need: fraction = 1 in 0 to 100  @shape
    var open = true  @shape

Route:  @shape
    "A route."
    let dest: Place
    input capacity: fraction = 5 in 0 to 100  @shape
    input fail_at: h = 1000 h in 0 h to 10000 h  @shape
    var up = true  @shape
    var lost: fraction = 0 size 1  @shape
    input loss: fraction/h = 0.001 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    flow lose: -> lost at loss while not up
    event fail once when t >= fail_at:  @shape
        "The route fails."
        up = false

places: Place from "places.csv"
routes: Route from "routes.csv"

output down: fraction = sum(Route.lost)  @shape
    "Lost"
'''

def write(folder, places, routes, failing, same_time=True, seed=0):
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    (folder / 'model.scn').write_text(HEAD + BODY + RECORD)
    (folder / 'places.csv').write_text('need: fraction @shape\n' + '\n'.join(f'{x:.3f}' for x in rng.uniform(0.5, 2, places)) + '\n')
    to = rng.integers(1, places + 1, routes)
    fail = np.full(routes, 1000.0)
    chosen = rng.choice(routes, failing, replace=False)
    fail[chosen] = 24.0 if same_time else rng.uniform(1, 160, failing)
    rows = ['dest,capacity: fraction @shape,fail_at: h @shape']
    rows += [f'places.{a},{c:.3f},{f:.6f}' for a, c, f in zip(to, rng.uniform(1, 10, routes), fail)]
    (folder / 'routes.csv').write_text('\n'.join(rows) + '\n')
    return folder / 'model.scn'

if __name__ == '__main__':
    places, routes, failing = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    same = sys.argv[4] == 'same'
    path = write(Path(f'm_{places}_{routes}_{failing}_{sys.argv[4]}'), places, routes, failing, same)
    t = time.perf_counter(); core = hybrid.compile(path); t_compile = time.perf_counter() - t
    print('families', [(f.host, len(f)) for f in core.families])
    t = time.perf_counter(); plan = timeline.Plan.of(core); t_plan = time.perf_counter() - t
    pr = cProfile.Profile() if len(sys.argv) > 5 else None
    t = time.perf_counter()
    if pr: pr.enable()
    result = timeline.run(plan)
    if pr: pr.disable()
    t_run = time.perf_counter() - t
    print(f'compile {t_compile:.2f}s plan {t_plan:.2f}s run {t_run:.2f}s', result.counts, result.outputs)
    if pr:
        s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(35); print(s.getvalue()[:6000])
