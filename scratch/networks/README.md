# Prototypes of the engine features for networks

This folder holds the scripts behind "What was measured" in
[the scope of the features](../../docs/scoping/networks-and-found-values.md). They are prototypes:

- no test covers them, and the check does not lint them;
- no part of the package, of the tools or of the tests reads them, and none may
  ([CONTRIBUTING.md](../../CONTRIBUTING.md#author-each-part-in-its-own-file));
- they hold no design that is agreed. The page holds it.

**Delete this folder before the branch merges into main.** Merge with a squash, so that the history
of main never holds it.

## Run a script

Run each script from this folder, with the requirements of the checkout installed. `SHARE` is a
share of the scale of the page: `1.0` is 30,000 places, 35,000 routes and 15,000 sources. A script
writes its models and its arrays into this folder, and `.gitignore` leaves them out.

| Script | What it measures |
| --- | --- |
| `baseline.py PLACES ROUTES FAILING same` | The engine of today with two tables and no found value: the compile and a run |
| `twolinks.py` | Routes with two ends in one table, today: the refusal, and the refusal of a list in a line of a template |
| `two_links_trial.py PLACES ROUTES` | The trial of a stand-in for each link (below) |
| `e1_kkt.py SHARE` | One sparse factorization and one solve with it: the normal equations against the whole system |
| `e3_lp.py SHARE` | The linear program of the goal in the bundled HiGHS, cold and from the last basis; then its quadratic program, which takes 73 s at `0.1`: do not run it at `1.0` |
| `e6_full.py physics SHARE`, `e6_full.py transport SHARE` | The goal and then the nearest step, each problem cold: a normal day, high demand, routes down |
| `e7_warm.py physics SHARE`, `e7_warm.py transport SHARE` | Hour after hour with one kept solver, and one route after another that fails |
| `e8_cascade.py SHARE 1.6` | A cascade, with a solve when the steps of a moment are done |
| `onepath_all.py > onepath_all.out` | Each run of each model through the flat side and through the table side: about 4 minutes on 4 processors |
| `onepath_prof.py` | Where the report of the table side takes its time on the largest model |
| `t_search.py` | The line search of the nearest step against a search by hand |

`net.py` makes the synthetic network. `hs.py` wraps the HiGHS solver that SciPy bundles, with one
solver that keeps its program. `nearest.py` is the nearest step. `twolinks_model.py` has the model
with two links.

## The trial of two links into one table

`two_links_trial.patch` changes four files of the package. Apply it to a copy of the checkout, never
to the checkout itself, and name the copy:

```bash
mkdir /tmp/trial && git -C ../.. archive HEAD napkin | tar -x -C /tmp/trial
(cd /tmp/trial && patch -p1 < "$OLDPWD/two_links_trial.patch")
NAPKIN_TRIAL=/tmp/trial python two_links_trial.py 30000 35000
```

## What is known to be wrong

- The rule to stop of `nearest.py` is too strict for values with a wide range: a problem that has
  its answer can go on to its limit of steps. `e8_cascade.py` shows it.
- Each problem of `e6_full.py` and `e8_cascade.py` starts cold. `e7_warm.py` keeps the solver.
- The patch makes the first of the three cases of the page only: two links into one table.
