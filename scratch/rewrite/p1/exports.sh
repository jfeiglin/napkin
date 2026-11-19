#!/bin/bash
# The exports at 30,000 places, one at a time, each stopped at 15 minutes (P1's rule).
cd /home/user/napkin
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=/home/user/napkin NAPKIN_STORE=off
PY=/home/user/venvs/p1/bin/python
for s in ${SCENARIOS:-normal shortage damaged global}; do
  echo "start $s $(date +%T) load $(cut -d' ' -f1 /proc/loadavg)"
  timeout 900 $PY scratch/rewrite/p1/lab.py export 1.0 $s 2>&1 | grep -v "^Running HiGHS\|^Includes third"
  echo "exit $s ${PIPESTATUS[0]} $(date +%T)"
done
echo "start engine 30000 $(date +%T)"
timeout 900 $PY scratch/rewrite/p1/lab.py engine 30000 2>&1 | grep -v "^Running HiGHS\|^Includes third"
timeout 900 $PY scratch/rewrite/p1/lab.py export-engine 30000 2>&1 | grep -v "^Running HiGHS\|^Includes third"
echo "exit engine ${PIPESTATUS[0]} $(date +%T)"
