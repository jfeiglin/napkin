#!/bin/sh
# Makes every result of A5 again: the census, the mechanical translation, the check of each hand
# translation (each must PASS), the bad case (it must FAIL), and the check of the migration table.
# Run from anywhere: sh /home/user/napkin/scratch/rewrite/a5/run_all.sh
cd "$(dirname "$0")" || exit 2
PY=/home/user/napkin/.venv/bin/python
export PYTHONPATH=/home/user/napkin-base
OLD=/home/user/napkin-base
status=0
$PY census.py || status=1
$PY translate.py || status=1
for pair in \
    examples/piano_tuners/model.scn \
    examples/reservoir/model.scn \
    scenarios/water_controls_wipe/water.scn \
    scenarios/water_controls_wipe/variants/jamestown/model.scn \
    scenarios/heat_wave_blackout/model.scn \
    scenarios/cyber_learning_loop/model.scn
do
    $PY check.py --quiet "$OLD/$pair" "translated/$pair" || status=1
done
echo "--- the bad case: the check must FAIL"
if $PY check.py "$OLD/scenarios/water_controls_wipe/water.scn" translated/bad/water.scn | grep FAIL; then
    echo "bad case: refused, as it must be"
else
    echo "bad case: NOT refused"; status=1
fi
$PY table_check.py || status=1
echo "run_all: $([ $status = 0 ] && echo OK || echo PROBLEMS)"
exit $status
