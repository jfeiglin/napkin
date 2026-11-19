#!/bin/sh
# Makes the results of the migration scripts again (stage M, PLAN.md "Changes after G0", item 17):
# the mechanical translation of the two test targets with their compile, the check of the hand
# translation of the piano tuners (it must PASS, its runs included), the check of each wrong
# translation (each must FAIL in its own group, and in the run step too where the fault moves a
# result), the wrong copy of the run step again with its change listed (it must PASS), the check of
# the reservoir's mechanical translation (reported), and the check of the migration table.
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
# Each wrong copy, with the summary that its check must end with: a changed number and a value that
# reads the wrong store move the yearly result as well, so the run step refuses them too.
for case in "number:1 number, 1 run" "text:1 text" "kind:1 kind" "cumulative:1 cumulative, 2 run" "run:1 run"; do
    fault=${case%%:*}
    summary=${case#*:}
    echo "--- a wrong translation ($fault): the check must FAIL with: $summary"
    if $PY check.py --quiet "$OLD/examples/piano_tuners/model.scn" "translated/wrong/piano_tuners_$fault/model.scn" \
        | grep -q "FAILED: $summary\$"; then
        echo "refused, as it must be"
    else
        echo "NOT refused as it must be"; status=1
    fi
done
echo "--- the wrong copy (run) with its change listed in its own changed.md: the check must PASS"
$PY check.py --quiet "$OLD/examples/piano_tuners/model.scn" translated/wrong/piano_tuners_run/model.scn \
    --changed translated/wrong/piano_tuners_run/changed.md || status=1
echo "--- the mechanical translation of the reservoir (its empty case WAIT is left for a person; reported)"
$PY check.py "$OLD/examples/reservoir/model.scn" translated/now/examples/reservoir/model.scn
$PY table_check.py || status=1
echo "run_all: $([ $status = 0 ] && echo OK || echo PROBLEMS)"
exit $status
