# A4a findings: the engine at scale

> DRAFT at the checkpoint of 18:15. Parts marked TODO are not final. `STATE.md` has the state of
> the work and every number measured so far, with its command.

## 1. Summary

1. A real transfer across rows is shown. One route row moves 2 L/h and one lot of 1.5 L from the
   stock of its origin row to the stock of its destination row. The right two stocks change
   (10 to 2.5 L and 30 to 37.5 L), also after the place rows are reordered.
2. The present engine runs it only with each row written out (one component). The table path
   cannot run it with a small honest change: with two refusals removed it runs and moves nothing.
3. The proposed layout (pools of rows, links by id, one sparse network) runs 30,000 places and
   35,000 routes: 0.12 s to build, 1.4 s for 50,302 moments, the total conserved.
4. One component of the present general tier is acceptable up to about 150 stores. TODO final.
5. A request that moves continuously costs seconds in a small set and is refused in a large one.
   TODO final numbers.
6. A record of histories (pieces of three numbers) for every store and flow of the 30,000-row run
   is 6 MB and adds 0.3 s. Today's trajectory would need about 80 GB at that size.

## 2. What was done

TODO: the list of scripts and how to run each. For now see the head of each script and `STATE.md`.

- `01_id_column.patch`, `02_table_path_probe.patch`: the two changes to a copy of the package.
- `layout.py`, `lines.py`, `reference.py`, `record.py`, `model.py`: the prototype.
- `t1_transfer.py`, `t2_sets.py`, `t3_record.py`: one script for each task.
- `measure.py`: makes every table again.

## 3. Results

TODO: the tables of `results.md`, after one whole run of `measure.py`. The numbers so far are in
`STATE.md`.

## 4. Rulings

TODO: each in its final form. The rules that the measurements support so far:

- **Layout.** A pool for each template; a link is a column of row numbers found from ids; every
  store has one place in one vector; a flow names its two ends by those places; the incidence is
  sparse, with its reverse by store.
- **Order of rows.** Rows are kept in the order of their ids, so a reordered file gives the same
  bits.
- **Connected sets.** A set is of stores and flows. A flow joins the store at an end that can hold
  it back; a request joins the stores that it reads when they move; a solver joins the flows that
  it sets. A tally does not join the flow into it.
- **Three ways.** A store alone: arrays. A set of at most about 150 stores: one component. A
  larger set: lines, with rates from the sparse solver at each moment, and refused when a rate
  reads a value that moves.
- **Record.** Histories as pieces `(t, y, rate)` for each stored value, and the trace. Every
  stored value is recorded while the record stays under a budget of pieces; above it, what the
  request names.
- **Reuse.** The key covers the program, the configuration, the mode, the seed, the choices, the
  numerical settings, the code and the machine. It covers no label and no request. A stored run
  says what it holds; it serves a request that it holds.

## 5. Not covered

TODO. Known now: upper bounds in `lines.py`; the real sharing rules (A3); occurrences (A4b); the
record of numeric segments; a solver's unknowns in the record.
