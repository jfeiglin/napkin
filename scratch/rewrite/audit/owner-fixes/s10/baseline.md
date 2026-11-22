## S10 proof and citation baseline

All 1,200 seed IDs failed on macOS at `e003d1a`. Each of the four families completed all 300 seeds on a clean engine and reference tree. The ledger includes every observed mismatch and its generated model. [Complete results](baseline.jsonl.gz).

| Family | Seed-zero observation |
|---|---|
| Network | The route’s signed rate and the leg and endpoint readings had the correct physical values. Several direct and in-event reports omitted the meter that determined them. |
| Solver | An aliased target and its identity formula both read 3 L, but their trails omitted the measurement that fixed the solution. A solver-constrained flow of 3 L/h also omitted its measurement. |
| Arguments | Occurrences started with separately cited 2 L and 9 L values. Reports retained the values while losing their individual argument citations. A never-started occurrence credited an upstream input. |
| Reachability | Overriding the categorical default from WAIT to SEND started dispatch and removed 4 L. The proof classified dispatch as unable to start and permitted lag on the falling stock. Unchanged and monotone controls passed. |

A conditional solver constraint chose the 2 L/h input before hour 1 and the 9 L/h input afterward. Both record modes returned the correct rates. Reports queried in reverse time order omitted the citation for the input that set each rate. [Two pinned failures](solver-branch-red.log.gz).
