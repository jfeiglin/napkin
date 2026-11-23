# Recover the interrupted Linux deep run

The first Linux deep session ended before pytest finalized its JUnit document. Keep the original verbose log and use each recorded terminal outcome to exclude completed nodes from the remainder. Keep each remainder log and JUnit separate. A completed test ID establishes its pytest outcome. For the original nine plant transformations a passing test may also have reported an allowed near-tie. Those properties count toward the truncation gate.

At the tested revision `93ebabf349d051f6fa71f1615732f5326b61ec4e`, all 35 other transformations return before the only near-tie property writer. Their logged passes establish zero truncations. For completed, property-capable nodes, first use any surviving Linux report of the same seed and transformation from the same tested source and runtime. Put any remaining full node IDs, one per line, in a separate file. Preserve the original outcome of each test.

From the same Linux checkout and virtual environment used for deep, read the [guard probe](guard_properties.py) from this evidence commit into a separate directory. Supply the original verbose Linux log and the list of IDs whose properties are missing. Reuse the original thread limits.

```bash
.venv/bin/python -B "$recovery/guard_properties.py" \
  --ids "$missing_ids" --pass-log "$original_log" --output "$new_jsonl"
```

Each result contains the original log digest, tested revision and platform, the actual branch decisions observed in the original program, reference and variant, and their derived near-tie properties. The output labels these observations as recomputed. The probe preserves the solver trajectory, checkpoint behavior and both roundoff displacements while reading only the guard. Each output row is flushed and synced to disk. An ID without an unambiguous original pass is refused. [Synthetic projection controls](guard-verified.json).

For a new remainder invocation the [pytest report plugin](audit_report_ledger.py) can journal each phase as the xdist controller receives it. Set `PYTHONPATH` to include the recovery directory, load `-p audit_report_ledger` and pass a new output path with `--audit-report-ledger="$results/deep-remainder.sqlite"`. Keep the same selection and JUnit options. Preserve the SQLite WAL alongside the database after an interruption, or export a consistent SQLite backup. [Synthetic interruption and outcome controls](validation.json).
