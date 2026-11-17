"""The trial of two links into one table. It reads a copy of the checkout with two_links_trial.patch
applied: NAPKIN_TRIAL names that copy. Arguments: the number of places and of routes."""
import os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ['NAPKIN_TRIAL'])
import numpy as np
from napkin.model import hybrid
from napkin.engine import timeline
from twolinks_model import write, BODY
places, routes = int(sys.argv[1]), int(sys.argv[2])
path = write(Path(f'sp_{routes}'), BODY, places, routes)
t = time.perf_counter(); core = hybrid.compile(path); t_c = time.perf_counter() - t
t = time.perf_counter(); plan = timeline.Plan.of(core); result = timeline.run(plan); t_r = time.perf_counter() - t
print(f'{routes} routes, two links into one table: families {[(f.host, len(f)) for f in core.families]}, compile {t_c:.2f}s, plan+run {t_r:.2f}s')
print('   steps', result.counts['steps'], 'output', result.outputs)
# the definition, by hand, from the tables
level = np.loadtxt(path.parent / 'places.csv', skiprows=1)
rows = [line.split(',') for line in (path.parent / 'routes.csv').read_text().splitlines()[1:]]
a = np.array([int(r[0].split('.')[1]) - 1 for r in rows]); b = np.array([int(r[1].split('.')[1]) - 1 for r in rows]); cap = np.array([float(r[2]) for r in rows])
drop = level[a] - level[b]
print('   by hand: sum of the drops', drop.sum(), '; routes that fail', int((drop >= cap).sum()))
if routes <= 100:
    from napkin.model.model import build_model
    from napkin.engine.runtime import simulate
    from napkin.model.ir import thaw
    model = build_model(path); resolved = model.resolve(next(iter(model.runs)))
    trajectory = simulate(resolved, thaw(model.library))
    flat = sorted((e['t'], e['rule']) for e in trajectory.trace if e['outcome'])
    mine = sorted((t_, r) for t_, r, o in result.trace)
    print('   the flat model of the same file: same events', flat == mine, len(flat))
