"""Every run of every model of the checkout through the path of table models, against the study of
the flat path: the final value of each outcome, and the steps of the trace."""
import sys, time, glob, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

def one(path):
    import napkin
    from napkin.model import hybrid
    from napkin.engine import evaluate_study, sample_result
    from napkin.engine.timeline import reports
    name = str(Path(path).parent.relative_to(root))
    out = dict(model=name, runs=0, same=0, refused=0, why=set(), worst=0.0, outcomes=0, steps_differ=0, starts=0)
    try:
        model = napkin.load_scenario(path)
        core = hybrid.compile(path)
    except Exception as exc:
        out['why'] = [f'load: {type(exc).__name__}: {str(exc)[:100]}']; return out
    for run in model.runs:
        out['runs'] += 1
        out['starts'] += bool(model.runs[run]['starts'])
        try:
            flat = sample_result(evaluate_study(model, runs=[run]))
            table = reports.study_of(core, [run])
        except Exception as exc:
            out['refused'] += 1; out['why'].add(f'{type(exc).__name__}: {str(exc)[:100]}'); continue
        if not flat['admissible']:
            continue
        if not table['admissible']:
            out['refused'] += 1; out['why'].add(table['diagnostics'][0].get('message', '')[:100]); continue
        a, b = flat['runs'][run], table['runs'][run]
        worst = 0.0
        for key, value in a['reporting_points']['final']['values'].items():
            other = b['reporting_points']['final']['values'].get(key)
            if value is None or other is None:
                worst = max(worst, 0.0 if value is None and other is None else 1.0); continue
            out['outcomes'] += 1
            worst = max(worst, abs(value - other) / max(1e-300, abs(value), abs(other)))
        out['worst'] = max(out['worst'], worst)
        steps = lambda r: [(e['rule'], e['outcome']) for e in r['trace']]
        out['steps_differ'] += steps(a) != steps(b)
        out['same'] += worst <= 1e-9
    out['why'] = sorted(out['why'])
    return out

if __name__ == '__main__':
    paths = sorted(glob.glob(str(root / 'examples/*/model.scn'))) + sorted(glob.glob(str(root / 'scenarios/*/model.scn')))
    paths += sorted(glob.glob(str(root / 'scenarios/*/variants/*/model.scn')))
    t = time.perf_counter()
    with ProcessPoolExecutor(4) as pool:
        for found in pool.map(one, paths):
            print(json.dumps(found), flush=True)
    print('seconds', round(time.perf_counter() - t))
