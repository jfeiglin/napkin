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
| 30 | 35 | no | 27 | 35 | 1.1e-13 | 1.08 |
| 30 | 35 | no | 23 | 35 | 1.1e-13 | 0.177 |
| 100 | 116 | no | 79 | 116 | 1.7e-13 | 1.14 |
| 300 | 350 | no | 232 | 350 | 5.7e-13 | 13.4 |
| 30 | 35 | yes | 22 | 35 | 144 | 1.09 |

Load: [1.17, 3.01, 3.32].

## T1.4 The layout against its second implementation, with rings

| places | routes | stocks that empty | moves | largest difference of a store (L) |
| --- | --: | --: | --: | --: |
| 300 | 350 | 228 | 349 | 5.5e-11 |
| 3000 | 3500 | 2450 | 3498 | 4.3e-11 |

## T1.5 The cost at scale: the layout, run on lines

|  | 300 places | 3,000 places | 30,000 places | 300,000 places |
| --- | --: | --: | --: | --: |
| places | 300 | 3,000 | 30,000 | 300,000 |
| routes | 350 | 3,500 | 35,000 | 350,000 |
| stores | 600 | 6,000 | 60,000 | 600,000 |
| flows | 650 | 6,500 | 65,000 | 650,000 |
| the two tables (bytes) | 25,309 | 264,672 | 2,777,836 | 29,122,841 |
| build: read the tables, links, network | 0.0012 | 0.0109 | 0.124 | 2.43 |
| start of the run | 0.00047 | 0.0047 | 0.0537 | 1.08 |
| run to 48 h | 0.0101 | 0.11 | 1.35 | 15.8 |
| moments | 490 | 5,045 | 50,302 | 502,760 |
| stocks that empty | 140 | 1,546 | 15,325 | 152,936 |
| moves | 350 | 3,499 | 34,977 | 349,824 |
| lines that start again | 1,397 | 14,329 | 143,921 | 1,431,253 |
| microseconds for each moment | 20.6 | 21.8 | 26.9 | 31.3 |
| total at 48 h less total at 0 h (L) | 2.9e-11 | 5.8e-11 | 0 | 0 |
| total at 0 h (L) | 35,175 | 328,718 | 3,305,805 | 32,972,557 |
| connected sets (plain rule) | 29 | 317 | 3,384 | 33,507 |
| stores of the largest set | 532 | 5,252 | 52,038 | 520,850 |
| peak memory of the process (MB) | 58.5 | 67.4 | 158 | 844 |
| runs (the best is given) | 3 | 3 | 3 | 1 |
| load | [1.15, 2.97, 3.31] | [1.15, 2.97, 3.31] | [1.14, 2.94, 3.3] | [1.0, 1.49, 2.47] |

## T1.6 Both tables with their rows in another order, 30,000 places and 35,000 routes

| order of the rows in memory | named values | values with other bits | largest difference (L) |
| --- | --: | --: | --: |
| rows in the order of their ids | 60000 | 0 | 0 |
| rows in the order of the file | 60000 | 2929 | 1.4e-13 |

## T2.1 The connected sets of the model with 30,000 places and 35,000 routes (a component has at most 150 stores)

| case | sets | stores of the largest | arrays: a store alone, or with one flow | one component of the continuous engine | lines, with rates from the sparse solver at each moment | refused: a large set with a rate that reads a value that moves | time of the cut |
| --- | --: | --: | --: | --: | --: | --: | --: |
| the requests read no value that moves | 33384 | 26019 | 32,948 sets, 32,948 stores | 435 sets, 1,033 stores | 1 sets, 26,019 stores | 0 sets, 0 stores | 0.0504 |
| the same, with the plain rule: a tally joins the flow into it | 3384 | 52038 | 0 sets, 0 stores | 3,383 sets, 7,962 stores | 1 sets, 52,038 stores | 0 sets, 0 stores | 0.0137 |
| the request of each route reads the stock of its origin | 33384 | 26019 | 32,948 sets, 32,948 stores | 435 sets, 1,033 stores | 0 sets, 0 stores | 1 sets, 26,019 stores | 0.0105 |
| the request of each route reads the stock of a third place | 30948 | 29045 | 30,943 sets, 30,943 stores | 4 sets, 12 stores | 0 sets, 0 stores | 1 sets, 29,045 stores | 0.0102 |
| one solver sets the rate of every route | 32949 | 27052 | 32,948 sets, 32,948 stores | 0 sets, 0 stores | 1 sets, 27,052 stores | 0 sets, 0 stores | 0.0078 |

## T2.2 One connected set as one component of the present general tier (horizon 300 h)

| request of a route | places | stores | flows | build | run | evaluations of the rates | ms for each | of it in the allocation | linear programs | peak memory (MB) | note |
| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| constant | 30 | 60 | 65 | 0.0697 | 0.072 | 87 | 0.319 | 87% | 0 | 126 | 3 run(s), load 1.0 |
| constant | 100 | 200 | 216 | 0.226 | 0.838 | 243 | 1.45 | 94% | 0 | 178 | 3 run(s), load 1.0 |
| constant | 300 | 600 | 650 | 1.05 | 12.6 | 702 | 10.5 | 98% | 0 | 865 | 1 run(s), load 1.0 |
| constant | 1000 | 2000 | 2166 |  |  |  |  |  |  | 801 | SimulationError: The moment t=1 h does not settle within 1000 steps; next: routes_1001.shi |
| constant, rings | 30 | 60 | 65 | 0.0723 | 0.615 | 78 | 7.67 | 99% | 21 | 126 | 3 run(s), load 1.0 |
| constant, rings | 100 | 200 | 216 | 0.379 | 1.03 | 258 | 1.46 | 94% | 0 | 161 | 1 run(s), load 1.0 |
| constant, rings | 300 | 600 | 650 | 0.952 | 861 | 702 | 1,219 | 100% | 510 | 919 | 1 run(s), load 1.0 |
| linear | 3 | 6 | 6 | 0.0149 | 0.295 | 2484 | 0.0687 | 70% | 0 | 122 | 3 run(s), load 1.02 |
| linear | 10 | 20 | 21 | 0.0342 | 0.345 | 2686 | 0.0791 | 71% | 0 | 121 | 3 run(s), load 1.02 |
| linear | 30 | 60 | 65 | 0.0867 | 1.05 | 5175 | 0.147 | 78% | 0 | 131 | 3 run(s), load 1.02 |
| linear | 100 | 200 | 216 | 0.265 | 8.07 | 16717 | 0.407 | 86% | 0 | 362 | 3 run(s), load 1.02 |
| linear | 300 | 600 | 650 |  |  |  |  |  |  | 4,883 | MemoryError: more than 5 GB |
| saturating | 3 | 6 | 6 | 0.0146 | 0.274 | 2642 | 0.0642 | 69% | 0 | 121 | 3 run(s), load 1.02 |
| saturating | 10 | 20 | 21 | 0.033 | 0.439 | 3620 | 0.0787 | 70% | 0 | 123 | 3 run(s), load 1.02 |
| saturating | 30 | 60 | 65 | 0.0875 | 1.25 | 6622 | 0.138 | 77% | 0 | 134 | 3 run(s), load 1.02 |
| saturating | 100 | 200 | 216 | 0.27 | 11 | 22737 | 0.439 | 84% | 0 | 377 | 3 run(s), load 1.02 |
| saturating | 300 | 600 | 650 |  |  |  |  |  |  | 4,883 | MemoryError: more than 5 GB |
| target | 3 | 6 | 6 | 0.0143 | 0.224 | 2262 | 0.0609 | 68% | 0 | 121 | 3 run(s), load 1.0 |
| target | 10 | 20 | 21 | 0.0328 | 0.384 | 2331 | 0.108 | 77% | 0 | 123 | 3 run(s), load 1.0 |
| target | 30 | 60 | 65 | 0.0915 | 1.58 | 5024 | 0.245 | 85% | 0 | 132 | 3 run(s), load 1.0 |
| target | 100 | 200 | 216 | 0.282 | 16.3 | 18890 | 0.829 | 90% | 0 | 226 | 3 run(s), load 1.0 |
| target | 300 | 600 | 650 | 1.23 | 683 | 131742 | 5.03 | 96% | 0 | 1,652 | 1 run(s), load 1.0 |

## T2.3 A large set whose requests read a stock: 30,000 places and 35,000 routes on sparse arrays

|  | value |
| --- | --: |
| stores | 60,000 |
| flows | 65,000 |
| nonzeros of the Jacobian | 94,998 |
| the same matrix, dense (MB) | 28,800 |
| one evaluation of the rates (ms) | 0.57 |
| the integration to 48 h | 32 |
| steps of the solver | 302 |
| evaluations of the rates | 2,784 |
| Jacobians | 35 |
| factorizations | 72 |
| stores at rest in the state of the two next rows | 15,311 |
| one sharing at that state, stand-in rule (ms) | 38.3 |
| one linear program at that state, bundled HiGHS | 0.226 |
| estimate: the run with the stand-in sharing at each evaluation | 107 |
| estimate: the run with one program at each evaluation (hours) | 0.174 |
| peak memory (MB) | 359 |
| load | [1.12, 2.88, 3.27] |

## T3.1 Two histories with the same readings

|  | read at 0, 6, 12 h | mean from 6 h to 10 h |
| --- | --: | --: |
| 8 L added at 7 h | [0.0, 0.0, 8.0] | 6 |
| 8 L added at 9 h | [0.0, 0.0, 8.0] | 2 |

## T3.2 The record with 30,000 rows

| what the run records | run to 48 h | added by the record | pieces | bytes as arrays | bytes packed | time to pack |
| --- | --: | --: | --: | --: | --: | --: |
| nothing | 1.39 |  |  |  |  |  |
| eight reductions (no max, no min) and five rows | 4.27 | 2.88 | 87538 | 1651120 | 1209778 | 0.0525 |
| ten reductions and five rows | 5.12 | 3.73 | 87569 | 1651864 | 1211058 | 0.048 |
| every store and every flow | 1.57 | 0.177 | 324857 | 6050512 | 2702960 | 0.175 |

30,000 places, 35,000 routes, 50,302 moments. Best of 3; load [1.01, 2.17, 2.95].

|  | value |
| --- | --: |
| recording changes the run | no |
| largest relative difference of a reduction kept in the run from the same made from every store | 3.6e-14 |
| pieces of each history kept in the run | {'held': 15327, 'used_total': 11763, 'critical_held': 4198, 'empty_places': 15326, 'low_places': 15953, 'any_critical_empty': 2, 'carried_now': 13169, 'unmet_use': 11763, 'fullest': 23, 'emptiest': 8} |
| passes over the rows for the greatest and the least | {'fullest': 29, 'emptiest': 414} |
| a report from the histories kept in the run: ten values at three times and one lag at three times | 0.0026 |
| from the record of everything: the ten reductions at three times | 0.0212 |
| from the record of everything: the whole history of two sums | 0.0172 |
| largest relative difference of those two histories from the ones kept in the run | 2.5e-14 |

## T3.3 What the present engine keeps

| places | quantities | segments | copies of the state around the steps | pickle with zlib (bytes) | of it, state by segment and by step (bytes, before zlib) |
| --- | --: | --: | --: | --: | --: |
| 30 | 60 | 29 | 100 | 58006 | 75840 |
| 100 | 200 | 81 | 314 | 573012 | 761600 |
| 300 | 600 | 234 | 935 | 8007572 | 6734400 |

| the table path of today, its own model | value |
| --- | --: |
| rows (places and routes) | 30,000 and 35,000 |
| steps | 35000 |
| compile and plan | 2.52 and 0.096 |
| run without the record | 5.12 |
| run with `record=True` | 5.71 |
| entries of the record (old values, old lines) | 175,000 and 35,000 |
| bytes of the record in memory | 39252838 |
| bytes of the trace in memory | 28064113 |
| a report of one output at three times, no lag | 0.0323 |

| routes | a report of one output with a uniform lag, at one time |
| --- | --: |
| 350 | 0.0262 |
| 3,500 | 1.67 |
| 35,000 | 191 |

Load: [1.01, 2.17, 2.95].
