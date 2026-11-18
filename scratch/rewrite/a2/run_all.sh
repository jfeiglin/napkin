#!/bin/sh
# Runs every case and every ruling of prototype A2, three times, and prints the load.
# Usage: sh scratch/rewrite/a2/run_all.sh   (from /home/user/napkin)
cd "$(dirname "$0")/../../.." || exit 1
uptime
for i in 1 2 3; do
  .venv/bin/python -m pytest scratch/rewrite/a2 -q -p no:cacheprovider --rootdir scratch/rewrite/a2 -c /dev/null | tail -1
done
