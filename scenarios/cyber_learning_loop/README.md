# AI uptake and a national cyber workforce

Over 25 years, how does AI change the work a national cyber workforce can deliver across its surveillance and effects missions? The model fixes a starting workforce, assigns its four groups of specialists and measures completed work in **baseline-equivalent staff-years**. A separate national account estimates completed effects operations and their annual rate. Budget reviews respond to the work actually delivered. The institution tracks whether effects output consistently meets a configurable service standard. [Current model](model.scn) · [Run comparisons](results/brief.md)

With the reference staffing assumptions, fast uptake increases cumulative effects work by **27.05%** and surveillance work by **25.83%** relative to the same run with adoption switched off. Slow uptake increases them by **18.47%** and **17.83%**, respectively. At year 25 the reference reliance indicator is on for fast and slow uptake. It is off for no uptake and for reversal, whose track-record score has decayed to 0.02465. These figures describe the labor and adoption assumptions of this model. [Matched no-AI results for all 12 runs](results/matched-uptake.csv)

```sh
python -m napkin run scenarios/cyber_learning_loop --run ai_fast \
  --value ai_tools.progress,surveillance_program.completed,effects_program.completed,attacks_per_year,total_attacks,governance.reliance \
  --at 0h,4years,12years,25years
```

## National counts and completed work

| AI case | Cumulative operations at `8488047` | Current cumulative operations | Current operations/year at year 25 | Current change in cumulative operations versus no AI |
| --- | ---: | ---: | ---: | ---: |
| No uptake | 8,880 | 6,587.12 | 263.539 | 0% |
| Fast uptake | 5,290 | 7,168.63 | 288.000 | +8.83% |
| Slow uptake | 6,860 | 7,139.32 | 288.000 | +8.38% |
| Reversal after year 12 | 6,280 | 7,137.76 | 280.797 | +8.36% |

**The historical and current models give opposite directions for operation count.** The older fast pathway produced 40.4% fewer operations than its no-AI baseline. Its case mix and the availability of resources changed as AI use increased. In the aggregate model the average case consumes the same 12 baseline staff-years across these four runs. More completed work initially raises volume, then demand caps the rate at 320 × 0.9 = 288 operations/year. The current fast pathway delivers 27.05% more effects work and 8.83% more completed operations. [All twelve historical and current counts](results/historical-operations.csv) · [Matched workload and operation changes](results/matched-uptake.csv)

## What the programs count

Research, operator support, collection processing and analyst review draw on separate payroll groups. Research productivity follows the slower uptake curve. Operator support and collection processing follow the general curve. Defensive monitoring uses analyst time according to observed demand, hardening and remediation pace. The rest supports both missions. A temporary budget increase adds posts, and a transfer between missions divides the same domestic staff and available analyst hours.

At a budget review, the institution shifts one quarter of the gap between the reference effects share and its last share of delivered work. It credits learning from the preceding period’s work per employee times the share of hours reserved for training. Retained practice decays. Each mission books a work rate for the coming period and continuously accrues that work in staff-years. Reviews are annual in peacetime and quarterly in the wartime case. The initial allocation, periodic accounting, learning rule, AI labor savings and workload reserve are explicit assumptions. [Equations and their records](model.scn)

The national count uses three inputs. The annual demand ceiling is 320 operations, the average labor requirement is 12 baseline staff-years per operation, and availability is 90%. The model takes the smaller of demand and affordable volume, applies availability, and integrates that rate. Demand and availability are hypothetical. The labor requirement falls within the historical study’s 8.1–15.3 staff-year calibration interval. The capacity test also checks a low demand ceiling, a high-burden case and zero availability. [National count tests](tests/test_strategic_workforce.py)

The reliance calculation asks whether the effects mission delivered at least 120% of its opening staff-year rate in the preceding period. Reviews smooth these observations over three years. The indicator turns on when the score reaches 0.7 and can fall when performance declines. The `retained_practice` study varies the delivery threshold and the learning adjustment rate across paired runs. The `workload_reserve` study varies how much shared staff time the institution reserves for fluctuations in demand. Each study uses 16 paired draws per participating run. `workload_reserve` uses seed 7 and `retained_practice` uses seed 11. [Study definitions](brief.toml) · [Paired sampled results](results/paired-spreads.json)

At year 25, the reliance indicator was on in 10 of 16 fast-AI draws and 12 of 16 fast-AI draws with additional learning. It was on in 0 of 16 draws for both no AI and reversal. Across the 16 workload-reserve draws, the fast-AI case added an average of 581 expected operations over 25 years relative to no AI. The 5th and 95th percentiles of the paired differences were 576 and 588 operations. [Paired sampled results](results/paired-spreads.json)

## Mapping the historical cases

| Run at `8488047` and in the current entry | Assumption represented here | Difference in coverage |
| --- | --- | --- |
| `ai_fast`, `ai_slow`, `no_ai` | General adoption follows a four-year curve, twelve-year curve or zero progress. Reviewed work has a separate ten-year curve. | The downstream quantities are completed labor and expected national operations. |
| `ai_reversal` | Four-year adoption followed by erosion starting in year 12, taking back 80% of the original cost advantage over a three-year time constant. | The effect is on workload and future service reviews. |
| `ai_fast_lessons` | Leadership protects extra training time and retains practice from actual completed work. | The funding rule uses measured productivity and training time. The former discounted mission-value calculation has no direct counterpart. |
| `surge_today` | An extra $250 million annually buys posts for the first four years at $420,000 per expert-year. AI uptake remains zero. | The study follows payroll and added service capacity. |
| `dispersed`, `dispersed_no_ai` | The common-factor coefficient falls from 0.30 to 0.13. The programs reserve less shared capacity for correlated workload. | The factor represents budgeted administrative slack here. The historical program used it in a distribution of outcomes across targets. |
| `defenders_ai` | Lasting improvements include 0.5 × AI uptake. Remediation pace rises with uptake. | Hardening and remediation affect the defensive call on available analyst time. |
| `wartime` | Quarterly budget and service reviews replace annual reviews with no AI progress. | The program represents institutional tempo. Historical use opportunities and execution deadlines are absent. |
| `analysts_one_share` | Analysts share the slower review-adoption path at the original 20% and 30% end shares. The starting payroll reflects the historical alternative. | The shares apply to mission-level review work. |
| `slow_spy_planning` | Surveillance review adopts AI at the slower review pace. Other roles keep their general uptake paths. | The model measures effective labor available for review. |

The original model counted operations from its simulated mission processes. This model converts completed labor to an expected national count using average burden, demand and availability. A staff-year measures labor at a reference productivity and has no inherent conversion to operations. The historical figures are published to three significant digits. The receipt compares both cumulative counts in operations and their 25-year averages in operations/year. The current endpoint rate is reported separately because an endpoint and a period average answer different questions. [Historical and current operation counts](results/historical-operations.csv)

The historical access counts, assessed effects, opportunity costs and military doctrine depend on stages and outcomes outside this aggregate model. The current reliance score and its sampled frequency are a service-standard sensitivity analysis. The original `doctrine_probability` and `tipping_corner` spreads remain available with their historical definitions and results. [Historical sources and reports](historical/README.md)

## Historical numerical comparison

The pinned interpreter supplied the four workforce headcounts, total workforce and analyst capacity at initialization for each of the 12 named configurations. It evaluated the time-only general and review adoption curves and the defensive hardening and remediation formulas at years 0, 1, 4, 10, 12, 15 and 25. All **408 observations** agree within relative tolerance 10⁻¹⁰ or absolute tolerance 10⁻¹². Two initial values differ in floating-point rounding for `analysts_one_share`. All historical and current discrepant values are recorded in the receipt. [Pinned readings](tests/strategic-reference.json) · [Numeric differences](results/workforce-legacy-differences.csv)

The separate defensive-response entry accepts workload and adoption as supplied inputs and has its own 200-reading reference. [Defensive response](defensive_response/README.md)

```sh
git show af5428b:scratch/rewrite/a5/compare_strategic_workforce.py > compare_strategic_workforce.py
python compare_strategic_workforce.py /path/to/8488047 > historical-workforce.json
python scenarios/cyber_learning_loop/tools/strategic_workforce_results.py scenarios/cyber_learning_loop/results
python -m tools.publish --check --scenario cyber_learning_loop --sample-spreads --jobs 4
```
