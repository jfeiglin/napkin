# The tables of A4a

Made by `measure.py`. Times are in seconds unless a column says otherwise.

## T1.1 The tiny transfer: the stock of each place (L)

| rows of places.csv | t (h) | expected depot | expected yard | expected clinic | present engine depot | present engine yard | present engine clinic | layout depot | layout yard | layout clinic | same |
| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| the order of the file | 0 | 10 | 20 | 30 | 10 | 20 | 30 | 10 | 20 | 30 | yes |
| the order of the file | 1 | 6.5 | 20 | 33.5 | 6.5 | 20 | 33.5 | 6.5 | 20 | 33.5 | yes |
| the order of the file | 3 | 2.5 | 20 | 37.5 | 2.5 | 20 | 37.5 | 2.5 | 20 | 37.5 | yes |
| the rows of the places in another order | 0 | 10 | 20 | 30 | 10 | 20 | 30 | 10 | 20 | 30 | yes |
| the rows of the places in another order | 1 | 6.5 | 20 | 33.5 | 6.5 | 20 | 33.5 | 6.5 | 20 | 33.5 | yes |
| the rows of the places in another order | 3 | 2.5 | 20 | 37.5 | 2.5 | 20 | 37.5 | 2.5 | 20 | 37.5 | yes |

## T1.2 The table path of the present engine: the stocks of three places at 3 h (L)

| case | expected | rows written out | table path, base commit | table path, with the probe patch |
| --- | --: | --: | --: | --: |
| one link, a flow out of the linked stock | [4.0, 20.0, 27.0] | [4.0, 20.0, 27.0] | refused: Outside: the flow routes_1.carried, which joins two spaces | refused: Outside: the flow routes_1.carried, which joins two spaces |
| one link, a move out of the linked stock | [8.5, 20.0, 27.5] | [8.5, 20.0, 27.5] | refused: Outside: places_1.stock: flows or transfers that connect quantities of two families | right: [8.5, 20.0, 27.5] |
| two links, a move between the linked stocks | [11.0, 17.5, 31.5] | [11.0, 17.5, 31.5] | refused: Outside: two links of routes_1 into one class | WRONG: [10.0, 20.0, 30.0] |
| two links, a flow between the linked stocks | [7.0, 17.0, 36.0] | [7.0, 17.0, 36.0] | refused: ModelError: Competing withdrawals require one explicit allocation policy | refused: ModelError: Competing withdrawals require one explicit allocation policy |

## T1.3 The layout against the present engine (one component)

| places | routes | rings | stocks that empty | moves | largest difference of a store (L) | present engine: build and run |
| --- | --: | --: | --: | --: | --: | --: |
| 30 | 35 | no | 27 | 35 | 1.1e-13 | 1.04 |
| 30 | 35 | no | 23 | 35 | 1.1e-13 | 0.181 |
| 100 | 116 | no | 79 | 116 | 1.7e-13 | 1.3 |
| 300 | 350 | no | 232 | 350 | 5.7e-13 | 14.1 |
| 30 | 35 | yes | 22 | 35 | 144 | 1.52 |

Load: [2.56, 1.34, 0.73].

## T1.4 The layout against its second implementation, with rings

| places | routes | stocks that empty | moves | largest difference of a store (L) |
| --- | --: | --: | --: | --: |
| 300 | 350 | 228 | 349 | 5.5e-11 |
| 3000 | 3500 | 2450 | 3498 | 4.3e-11 |

## T1.5 The cost at scale: the layout, run on lines

|  | 30,000 places |
| --- | --: |
| places | 30,000 |
| routes | 35,000 |
| stores | 60,000 |
| flows | 65,000 |
| the two tables (bytes) | 2,600,895 |
| build: read the tables, links, network | 0.121 |
| start of the run | 0.0749 |
| run to 48 h | 1.42 |
| moments | 50,302 |
| stocks that empty | 15,325 |
| moves | 34,977 |
| lines that start again | 143,921 |
| microseconds for each moment | 28.1 |
| total at 48 h less total at 0 h (L) | 0 |
| total at 0 h (L) | 3,305,805 |
| connected sets (plain rule) | 3,384 |
| stores of the largest set | 52,038 |
| peak memory of the process (MB) | 156 |
| runs (the best is given) | 3 |
| load | [2.62, 1.4, 0.76] |

## T1.6 Both tables with their rows in another order, 30,000 places and 35,000 routes

| order of the rows in memory | named values | values with other bits | largest difference (L) |
| --- | --: | --: | --: |
| rows in the order of their ids | 60000 | 0 | 0 |
| rows in the order of the file | 60000 | 2929 | 1.4e-13 |

## T2.1 The connected sets of the model with 30,000 places and 35,000 routes (a component has at most 150 stores)

| case | sets | stores of the largest | arrays: a store alone, or with one flow | one component of the continuous engine | lines, with rates from the sparse solver at each moment | refused: a large set with a rate that reads a value that moves | time of the cut |
| --- | --: | --: | --: | --: | --: | --: | --: |
| the requests read no value that moves | 33384 | 26019 | 32,948 sets, 32,948 stores | 435 sets, 1,033 stores | 1 sets, 26,019 stores | 0 sets, 0 stores | 0.0481 |
| the same, with the plain rule: a tally joins the flow into it | 3384 | 52038 | 0 sets, 0 stores | 3,383 sets, 7,962 stores | 1 sets, 52,038 stores | 0 sets, 0 stores | 0.0103 |
| the request of each route reads the stock of its origin | 33384 | 26019 | 32,948 sets, 32,948 stores | 435 sets, 1,033 stores | 0 sets, 0 stores | 1 sets, 26,019 stores | 0.0082 |
| the request of each route reads the stock of a third place | 30948 | 29045 | 30,943 sets, 30,943 stores | 4 sets, 12 stores | 0 sets, 0 stores | 1 sets, 29,045 stores | 0.0099 |
| one solver sets the rate of every route | 32949 | 27052 | 32,948 sets, 32,948 stores | 0 sets, 0 stores | 1 sets, 27,052 stores | 0 sets, 0 stores | 0.0067 |

## T2.2 One connected set as one component of the present general tier (horizon 300 h)

| request of a route | places | stores | flows | build | run | evaluations of the rates | ms for each | of it in the allocation | linear programs | peak memory (MB) | note |
| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| constant | 30 | 60 | 65 | 0.0712 | 0.0783 | 87 | 0.309 | 88% | 0 | 119 | 3 run(s), load 2.0 |
| constant | 100 | 200 | 216 | 0.333 | 0.863 | 243 | 1.31 | 94% | 0 | 157 | 1 run(s), load 1.98 |
| constant | 300 | 600 | 650 | 0.903 | 12.3 | 702 | 10.4 | 99% | 0 | 864 | 1 run(s), load 1.98 |
| constant, rings | 30 | 60 | 65 | 0.0768 | 0.604 | 78 | 7.59 | 99% | 21 | 120 | 3 run(s), load 2.0 |
| constant, rings | 100 | 200 | 216 | 0.338 | 0.995 | 258 | 1.45 | 94% | 0 | 160 | 1 run(s), load 1.83 |
| constant, rings | 300 | 600 | 650 |  |  |  |  |  |  |  | no result after 13 min (stopped by hand), t2_sets.py component OUT constant 300 rings 1 |

## T2.3 A large set whose requests read a stock: 30,000 places and 35,000 routes on sparse arrays

|  | value |
| --- | --: |
| stores | 60,000 |
| flows | 65,000 |
| nonzeros of the Jacobian | 94,998 |
| the same matrix, dense (MB) | 28,800 |
| one evaluation of the rates (ms) | 0.521 |
| the integration to 48 h | 36 |
| steps of the solver | 302 |
| evaluations of the rates | 2,784 |
| Jacobians | 35 |
| factorizations | 72 |
| stores at rest in the state of the two next rows | 15,311 |
| one sharing at that state, stand-in rule (ms) | 39.8 |
| one linear program at that state, bundled HiGHS | 0.233 |
| estimate: the run with the stand-in sharing at each evaluation | 111 |
| estimate: the run with one program at each evaluation (hours) | 0.18 |
| peak memory (MB) | 368 |
| load | [1.46, 3.49, 2.56] |

## T3.1 Two histories with the same readings

|  | read at 0, 6, 12 h | mean from 6 h to 10 h |
| --- | --: | --: |
| 8 L added at 7 h | [0.0, 0.0, 8.0] | 6 |
| 8 L added at 9 h | [0.0, 0.0, 8.0] | 2 |

## T3.2 The record with 30,000 rows

| what the run records | run to 48 h | added by the record | pieces | bytes as arrays | bytes packed | time to pack |
| --- | --: | --: | --: | --: | --: | --: |
| nothing | 1.54 |  |  |  |  |  |
| eight reductions (no max, no min) and five rows | 3.99 | 2.45 | 87538 | 1651120 | 1209778 | 0.0516 |
| ten reductions and five rows | 4.9 | 3.36 | 87569 | 1651864 | 1211058 | 0.0469 |
| every store and every flow | 1.64 | 0.0947 | 324857 | 6050512 | 2702960 | 0.177 |

30,000 places, 35,000 routes, 50,302 moments. Best of 1; load [5.42, 3.03, 1.75].

|  | value |
| --- | --: |
| recording changes the run | no |
| largest relative difference of a reduction kept in the run from the same made from every store | 3.6e-14 |
| pieces of each history kept in the run | {'held': 15327, 'used_total': 11763, 'critical_held': 4198, 'empty_places': 15326, 'low_places': 15953, 'any_critical_empty': 2, 'carried_now': 13169, 'unmet_use': 11763, 'fullest': 23, 'emptiest': 8} |
| passes over the rows for the greatest and the least | {'fullest': 29, 'emptiest': 414} |
| a report from the histories kept in the run: ten values at three times and one lag at three times | 0.0027 |
| from the record of everything: the ten reductions at three times | 0.0271 |
| from the record of everything: the whole history of two sums | 0.0232 |
| largest relative difference of those two histories from the ones kept in the run | 2.5e-14 |

## T3.3 What the present engine keeps

| places | quantities | segments | copies of the state around the steps | pickle with zlib (bytes) | of it, state by segment and by step (bytes, before zlib) |
| --- | --: | --: | --: | --: | --: |
| 30 | 60 | 29 | 100 | 58001 | 75840 |
| 100 | 200 | 81 | 314 | 573004 | 761600 |
| 300 | 600 | 234 | 935 | 8007579 | 6734400 |

| the table path of today, its own model | value |
| --- | --: |
| rows (places and routes) | 30,000 and 35,000 |
| steps | 35000 |
| compile and plan |  and  |
| run without the record | 5.37 |
| run with `record=True` | 5.48 |
| entries of the record (old values, old lines) | 175,000 and 35,000 |
| bytes of the record in memory | 39252838 |
| bytes of the trace in memory | 28064113 |
| a report of one output at three times, no lag | 0.0302 |

| routes | a report of one output with a uniform lag, at one time |
| --- | --: |
| 350 | 0.0261 |
| 3,500 | 1.66 |
| 35,000 | 202 |

Load: [5.71, 3.17, 1.82].
