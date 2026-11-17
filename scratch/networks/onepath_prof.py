import sys, time, cProfile, pstats, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import napkin
from napkin.model import hybrid
from napkin.engine import evaluate_study, sample_result, timeline
from napkin.engine.timeline import reports, Plan
path = str(ROOT / 'scenarios/cyber_learning_loop/model.scn')
core = hybrid.compile(path); model = core.model; run = list(model.runs)[0]
t = time.perf_counter(); plan = Plan.of(core, run); t_plan = time.perf_counter() - t
t = time.perf_counter(); result = timeline.run(plan, record=True); t_run = time.perf_counter() - t
t = time.perf_counter(); made = reports.report_of(result, None, ()); t_rep = time.perf_counter() - t
print(f'table path, one run: plan {t_plan:.2f}s  run {t_run:.2f}s  report {t_rep:.2f}s')
flat = napkin.load_scenario(path)
t = time.perf_counter(); study = evaluate_study(flat, runs=[run]); t_s = time.perf_counter() - t
t = time.perf_counter(); rep = sample_result(study); t_r = time.perf_counter() - t
print(f'flat path, one run:  resolve+run {t_s:.2f}s  report {t_r:.2f}s')
pr = cProfile.Profile(); pr.enable(); reports.report_of(result, None, ()); pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(14)
print('\n'.join(line[:150] for line in s.getvalue().splitlines()[6:26]))
