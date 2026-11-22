# Final verification

Run the following Bash commands once on macOS and once on Linux, from the same audited commit with its locked virtual environment. The output directory records the host, revision, per-test outcomes and a separate failed-test cache for each tier.

```bash
set -o pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
audited_sha=$(git rev-parse HEAD)
results="../audit-owner-runs/final-$audited_sha-$(uname -s)"
args=scratch/rewrite/audit/owner-fixes/final/pytest.args
python=.venv/bin/python
workers=${JOBS:-4}
mkdir -p "$results"
git rev-parse HEAD | tee "$results/commit"
"$python" -VV | tee "$results/python"
uname -a | tee "$results/host"
```

## Regular and deep

The same argument file covers the generic engine and tool tests, both heat-resilience and IV-fluid recovery packages, the standalone defensive-response model, and UI metadata that can be read without running the regional models. Catalogue-wide formatting, source provenance, role names and startup-only scalar tests remain selected. The exclusions cover offensive workflow and targeted response simulations, associated diagrams, and admission of their comparison-study edits. Each tier runs once. Verbose logs preserve completed node IDs even if the session is interrupted. The regular rotation runs one transformation per seed across 300 seeds. Deep runs every transformation on each of 2,000 seeds.

```bash
tier() {
  local name="$1" marker="$2" attempt="$3"
  shift 3
  "$python" -B -m pytest -v -n "$workers" --dist worksteal -m "$marker" \
    -o "cache_dir=$results/$name-cache" -o junit_family=xunit1 --junitxml="$results/$name-$attempt.xml" \
    "$@" "@$args" 2>&1 | tee "$results/$name-$attempt.log"
}
tier regular 'not deep' first
tier deep deep first
```

The corpus verifier checks the seed, transformation and near-tie properties in each first-pass report. The regular comparison uses the recorded elapsed time and worker count. The documented 180-second budget is for a complete four-worker regular suite. These commands report the scoped measurement separately.

```bash
corpus=scratch/rewrite/audit/port_corpus_results.py
"$python" -B "$corpus" regular "$results/regular-first.xml" 2>&1 | tee "$results/corpus-regular.log"
"$python" -B "$corpus" deep "$results/deep-first.xml" 2>&1 | tee "$results/corpus-deep.log"
"$python" - "$results/regular-first.xml" "$workers" <<'PYTIME' | tee "$results/regular-time.log"
import sys
from xml.etree import ElementTree
suite, = ElementTree.parse(sys.argv[1]).iter('testsuite')
print(f"Scoped regular elapsed {suite.attrib['time']} s with {sys.argv[2]} workers. Full regular reference budget 180 s with four workers.")
PYTIME
```

For a completed tier with recorded failures, rerun the corresponding line after the fix. Each retry preserves its own log and XML. The empty-cache setting prevents an accidental full rerun.

```bash
tier regular 'not deep' retry1 --lf --lfnf=none
tier deep deep retry1 --lf --lfnf=none
```

## Publication

The first command runs the declared studies behind the selected catalogue pages. The second checks the standalone defensive readings. The third compares the catalogue's static source dossiers and manifest. Each comparison has a separate exit status and log. On a mismatch rerun the affected check and narrow the scenario and format to the output named in the log.

```bash
"$python" -B -m tools.publish --check --jobs 4 --only briefs --only readings \
  --scenario heat_wave_blackout --scenario iv_fluid_shortage 2>&1 | tee "$results/catalogue-pages.log"
"$python" -B -m tools.publish --check --jobs 4 \
  --model scenarios/cyber_learning_loop/defensive_response 2>&1 | tee "$results/defensive-readings.log"
"$python" -B -m tools.publish --check --jobs 4 --only dossier --only manifest \
  2>&1 | tee "$results/sources.log"
```

## Mac timing table

Run on an otherwise idle Mac after the correctness runs. The baseline and historical worker below are the existing pinned sibling worktrees. Each tank row uses 12 generated tanks for 12 h. Events exercise clock-triggered shipping at 1,200 synthetic places over 48 h, divided into 12 phases. The declared solver uses a synthetic network of 3,000 places, 3,500 routes and 1,500 sources. All four workloads are generated locally from repository benchmark scripts.

```bash
baseline=../engine-finalized-baseline
worker_tree=../engine-finalized-held-protocol
bench=scratch/rewrite/audit/port_benchmark.py
speed_dir="$results/speed"
test "$(git -C "$baseline" rev-parse HEAD)" = 6202824d6d567c34ac46da7b018e66a9c28588b3 &&
test "$(git -C "$worker_tree" rev-parse HEAD)" = 0f0fcb2a933fdf71a0458a101a4377e1ccb0f44a &&
test "$(git rev-parse HEAD)" = "$audited_sha" &&
"$python" -B "$bench" campaign --phase final --rows sparse-tanks component-tanks events declared \
  --revision "B=$baseline" --revision "F=." --worker-script "$worker_tree/$bench" \
  --out "$speed_dir" 2>&1 | tee "$results/speed-campaign.log" &&
"$python" -B "$bench" summary --phase final --rows sparse-tanks component-tanks events declared \
  --out "$speed_dir" 2>&1 | tee "$results/speed-summary.log"
```

The driver alternates B/F, F/B, B/F. Each row's median paired candidate/baseline run-and-record ratio must be at most 1.05. The summary also checks the declared solver's build-plus-plan-plus-run ratio against that limit. The speed directory keeps the three pairs, the uncounted tank calibrations and each revision's checksums. Repeating a campaign after an interruption reuses completed samples with matching identities.
