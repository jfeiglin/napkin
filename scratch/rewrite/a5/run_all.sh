#!/bin/sh
# Makes the results of the migration scripts again (stage M, PLAN.md "Changes after G0", item 17):
# the mechanical translation of the two test targets with their compile, the check of the hand
# translation of the piano tuners (it must PASS), the check of each wrong translation (each must
# FAIL in its own group), and the check of the migration table against the census.
# Run from anywhere: sh /home/user/napkin/scratch/rewrite/a5/run_all.sh
cd "$(dirname "$0")" || exit 2
PY=/home/user/napkin/.venv/bin/python
OLD=/home/user/napkin-base
status=0
echo "--- translate (the old compiler reads; the compiler of now compiles)"
PYTHONPATH=$OLD $PY translate.py --compile examples/reservoir scenarios/water_controls_wipe/model.scn \
    scenarios/water_controls_wipe/water.scn scenarios/water_controls_wipe/variants/jamestown/model.scn
echo "--- the hand translation of the piano tuners: the check must PASS"
$PY check.py --quiet "$OLD/examples/piano_tuners/model.scn" /home/user/napkin/examples/piano_tuners/model.scn || status=1
for fault in number text kind cumulative; do
    echo "--- a wrong translation ($fault): the check must FAIL in [$fault]"
    if $PY check.py --quiet "$OLD/examples/piano_tuners/model.scn" "translated/wrong/piano_tuners_$fault/model.scn" \
        | grep -q "FAILED: 1 $fault\$"; then
        echo "refused, as it must be"
    else
        echo "NOT refused as it must be"; status=1
    fi
done
echo "--- the mechanical translation of the reservoir (its empty case WAIT is left for a person)"
$PY check.py "$OLD/examples/reservoir/model.scn" translated/now/examples/reservoir/model.scn
$PY table_check.py || status=1
echo "run_all: $([ $status = 0 ] && echo OK || echo PROBLEMS)"
exit $status
