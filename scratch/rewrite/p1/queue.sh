#!/bin/bash
# Run the commands of a queue file one at a time (one 30,000-place case at a time), each stopped at
# 15 minutes; lines are read as they come, so the file can grow while it runs. Waits for the exports.
cd /home/user/napkin
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=/home/user/napkin:/home/user/napkin/scratch/rewrite/p1 NAPKIN_STORE=off
QUEUE=$1
LOG=$2
while pgrep -f "p1/exports.sh" > /dev/null; do sleep 15; done
done_lines=0
while true; do
  total=$(wc -l < "$QUEUE")
  if [ "$done_lines" -ge "$total" ]; then
    grep -q "^#end" "$QUEUE" && break
    sleep 20; continue
  fi
  done_lines=$((done_lines + 1))
  line=$(sed -n "${done_lines}p" "$QUEUE")
  case "$line" in ''|'#'*) continue;; esac
  echo "=== $(date +%T) load $(cut -d' ' -f1 /proc/loadavg): $line" >> "$LOG"
  start=$(date +%s)
  timeout 900 /home/user/venvs/p1/bin/python -W ignore $line 2>&1 | grep -v "^Running HiGHS\|^Includes third" >> "$LOG"
  status=${PIPESTATUS[0]}
  echo "=== exit $status after $(( $(date +%s) - start )) s" >> "$LOG"
  if [ "$status" = "124" ]; then echo "DID NOT FINISH IN 15 MIN: $line" >> "$LOG"; fi
done
