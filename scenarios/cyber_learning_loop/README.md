# cyber_learning_loop

[Model](model.scn) · [Specification](#specification-when-a-countrys-cyber-attacks-start-to-pay) · [Methods](results/methods.md)

This folder owns the model, evidence, units, tests and generated results. Shared mathematics and vocabulary remain central.

## Mechanism family

`cyber_learning_loop` is a strategic model, not a model of one incident. One capable country has four groups of cyber
experts for 25 years from 2026: researchers, who find flaws that the defenders do not know and build
the tools that use them for both missions; operators, who do the hands-on work of operations and whom
the leaders split between surveillance and effects operations (attacks); collection specialists, who
run surveillance's implants and turn their take into intelligence; and analysts, who plan the
operations of both missions and assess the damage of attacks. By default the groups keep their sizes;
as an option, the leaders retrain operators who wait for the analysts as analysts.

Each operation is a chain of steps. A step takes the units of the step before, people's hours and
capabilities from a pool, and it runs at the pace of the scarcest of them. Each group's hours go to the
operations farthest along first. These amounts change all the time:

- the share of the operators on attacks, which the leaders move toward a target that the assessed
  return of attacks against surveillance's current return sets;
- the share of the analysts on attacks, which moves toward the target of a staffing rule. By default the
  analysts go first to the mission where one more analyst-year is worth more. On attacks, damage
  assessment takes at most its share of the analysis work waiting, and planning takes the rest;
- the lessons that the force keeps, by stage: lessons of effects, the assessed outcomes that it gains
  from its attacks and loses to patches, burned tools, turnover and secrecy; and lessons of access,
  which the accesses of attacks and of surveillance both teach and which fade more slowly;
- the attention of the defenders, which the whole threat flow, counted in targets, draws towards a cap
  and time lowers; the force's attacks are a small share of that flow. As an option their lasting
  capability grows with time or with their own AI;
- the attack chain: an attack and its targets move together through initial access, movement inside
  the network and the effect, and the attack then waits ready for its moment or is made at once, and
  then waits for its damage assessment. Each attack keeps the targets that it started with, and the kinds
  of target system and the correlation of its targets when the force finishes its effect. The force
  learns from an attack when the assessment ends;
- the surveillance chain: accesses in initial access, accesses gained, and implants that collect while
  they live. The take waits in a queue until the collection specialists process it, and surveillance's
  value comes from the processed take;
- four pools of capabilities, one for each step: access and movement in the network, which both missions
  share, the effect, which only attacks use, and collection, which only surveillance uses. A capability is
  never used, used by surveillance, used in an attack, or burned. A step needs a capability for each kind
  of target system that no known flaw serves. Each such zero-day is one that surveillance uses, one kept
  from an earlier attack or a never-used one, and an empty source holds back only its part of the step;
  the missions start only the operations that the pools can equip. The researchers work to each pool's
  need and keep a reserve of a year of asks. An exposed attack burns the capabilities that it holds, and
  the defenders then find some of surveillance's accesses that run on shared ones. A flaw is also lost
  when others find it, when a patch closes it or when its systems stop mattering. A flaw in use is lost
  faster than one that waits, and AI helps the defenders find and close flaws in every run.

Military plans count on cyber attacks once a plan of attacks passes planning reviews in a row (yearly in
peace, every quarter in war), and stop when every plan misses in a row. The planners test plans from one
day to one quarter by one rule, so the length that doctrine forms around is a result. A plan passes when
its chance of falling short of the planned share of targets hit by no more than a tolerance reaches the
level that planners accept. The planned share is the mean share that pooled outcomes teach. The chance
counts the one defender that all of the plan's attacks face, the planners' forecast error, and the
capabilities that the attacks share: one for each kind of target system, each of which can fail on its
own and take the attacks that depend on it.
Today's split is a rest point of the funding rule, so the value of one intended effect is the value
that the country's choice reveals.

[The specification](#specification-when-a-countrys-cyber-attacks-start-to-pay) gives the state, the parameters with their ranges and bases, the equations, the
timing and the functional forms.

## The AI operation and its matched pathway

- **AI mechanism.** An attack's work is the sum of five kinds of work, each with work by hand for the
  attack and for each target, a share that AI does and a time. AI moves those shares and times along
  two paths, fast for access, the running of attacks and of implants, the analysis of each target and
  the planning of new accesses, and slow for payloads, the review, the approval and the assessment of
  the whole attack, the damage check of each target and the processing of the take. AI work
  costs supervision, which parallel attacks share, and compute, priced on working hours: today a unit of
  AI work already costs less than a unit by hand. So the cost of an attack, the time to build it and AI's
  share of the work are results. AI tailors the steps that an attack's targets share, so they fall
  together less often, and it removes one of the four kinds of evidence that attribute an attack. AI
  also moves the targets of one attack, and so its kinds of target system: each kind needs its own
  capability, so one failed capability takes less of a plan, but more capabilities can fail. AI
  multiplies the capabilities that a researcher finds. In surveillance, AI cheapens new accesses, widens
  the reach of each collection specialist and speeds the processing, so the gain of surveillance from AI
  is a result too. In every run, AI also helps the defenders find and close the force's flaws: discovery
  and patching reach three times today's rates at the end of AI progress.
- **Defenders' AI.** As an option ("Defenders' AI"), the defenders' own AI also hardens their networks
  and takes part of an attack's chance of success. `defenders_ai` runs the fast AI path with it.
- **War.** As an option, the country goes to war in 2026 from its peacetime posture: moments to use
  the attacks held ready come about monthly and the planners review every quarter. `wartime` runs it
  without AI progress.
- **Matched human pathway.** `no_ai` keeps every driver at its value today. It is the comparison of
  `ai_fast`, and without AI the force stays at today's split. `dispersed_no_ai` keeps the dispersed
  targets without AI, and it is the comparison of `dispersed`.
- **Decisive control.** Whether the lessons of attacks outlast their loss at the volume that cheaper
  attacks allow: the prior strength of lessons, the rate at which the force loses them, and how strongly
  budgets follow results. The analysts' work per attack limits that volume: AI does the work for each
  target sooner and further than the review, the approval and the assessment of the whole attack. How
  the leaders staff the analysts decides where that work goes.
- **Options of the analysts and the workforce.** "Analysts' AI" sets the AI shares of the analysts'
  work: `analysts_one_share` gives each stage of the analysts one AI share, and `slow_spy_planning` keeps
  the planning of surveillance's new accesses as slow as the review and the approval of an attack.
  "Analysts' staffing" sets how the analysts' split moves: by the value of one more analyst-year in each
  mission (the default), by each mission's share of the analysis work that it needs ("Work waiting"), or
  fixed at today's split ("Fixed split"). "Workforce" keeps the four groups at their sizes ("Fixed
  groups", the default) or retrains the operators who wait for the analysts as analysts, at half an
  analyst's work, over about three years ("Idle operators retrain").
- **Comparison measures.** Attacks made, attacks made and started in a year, the attacks held ready, the
  targets on their way, the share of the operators and of the analysts on attacks, the share of the
  possible new operations that the analysts plan, the operators who wait for the analysts, the return of
  an operator on surveillance, the accesses and implants that surveillance holds and the implants that it
  runs, the capabilities in each state, the chance of success on one target, the defenders' attention and
  lasting capability, the chance that the best plan meets its plan, its length, whether plans count on
  cyber attacks, and the weight of lessons. Deaths, serious casualties and economic loss are not
  estimated.

## What the model finds

The results of the model are refreshed with its publication: [results/brief.md](results/brief.md)
gives them at the defaults, and [the specification](#7-calibration-notes), section 7, gives today's state that the inputs set.
The results below come from the runs at the defaults.

- At the defaults, without AI the force stays at today's split and makes 355 attacks a year. Plans
  never count on cyber attacks: the best plan today, a one-day salvo, meets its plan with a chance of
  0.754 against the 0.8 needed.
- With fast AI, plans start to count on cyber attacks in 2044: the planning reviews pass from 2042, and
  the best plan's chance is 0.813 in 2051. When funding also counts the value of lessons, doctrine forms
  in 2043. Each attack reaches about 30 targets and takes more work, so
  in 2051 the force makes fewer attacks than today, about 190 a year, but hits about 1,600 targets a year
  against 71 today.
- That result holds only in a part of the input ranges, and no source measures these inputs. In fast AI,
  doctrine forms by 2051 only when AI tailors about 0.75 or more of the steps that an attack's targets
  share; 0.73 gives none. It also needs an attack to reach between about 2 and 40 targets at the end of
  AI progress; 1 target or 50 give none. With no extra kinds of target system, it forms only at the last
  review, in 2051.
- The default staffing of the analysts carries the result too. When the analysts' split follows the
  work that each mission needs, or stays at today's split, or when idle operators retrain as analysts,
  fast AI forms no doctrine by 2051: the best chance in 2051 is 0.799, 0.769 and 0.7998.
- Doctrine years are fragile. Near 0.8 the best plan's chance rises by only about 0.002 a year: the 2041
  review misses by 0.0001, and planners who need 0.79 or 0.81 move the year to 2040 or 2050.
- The model also gives doctrine as a chance, not as a year: the study `doctrine_probability` gives the
  share of 160 calculations in which military plans count on cyber attacks. Each calculation draws four
  values of the planners and the defenders from the ranges of the evidence (the chance that the planners
  need, the shortfall that they accept, the floor of their error and the common spread of the
  defenders), and the error of each yearly assessment. The pathways use the same draws, so the chance
  with fast AI less the chance without AI is the chance that only AI brings doctrine. In a first test of
  20 calculations (about ±0.1), doctrine held by 2051 in 55% of them with fast AI and in 30% without AI,
  so AI alone brought it in about a quarter of them; where it formed without AI, today's plan already met
  the drawn need. The shortfall that the planners accept and the chance that they need decide most of
  it. The published study replaces these first figures.
- In one corner of the inputs (a prior strength of 300 and a curve shape of 3), today is a tipping point:
  the spread `tipping_corner` draws only the yearly assessment error, and its calculations split between a
  force that moves to attacks and one that leaves them.
- With slow AI, with the defenders' AI, or when the costs of attacks rise again, no doctrine forms by
  2051: the best chance in 2051 is 0.792, 0.783 and 0.761.
- Dispersed targets form doctrine in 2029, at the third review, with AI and without it: the chance is
  0.908 already today. So the dispersed run does not show an effect of AI.
- The analysts plan the operations of both missions and assess the damage of attacks. When AI widens
  each attack to many targets, the analysts' work per attack grows, so the analysts can limit how many
  operations both missions start. By default they go to attacks, where one more analyst-year is worth
  far more. So in fast AI in 2051 they plan only 38% of the accesses that surveillance's operators could
  start, and about 530 of those operators wait. With one AI share for each stage of the analysts, they
  plan only about half of the attacks that the operators can start, the force makes about 90 attacks a
  year in 2051, and no doctrine forms. Slow planning of surveillance gives doctrine in 2044, as fast AI
  does.
- A failed capability that a plan's attacks share takes the attacks that depend on it: half of a plan
  today. As each attack reaches more kinds of target system, one failure takes less of a plan, but more
  capabilities can fail.
- The defenders' attention barely follows the force's attacks, because the force is a small share of the
  threat that they answer. At the defaults the researchers keep up with the needs of the missions, so
  the pools of capabilities hold back no operation in fast AI, with the defenders' AI or in war.
- War uses up the attacks held ready within about a quarter, and no doctrine forms: the best plan is a
  one-month plan, with a chance of 0.667 in 2051. While the attacks held ready drain, the operators'
  hours go to execution first. Damage assessment takes only its share of the analysts' hours, so the
  analysts still plan new attacks.

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) · [Assumptions](evidence/assumptions.json) · [Local units](units.json) · [Oracle inputs](tests/oracle-inputs.json)

- **Claims.** The model cites 63 claims. Fifty-three verified claims anchor today's split, the budget
  cycle, the stages of an attack's work and AI's share of them, AI's help with targeting and damage
  assessment and the policy that sets the approval of operations, the cost of waiting, the low success of
  documented effects, attribution and sanctions, damage assessment, the 2025 surge, the planners' error,
  the lapse of a weapon from plans, the drift of mass attacks on unconnected victims, how fast defenders
  fix a famous flaw, how AI finds flaws, surveillance's implants, their automated control and how long
  espionage stays hidden, the defenders (the threat flow that they answer, how their fixes saturate, how
  fast exposed actors return, the reuse of exposed tools and flaws, and their gains in detection and
  from AI), the life of a private zero-day, the zero-days that defenders catch in use each year and who
  uses them, and the wartime tempo of 2022. Two of them are adopted from `heat_wave_blackout`. Eight more are partial,
  because no stored copy matches their records: the budget response, a drone campaign against one
  defender, how fast defenders fix known-exploited flaws, the compute cost of AI-built exploits, and four
  figures of the life of a zero-day (its 6.9-year life, how often others find it again, the other ways
  to lose it and its life in use). Seven of them are in PDFs, and their recorded extractor was not
  available to match the quotes again. Two are unverified: the use of implants and the staff of the
  implant program in 2011, whose article is paywalled, and the learning rates and task overlap of
  aircraft production, in a PDF; the model uses their figures as the research notes quote them.
- **Assumptions.** Fourteen unreviewed assumptions give every other value with a range that a reader can
  explore; two of them cover the four kinds of expert and the pools of capabilities.
- **Tests.** The scenario's tests in `tests/` are rewritten for the rebuilt model: an independent oracle
  of today's rest point and of the rest points over time, and checks of each mechanism with independent
  mathematics. This list is refreshed with them.

## Consequences

`cyber_learning_loop` gives no harm of an attack. Its results are indicators of a change in how a country fights:

- the share of attacks from access built on demand;
- the attacks held ready for their moment, and the attacks started against the attacks made;
- the targets on their way through initial access, movement and the effect;
- the accesses and implants that surveillance holds, the share of its implants that it runs, and the
  accesses that the defenders find through burned capabilities;
- the share of the operators and of the analysts on attacks, the share of the possible new operations
  that the analysts plan, and the operators who wait for the analysts;
- the chance of success on one target, the defenders' attention and their lasting capability;
- the work of each stage of an attack, and the lessons of access;
- lessons gained and lost in a year;
- the signal-to-noise ratio of damage assessment;
- spending on attacks;
- targets hit in a year;
- the kinds of target system in one attack, and the share of a plan's effect that one failed shared
  capability takes;
- planning reviews passed and missed, whether plans count on cyber attacks, and the length of the plan
  that doctrine forms around.

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/cyber_learning_loop
python -B -m tools.publish --write --scenario cyber_learning_loop
python -B -m tools.check --scenario cyber_learning_loop
```

The analysis of rest points, branches and sensitivity reads the model through `napkin.dynamics`
([docs/python-api.md](../../docs/python-api.md#dynamics)).

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`; local tests and prose remain authored files.

[Shared testing rules](../../CONTRIBUTING.md#testing)

## Specification: when a country's cyber attacks start to pay

The model lives in [model.scn](model.scn); this section states it in mathematics. Every value has a
record in the model file, and the evidence is in [evidence/](evidence/).

### 0. Principle: single actions in, conclusions out

Each input describes one action or one actor's rule: the work of one stage of an attack and the kind of
expert who does it, the share of it that AI does and its time, the work to gain one access of
surveillance, the capabilities that a step needs and where they come from, the rate at which defenders
fix a flaw, the value of one intended effect. The totals are results: the work and the time of an
attack, the attacks of a year, AI's share of the work, the capabilities that the missions take and burn,
the implants that surveillance runs, the gain of surveillance from AI, the split of the operators and of
the analysts, and whether plans come to count on cyber attacks.
Today's observed totals are checks against the evidence, never targets, and today is a rest point by
construction. Harms are not estimated.

### 1. Scope, time and units

- One capable country (US evidence), 25 years from the start of 2026. Its cyber experts are four
  groups, which keep their sizes by default: researchers, who find flaws and build tools for both
  missions; operators, who do the hands-on work of operations and whom the leaders split between the
  missions; collection specialists, who run surveillance's implants and process their take; and analysts,
  who plan the operations of both missions and assess the damage of attacks. As an option, the leaders
  retrain idle operators as analysts.
- Attacks and surveillance run in separate chains of steps. A step takes the units of the step before,
  people's hours and capabilities from a pool, and it runs at the pace of the scarcest of them.
- Time t is in years. The engine runs in hours, at a resolution of 7 days, with its timescales.
- Units:
  - experts in people, and work in person-years;
  - attacks (effects operations) in operations;
  - targets, independent outcomes and assessed outcomes, in targets;
  - surveillance's accesses and implants, and the lessons of access, in accesses;
  - surveillance's take in access-years: one implant run for one year;
  - capabilities (a flaw that the defenders do not know, with the tools that use it) in capabilities;
  - value in **SEV**: the value of one expert-year of surveillance in 2026. SEV compares the two
    missions; it is not a price.
- Money is in USD2025. It enters through the surge, the price of compute against the cost of an expert,
  and spending.

### 2. State

| Symbol | Model name | Meaning | Kind |
|---|---|---|---|
| s | `leadership.attack_share` | Share of the operators on attacks | stock, s ∈ (s_min, s_max) |
| s_N | `analysts.attack_share` | Share of the analysts on attacks | stock, s_N ∈ [0, 1] |
| s_O | `operators.retrained_share` | Share of the operators who do analysis work | stock, s_O ∈ [0, 0.9] |
| τ | `effects_program.know_how` | Lessons of effects kept: assessed outcomes | stock, τ ≥ 1 target |
| τ_a | `effects_program.access_know_how` | Lessons of access kept: accesses gained | stock, τ_a ≥ 1 access |
| A | `defenders.alertness` | Defender attention (log-odds lost) | stock |
| X_i | `effects_program.in_access` | Targets whose initial access the force is gaining | stock |
| X_m | `effects_program.accesses` | Targets where the force has access and moves inside the network | stock |
| X_p | `effects_program.positioned` | Targets on the systems that the effect needs, while the effect is built | stock |
| N_i, N_m, N_p | `effects_program.in_access_attacks`, `access_attacks`, `positioned_attacks` | Attacks whose targets are in X_i, X_m and X_p | stock |
| N_h | `effects_program.held_ready` | Attacks built in advance, held ready for their moment | stock |
| X_h | `effects_program.held_targets` | Targets of the attacks held ready | stock |
| X_h^ρ | `effects_program.held_spread` | The same targets, each attack's weighted by the correlation of its targets: Σ m(1 + (m − 1)ρ_w) | stock |
| I_h | `effects_program.held_outcomes` | Independent outcomes of the attacks held ready: Σ m/(1 + (m − 1)ρ_w) | stock |
| N_q | `effects_program.assessing` | Attacks made, awaiting the end of their damage assessment | stock |
| X_q | `effects_program.assessing_targets` | Targets of the attacks under assessment | stock |
| I_q | `effects_program.assessing_outcomes` | Independent outcomes of the attacks under assessment | stock |
| G_i | `surveillance_program.accesses_underway` | Accesses whose initial access surveillance is gaining | stock |
| G_h | `surveillance_program.accesses_held` | Accesses gained, before movement and the deployment of an implant | stock |
| G | `surveillance_program.implants` | Implants deployed, which collect while they live | stock |
| Q | `surveillance_program.collected` | Take that waits to be processed | stock, access-years |
| F_k | `<pool>.fresh` | Capabilities of pool k that no one has used | stock |
| U_k | `<pool>.spy_used` | Capabilities of pool k that surveillance uses and no attack has used | stock |
| C_k^s, C_k^a | `<pool>.held_shared`, `held_attack` | Capabilities held by attacks underway, which surveillance also uses or not | stock |
| R_k^s, R_k^a | `<pool>.kept_shared`, `kept_attack` | Capabilities kept from earlier attacks that were not exposed, which surveillance also uses or not | stock |
| B_k | `<pool>.burned` | Capabilities of pool k that exposed attacks burned | tally |
| e | `leadership.assessment_error` | Error of the latest yearly assessment | number state (yearly) |
| P | `military_planners.passes_in_a_row` | Planning reviews passed in a row | number state (each review) |
| M | `military_planners.misses_in_a_row` | Planning reviews missed in a row | number state (each review) |
| — | `military_planners.tempo` | "peace" or "war" | named state |
| D | `military_planners.doctrine` | "none", "formed" or "lapsed" | named state |
| T_D | `military_planners.formed_length` | Length of the plan that doctrine last formed around | number state |

The pools are k ∈ {access, movement, effect, collection} (`access_pool`, `movement_pool`, `effect_pool`,
`collection_pool`). A capability used in an attack is one of C_k^s, C_k^a, R_k^s and R_k^a.

An attack keeps the targets that it starts with, and the kinds of target system and the correlation that
it has when the force finishes its effect. So each stock of attacks has its own size: m_i = X_i/N_i,
m_m = X_m/N_m, m_p = X_p/N_p, m_h = X_h/N_h and m_q = X_q/N_q targets for each attack, each at least one.
A flow of attacks out of a stock takes their targets with them, at the size of the stock.

The equilibrium analysis follows the 47 stocks above, B_k apart. Seven of them are empty by
construction: no surveillance uses the effect's capabilities (U, C^s and R^s of the effect), and no
attack uses collection's (C^s, C^a, R^s and R^a of collection). The share s_O moves only in the option
"Idle operators retrain", and only while operators wait, so it is 0 at today's rest. The number states,
D and the tempo are frozen there, and the cumulative counts (B_k and the tally of attacks) are passive.

### 3. Equations (per year)

**AI progress.** Two paths, g(t) = clip(π·[(1 − e^(−t/T)) − ζ·(1 − e^(−max(t − t_r, 0)/T_r))], 0, 1):
g₁ with T = T_AI for access, the running of attacks and of implants, supervision, compute and the
defenders' AI, and g₂ with T = T_P for payloads, the work of target analysis and of damage assessment
for the whole attack, the damage check of each target and the processing of the take, which AI reaches
more slowly. The target analysis of each target, and with it the planning of new accesses, moves on g₁.
Here π is the pace (0 without AI) and ζ the reversal depth (0 by default). The targets of one attack
move along g₁ from today's to their end value, m = m₀(m∞/m₀)^g. This m is the size of the attacks that
the force starts now; each attack then keeps its targets (§2). A rule that chose m as an optimum would
need a cost of each added target that no source measures, and calibrated to one target per attack
today it would hold AI-era attacks near one target, against the evidence of about 30. So m stays an AI
path.

**Experts: four groups.** Today's experts on attacks, s₀·H with H the experts, are operators and
analysts as the stages of an attack say: n₀ = s₀H/c₀ attacks a year, with c₀ the work of an attack today
(below), O_a0 = n₀·c_o0 operators and N_a0 = n₀·(c_plan,0 + c_assess,0) analysts. The researchers are a
share ψ_R of the experts, R = ψ_R·H. The other experts of the agency, L_e = (1 − s₀)H − R, work for
surveillance in shares:
- operators who gain access and deploy implants: O_s0 = φ_b·L_e;
- analysts who plan new accesses: N_s0 = ψ_P·ψ_A·L_e;
- collection specialists, the rest: Z_r0 = (1 − ψ_A)L_e − O_s0 run implants and Z_p0 = (1 − ψ_P)ψ_A·L_e
  process their take.

The groups O = O_a0 + O_s0, Z = Z_r0 + Z_p0, N = N_a0 + N_s0 and R add up to H, and by default they
keep their sizes. Today's share of the operators on attacks, s₀' = O_a0/O, follows from today's work; at
the defaults it is 0.575 (2,424 of 4,214 operators).
- **Workforce** (the group "Workforce"). In the option "Idle operators retrain", the leaders retrain the
  operators whose hours wait for the analysts: ds_O/dt = O_idle/(O·T_O), with T_O the time to retrain
  (3 years) and O_idle = O_a·max(1 − n_s/n_w, 0) + O_s·max(1 − b_r/b, 0) the idle operators (n_s, n_w, b_r
  and b below). The flow goes one way, and s_O stays at most 0.9. A retrained operator does the share φ_r
  (0.5) of an analyst's work. By default ("Fixed groups") s_O stays 0. No operator waits today, so today
  is at rest in both options. Every run reports O_idle.
- The leaders split the operators who do operations, O' = (1 − s_O)·O: O_a = s·O' + H_surge on attacks
  and O_s = (1 − s)·O' on surveillance.
- The analysts can do C_N = (N + φ_r·s_O·O)/ℓ of work, ℓ the share that today's work fills (0.9). Their
  split moves toward the target s_N* of the staffing rule: ds_N/dt = (s_N* − s_N)/T_N, with T_N the time
  to adjust (1 year). The analysts on attacks can do C_a = s_N·C_N, and those on surveillance
  C_s = (1 − s_N)·C_N.
- The staffing rule (the group "Analysts' staffing") reads the analysis work that each mission needs:
  W_a = max(N_q/T_q, n_w)·c_assess + n_w·c_plan for attacks, the work of the attacks that the operators can
  start, or of the queue when it is larger, and W_s = b·w_p for surveillance (below). The three rules
  give today's split at rest:
  - by the value of the work (default): s_N* = π_N·min(W_a/N, 1) + (1 − π_N)·max(1 − W_s/N, 0). The first
    term gives attacks their work first and the second gives surveillance its work first, each with
    today's slack. The priority of attacks, π_N = 1/(1 + (V'_s/V'_a)^β_N) with β_N = 2, compares the value
    of one more analyst-year on attacks, V'_a = max((V_R/(1 + X/X_s) − C)/n, 0)/(c_plan + c_assess), with
    its value on the planning of surveillance, V'_s = ε·V_s·K/(G + K)/(b_r·w_p). Here V_R, X and C are the
    value, the targets hit and the costs of a year's attacks, and V_s, K and G surveillance's value, reach
    and implants (below). Today V'_a is 41 and V'_s 1.9 SEV per analyst-year, because the collection
    specialists, not the accesses, limit surveillance's take; so π_N is nearly 1 today;
  - by the work waiting ("Work waiting"): s_N* = W_a/(W_a + W_s);
  - fixed ("Fixed split"): s_N* is today's share, N_a0/N.

**Correlation of an attack's targets.** The targets share steps that work with the chance Q; given
them, each target succeeds with the chance p/Q. So ρ_w = p(1 − Q)/(Q(1 − p)), exact for this
two-level model. Today Q₀ = p₀/(p₀ + ρ₀(1 − p₀)) reproduces the observed ρ₀. A share φ₀ = ln Q₀/ln p₀
of the log-chance lies in the shared steps; AI tailors a share τ = τ∞·g₁ of them to each target, so
Q = p₀^((1 − τ)φ₀). The correlation is taken at today's p₀: lessons do not feed back into it. An attack
keeps the ρ_w of the time when the force finishes its effect (§2).

**Attribution** (the template `Channel`): q = 1 − Π_c (1 − q_c) over four kinds of evidence (tools,
infrastructure, operators, targeting), each q_c = q_c0 + (q_c∞ − q_c0)·g₁. Only the tools channel
falls with AI by default. q₀ is a check against the evidence: 0.6–0.95.

**Stages of work** (the template `Stage`; person-years for one attack). An attack needs five kinds of
work k: target analysis and approval, access, building and testing the effect, running the attack, and
damage assessment. Each has work by hand W_k for the attack and w_k for each target, AI's share
a_k = a_k0 + (a_k∞ − a_k0)·g_k on its path, and a time T_k = T_k0·(T_k∞/T_k0)^(g_k). A unit of AI work
costs an expert's supervision σ_s, which the P attacks that one expert runs at once share, and compute
κ, priced in expert-years at the cost of an expert e:
- c_k = [W_k·u(a_k) + w_k·m_k·u(b_k)]·(w(L) if k is held ready, else 1), with
  u(a) = (1 − a) + a·(σ_s/P + κ/e) and m_k the targets of the attacks that the stage serves: m, except in
  damage assessment, whose work for each target counts the attacks under assessment, m_q;
- b_k = a_k, except in the two stages of the analysts, where the work for each target has its own share
  b_k = b_k0 + (b_k∞ − b_k0)·g on its own path: target analysis 0.2 → 0.75 on g₁, the damage check
  0.1 → 0.6 on g₂. AI does the repeated work for each target; policy sets the review, the approval and
  the assessment of the whole attack, at a_k. The option "One AI share" sets b_k = a_k;
- P = P₀(P∞/P₀)^(g₁) and κ = κ₀(κ∞/κ₀)^(g₁). Parallel supervision saves only the AI part of the work.
- The compute is priced on working hours, about 2,000 in an expert-year: κ₀ = USD 0.1 m and
  κ∞ = USD 0.01 m for each expert-year of AI work, against e = USD 0.42 m for an expert. So today a unit of
  AI work costs σ_s/P₀ + κ₀/e = 0.44 of a unit by hand.
- Access is two steps that split its time and its work by the share ψ_i (0.5): initial access, with
  T_i = ψ_i·T_acc and w_i = ψ_i·c_acc/m for each target, and movement inside the network, with
  T_m = (1 − ψ_i)·T_acc and w_m = (1 − ψ_i)·c_acc/m.

**Cost of an attack: lessons by stage.** c = Σ_{k≠a} c_k·(1 − γ_c·Δk) + c_a·F_a, and today's
c₀ = Σ_k c_k at g = 0 and m = m₀.
- The stages that only attacks do learn from the lessons of effects, Δk (below).
- The access stage a, whose work surveillance also does, learns from the lessons of access by Wright's
  law: F_a = (τ_a/τ_a0)^(log₂(1 − λ_a)), so each doubling of the lessons saves the share λ_a of its work.
  dτ_a/dt = α_a·r_i + ω·α_s·r_si − δ_a·τ_a: the targets where the force gains initial access, and the
  accesses where surveillance gains initial access, r_si, at the overlap ω of the two tasks (α_a, α_s, the
  served shares of the access pool, r_i and r_si below). The lessons of access fade at δ_a, more slowly than those of effects.
- The time to build an attack is L = T_i + T_m + T_e: initial access, movement and the effect.
- AI's share of the work is Σ (a_k·W_k + b_k·w_k·m_k) / Σ (W_k + w_k·m_k), and the compute of a year costs
  n_s·κ·Σ (a_k·W_k + b_k·w_k·m_k), for the n_s attacks started in a year.
- The waiting factor is w(L) = 1 + π_pre(L)(δ_P + u)/λ.
- π_pre(L) = 1 − 1/(1 + (L/W)^ν) is the share of attacks whose build takes longer than the warning
  W, so they need access built in advance. That access decays at δ_P, needs upkeep u and waits a mean
  1/λ for its moment.
- In war, λ and W take their wartime values λ_w and W_w (below).
- c₀, n₀ and L₀ are results, so they are checks against the evidence: 8.1–15.3 expert-years, 231–437
  attacks a year and 2–11 months (tests/test_calibration.py). At the defaults they are 9.9,
  355 and 9 months.

**Attacks: the chain of steps.** An attack and its targets move together through three stocks, and then
the attack moves with its targets through two (§2). The operators' hours O_a go to the steps farthest
along first, and each step runs at the lower of its pace by time and the pace that its hours left allow:
- execution: the attacks due are E* = λ·N_h + (1 − π_pre)·N_p/T_e, and the operators can execute the
  share σ_x = min(1, O_a/(E*·c_x)), with c_x the work of running an attack of the targets that the attacks
  due carry, m_x = (λ·Θ_h + (1 − π_pre)·X_p/T_e)/E*: c_x = [W_x·u(a_x) + w_x·m_x·u(b_x)]·(1 − γ_c·Δk);
- the effect: r_e = min(N_p/T_e, h_e/c_e') attacks a year, with h_e = max(O_a − σ_x·E*·c_x, 0) and c_e'
  the operators' work to build the effect of an attack of m_p targets;
- movement: r_m = min(X_m/T_m, h_m/w_m) targets a year, with h_m = max(h_e − (π_pre + (1 − π_pre)σ_x)·
  r_e·c_e', 0);
- initial access: r_i = min(X_i/T_i, h_i/w_i), with h_i = max(h_m − r_m·w_m, 0).

The operators on attacks can start n_w = O_a/c_o attacks a year, with c_o the operators' work of an
attack after lessons; here H_surge = funding/cost per expert-year while a surge runs. On attacks, damage
assessment takes at most its share of the analysis work waiting, φ_q = (N_q/T_q)·c_assess/((N_q/T_q)·
c_assess + n_w·c_plan): r_q = min(N_q/T_q, φ_q·C_a/c_assess). The analysts plan with the rest, so the
force starts n_s = min(n_w, max(C_a − r_q·c_assess, 0)/c_plan)·α_a·α_l·α_x attacks a year, with α_k the
share of a step's units that pool k lets pass (below).
- dX_i/dt = n_s·m − α_a·r_i and dN_i/dt = n_s − α_a·r_i/m_i: each attack starts with the m targets of its
  start;
- dX_m/dt = α_a·r_i − α_l·r_m and dX_p/dt = α_l·r_m − (π_pre + (1 − π_pre)σ_x)·α_x·r_e·m_p, and N_m and N_p
  move with them at the sizes m_i and m_m;
- dN_h/dt = π_pre·α_x·r_e − σ_x·λ·N_h, while an attack built in advance waits ready for its moment;
- dN_q/dt = n − r_q, with n = (1 − π_pre)σ_x·α_x·r_e + σ_x·λ·N_h the attacks made in a year. An attack
  built on demand is made when it is ready.
- The attacks made carry X_n = (1 − π_pre)σ_x·α_x·r_e·m_p + σ_x·λ·X_h targets a year. The targets hit,
  the value and its spread, the defenders' threat and the yearly assessment read X_n; the sanctions, the
  burns, the burned lessons and the tally read n.
- The attacks held ready and assessed also carry their independent outcomes, I_h and I_q, for the
  lessons, and the attacks held ready their targets weighted by correlation, X_h^ρ, for the plans. An
  attack whose effect the force finishes adds m_p/(1 + (m_p − 1)ρ_w) to I_h or I_q and
  m_p(1 + (m_p − 1)ρ_w) to X_h^ρ when it is held ready, at the ρ_w of that time. The assessment of an attack
  removes its share of X_q and I_q, and the use of an attack held ready removes its share of X_h^ρ.
- Each step moves in one part for each source of the capabilities that it needs (below), and each part
  moves with the stock that it draws on. So an empty source holds back only its part of the step.
- At rest each stock holds what passes in a year times its time: X_i = n·m·T_i, X_m = n·m·T_m,
  X_p = n·m·T_e, N_h = π_pre·n/λ and N_q = n·T_q, with m targets for each attack and n·T_i, n·T_m and
  n·T_e attacks in the first three stocks. Every stock starts there, so every run without a surge starts
  at rest. With n_s = n_w at rest, the operators on attacks use all of their hours, and initial access is
  the step that the hours limit.
- **A neutral backlog of initial access.** While the operators limit the starts, the pace that the hours
  allow at initial access equals the targets that start, whatever X_i holds. So a backlog of initial
  access above its rest level is also at rest: a neutral direction on one side of the kink of the step.
  When AI shortens T_i while the operators limit the starts, the backlog does not drain, and it drains
  once the analysts limit the starts. The targets in build count the backlog. No decision result depends
  on it.
- The waiting factor is an identity of the stock held ready: at rest, the force builds lost access
  again in place at δ_P·N_h a year and keeps it up at u·N_h, so for each use the held stages cost
  1 + π_pre(δ_P + u)/λ times their build.

**Learning: the lessons of effects.**
- dτ/dt = r·r_q·I_q/N_q − δ_τ·τ: lessons come as assessments end, from the independent outcomes that
  the attacks assessed carry, and r, the reliability of the assessment, is the share of what one outcome
  teaches that the damage assessment keeps.
- An attack of m targets has m_e = m/(1 + (m − 1)ρ_w) independent outcomes, at the m and ρ_w of its build.
- δ_τ = δ₀·(1 − b + b·n/n₀). The share b of today's loss of lessons comes from exposed attacks.
- The evidence weight is k = 1 − 1/(1 + (τ/τ_h)^h) (Hill; h = 1 is the Bayesian weight of
  evidence against a prior of strength τ_h), or k = 1 − 2^(−τ/τ_h) (exponential form).
- The gain since today is Δk = (k − k₀)/(1 − k₀), written without the division.

**Capability pools** (the template `Pool`). A capability is a flaw that the defenders do not know, with
the tools that use it, and it burns as a whole. Each step has a pool k: access (a) and movement in the
network (l) serve both missions, the effect (x) serves attacks only, collection (c) surveillance only.
- **One-days.** A need of a step takes no capability when a known flaw or the target's own functions
  serve it, on a target that has not fixed the flaw by its use: o_k = K_k·[ρ_k + (1 − ρ_k)·e^(−f·v_k·T)],
  with the share K_k of needs that known flaws can serve, the pace v_k of fixes at the step (industrial
  systems 0.2, the inside of a network 0.5) and T the time of the step.
- **Needs.** An attack of x targets has u(x) = 1 + μ·max(x − 1, 0) kinds of target system, μ the chance
  that a further target is a new kind, and needs one capability for each kind at each step. Each step
  counts the attacks in its own stock: u(m_i)/m_i for each target at initial access, u(m_m)/m_m for each
  target at movement, and u(m_p) for each attack at the effect. An access of surveillance needs one at
  initial access, one at movement and one to collect. The zero-days that the missions need in a year are
  a_k for attacks that wait (initial access: r_i·(u(m_i)/m_i)(1 − o_a); movement:
  r_m·(u(m_m)/m_m)(1 − o_l); the effect: π_pre·r_e·u(m_p)·(1 − o_x)), a_o for attacks made at once
  ((1 − π_pre)σ_x·r_e·u(m_p)·(1 − o_x), the effect only) and z_k for surveillance (initial access:
  r_si·(1 − o_a); movement and collection: r_d·(1 − o_k)).
- **Sources.** Each zero-day that an attack needs is a capability that surveillance uses (from U_k), one
  kept from an earlier attack (from R_k), or a never-used one (from F_k). Each zero-day that surveillance
  needs is one that it already uses, one kept from an attack that only attacks used (from R_k^a), or a
  never-used one. A capability in use serves a need as one independent try: with y₂ = Y₀·(p₂₀/(p₂₀ +
  p₃₀))·U_k/U_k0 and y₃ = Y₀·(p₃₀/(p₂₀ + p₃₀))·R_k/R_k0, the shares are p₂ = (1 − e^(−y))·y₂/y,
  p₃ = (1 − e^(−y))·y₃/y and p₄ = e^(−y), y = y₂ + y₃ and Y₀ = −ln(1 − p₂₀ − p₃₀). Today's shares p₂₀ and
  p₃₀ are inputs: 0.1 and 0.05 for attacks, 0.95 and 0.0001 for surveillance (on U + C^s + R^s and on R^a).
  A source that a step does not have is zero. So no share passes one, and a share falls to zero with its
  stock. Only the never-used source can run dry while its share stays: the next rule holds it back.
- **Supply.** The missions ask pool k for D_k = (a + a_o)·p₄ + z·p₄^s never-used capabilities a year. The
  pool serves the share α_k* = min(1, F_k/(D_k·t_s)) of these asks, with t_s the supply time (0.02 years,
  about a week of asks). So a step of attacks lets pass the share α_k = 1 − (1 − o_k)·p₄·(1 − α_k*) of its
  units, and a step of surveillance α_k^s = 1 − (1 − o_k)·p₄^s·(1 − α_k*). The force starts only the
  attacks that the pools can equip, and surveillance only the accesses (the factors α of n_s and b_r).
  Today α* = 1: each pool holds t_R/t_s = 50 times the stock at which it starts to hold back the asks.
- **Parts.** A step moves in one part for each source: the part of its units p_j·(1 − o_k) moves with
  its capabilities from the stock that the source draws on, and the part o_k (with surveillance's own
  capabilities, which move nothing) moves alone. The part that needs a never-used capability moves at
  α_k* times its pace. Deployment draws on the movement and the collection pools at once, so it moves in
  six parts.
- **Flows of pool k** (attacks' draws a, a_o, surveillance's z, at the shares p above):
  - dF_k/dt = P_k − α_k*·[(a + a_o)·p₄ + z·p₄^s] − δ_c·F_k;
  - dU_k/dt = α_k*·z·p₄^s − a·p₂ − δ_u·U_k;
  - dC_k^s/dt = a·(p₂ + p₃·R^s/R) − (h + δ_u)·C_k^s and
    dC_k^a/dt = a·(α_k*·p₄ + p₃·R^a/R) − (h + δ_u)·C_k^a;
  - dR_k^s/dt = (1 − χ)·h·C_k^s + z·p₃^s − a·p₃·R^s/R − δ_u·R_k^s;
  - dR_k^a/dt = (1 − χ)·h·C_k^a + (1 − χ)·α_k*·a_o·p₄ − z·p₃^s − a·p₃·R^a/R − χ·a_o·p₃ − δ_c·R_k^a;
  - dB_k/dt = χ·h·(C_k^s + C_k^a) + χ·a_o·(p₃ + α_k*·p₄).
- **Burns.** In a year the force makes the share h of the attacks that hold capabilities of a pool:
  h = n/(N_m + N_p + N_h) for access, n/(N_p + N_h) for movement and σ_x·λ for the effect. That share of
  the held capabilities leaves the held stocks: the exposure χ burns them, and the rest are kept for
  reuse. An attack made at once burns or keeps its effect's capabilities as it takes them.
- Where surveillance also uses a burned capability, the defenders find a share φ_f of the accesses that
  run on it. So surveillance loses β_k = φ_f·χ·h·C_k^s·(1 − o_k)/(U_k + C_k^s + R_k^s) of its accesses on
  pool k in a year.
- **Three ways to lose a flaw.** Others find a flaw that the force holds on their own and disclose it
  (the rate δ₁), a patch or code change made for another reason closes it (δ₂), or its systems leave
  service or stop mattering (δ₃). AI helps the defenders find and close flaws in every run: discovery and
  patching grow by the factor 1 + γ_d·g₁ (γ_d = 2, so three times today's at the end), and the third route
  does not change. A flaw that the force holds unused, never used or kept for attacks only (F and R^a),
  is lost at δ_c = (δ₁ + δ₂)(1 + γ_d·g₁) + δ₃: 0.145 a year today, a life of 6.9 years. A flaw that the
  force uses on targets (U, C^s, C^a, and R^s, which surveillance runs) can also be seen at work, so
  others find it at δ₁ᵤ, and it is lost at
  δ_u = (δ₁ᵤ + δ₂)(1 + γ_d·g₁) + δ₃: 1.17 a year today, from the 312 days that zero-days used in attacks
  lasted. Today δ₁ = 0.057, δ₁ᵤ = 1.08 and δ₂ = δ₃ = 0.044 a year.
- **Research to need.** Each pool asks the researchers for what the missions ask from it, for what it
  loses and for what restores its reserve of t_R years of asks:
  P_k* = max(D_k + δ_c·F_k + (t_R·D_k − F_k)/t_R, 0) a year. The researchers can find R·Y capabilities a
  year, Y = Y₀·γ_R^(g₁) (γ_R = 10 at the end of AI progress), and they find no more than the pools ask:
  P_k = P_k*·min(1, R·Y/Σ_j P_j*). So while they keep up, each never-used stock stays near t_R·D_k.
- **Today is a rest point**, in closed form, with x = h₀ and a = a_k0 (the effect: a_o = a_o0), the
  rate δ_u0 of a flaw in use and δ_c0 of a stockpiled flaw:
  - C = a/(x + δ_u0); the kept stock's net gain is N = (1 − χ)(x·C + a_o·p₄) − (a + χ·a_o)·p₃, and R^s
    is lost at δ_u0 while R^a is lost at δ_c0, so with Δ = δ_u0 − δ_c0, Q = (1 − χ)·x·a·p₂/(x + δ_u0) +
    z·p₃^s and B = a·p₃·(1 − (1 − χ)x/(x + δ_u0)), the shared share ϱ of R solves
    B·Δ·ϱ² + b·ϱ − Q·δ_c0 = 0 with b = δ_u0·N + B·δ_c0 − Q·Δ: ϱ = 2Q·δ_c0/(b + √(b² + 4B·Δ·Q·δ_c0)), and
    R = N/(δ_c0 + ϱ·Δ). With equal rates this is ϱ = Q/(N + B) and R = N/δ_c0;
  - R^s = ϱ·R, C^s = a·(p₂ + p₃·ϱ)/(x + δ_u0), U = (z·p₄^s − a·p₂)/δ_u0 and F = t_R·((a + a_o)p₄ + z·p₄^s),
    t_R years of today's asks (1 year); Y₀ = Σ_k (D_k0 + δ_c0·F_k0)/R.
  - Checks before a run reject today's shares that no rest point can keep: U, R and R^a must be positive.

**Defenders: attention, fixes and lasting gains.**
- Attention answers the whole threat flow, of which the force's attacks are a share f today, counted in
  targets: T = 1 − f + f·X_n/(n₀·m₀) is the threat flow as a multiple of today's.
  dA/dt = δ_A·(A*(T) − A), with A*(T) = A₀·c·T/(T + c − 1): today's attention A₀ at T = 1, rising towards
  the cap c·A₀. So attention grows less than the threat flow and never reaches the cap, and today's
  attention is a rest point.
- Fixes: a known flaw works only on a target that has not fixed it by its use (the one-days of the
  pools). An exposed attack's capabilities burn, so the force does not reuse what it exposed. In every
  run AI helps the defenders find and close the force's flaws (the three ways to lose a flaw, above).
- Lasting gains: H(t) = h·t + a_H·g₁, a yearly trend and the defenders' AI. Both are 0 unless the
  "Defender hardening" group sets them, so every run without them starts at rest.

**Success per target.** logit p = logit p₀ + (logit p∞ − logit p₀)·Δk − (A − A₀) − H. So p stays in
(0, 1).

**Value and cost of attacks** (SEV per year).
- Targets hit are X = X_n·p, and V = κ·v·X/(1 + X/X_s)·(1 + γ_v)^Δk·(1 + ξ·[D = formed]). Here κ is
  the value scale (1), X_s the saturation and ξ the doctrine feedback (0 by default). The factor
  (1 + γ_v)^Δk is 1 today and 1 + γ_v with every lesson learned, and it stays positive when the
  lessons fall below today's.
- Risk: V_R = V/(1 + (γ_R/2)·CV²). CV² = ((1 − p)/p)·(1 + (m − 1)ρ_w)/(X_n·1yr + 1) + (1 − p)²σ_C²
  + (1 − p)/p/(τ + τ_h + 1) is the relative variance of a year's value, with σ_C the common factor of
  the doctrine test.
- Costs: C = n·q·S·(1 + ψ·n·q) + v_ℓ·Z_b, for sanctions plus the accesses of surveillance that the
  defenders find through burned shared capabilities, Z_b = β_a·(G_h + G) + β_l·G a year, each worth what
  one access gives in its life today, v_ℓ = V_s0/(G₀·δ_s).

**Surveillance: its chain and its value.** Surveillance has O_s = (1 − s)·O' operators, the analysts C_s
and the collection specialists Z.
- The work w_s to gain one access and deploy its implant is the access work of an attack, so it moves
  with AI as the access stage's cost share u_a does: w_s = w_s0·u_a(g₁)/u_a(0). Initial access takes
  w_si = ψ_i·w_s and deployment w_d = (1 − ψ_i)·w_s. Only the share φ_d = 1/(1 + (δ_s + β_a)·T_m) of the
  accesses gained lives until its deployment, so each start costs its initial access and its expected
  deployment, and the operators can start b = O_s/(w_si + φ_d·w_d) accesses a year.
- The analysts plan each new access at the work w_p. Its AI moves with the planning stage's AI for each
  target, b_plan, as far as the share θ, and with its AI for the attack, a_plan, for the rest:
  w_p = w_p0·(u(b_plan)/u(b_plan,0))^θ·(u(a_plan)/u(a_plan,0))^(1 − θ), θ = 1 by default and 0 in the option
  "Slow planning of surveillance". So surveillance starts b_r = min(b, C_s/w_p)·α_a^s·α_l^s·α_c^s, the
  accesses that its operators can start, its analysts plan and its pools can equip.
- The operators deploy first: r_d = min(G_h/T_m, O_s/w_d). They gain new access with the hours left:
  r_si = min(G_i/T_i, max(O_s − r_d·w_d, 0)/w_si).
- dG_i/dt = b_r − α_a^s·r_si, dG_h/dt = α_a^s·r_si − α_l^s·α_c^s·r_d − (δ_s + β_a)·G_h and
  dG/dt = α_l^s·α_c^s·r_d − (δ_s + β_a + β_l)·G, where δ_s is the rate at which surveillance loses accesses
  to the defenders, to patches and to changes. Collection does not drain the implants.
- The collection specialists process the take first: r_Q = min(Q/T_Q, Z/w_c), with T_Q the processing
  time (0.1 years) and w_c the specialists for each access-year a year, which AI on the slower path
  lowers: w_c = w_c0·r_A/r_A0, r_A = (1 − a_A) + a_A(σ_s/P + κ/e). They run implants with the hours left:
  they can run K = max(Z − r_Q·w_c, 0)/w_r implants, w_r = w_r0·r(g₁)/r(0), with r the cost share of
  running an implant and AI doing a_r = a_r0 + (a_r∞ − a_r0)·g₁ of it.
- The implants run are C = G·K/(G + K): fewer than G and than K, and at least half the smaller. They add
  one access-year of take a year each: dQ/dt = C − r_Q.
- V_s = V_s0·(r_Q/r_Q0)^ε·e^(−β_s(A − A₀ + H)), with V_s0 = L_e SEV a year: one SEV per surveillance
  expert today, by definition of the SEV. The return of an operator on surveillance is ρ_s = V_s/O_s,
  20 SEV per person-year today at the defaults. Here ε is the returns scale and β_s the sensitivity to
  alertness.
- **Today is a rest point**, in order along the chain: b₀ = δ_s·G₀ with G₀ today's accesses;
  G_h0 = b₀/(1/T_m0 + δ_s + β_a0); r_d0 = G_h0/T_m0; G_0' = r_d0/(δ_s + β_a0 + β_l0); r_Q0 = u₀·G_0',
  K₀ = G_0'·u₀/(1 − u₀) and Q₀ = r_Q0·T_Q. The works follow from today's people:
  w_s0 = O_s0/(ψ_i·b₀ + (1 − ψ_i)·r_d0), because only the accesses deployed take the work of deployment, so
  today's operators use all of their hours; w_p0 = N_s0/b₀, w_c0 = Z_p0/r_Q0 and w_r0 = Z_r0/K₀. The
  defenders' finds through burned shared capabilities keep G_h0 + G_0' a little below G₀.

**Funding.**
- The assessed return of an operator on attacks is ρ̂ = (V_R·e^(e + B) − C)/(s·O' + H_surge) + φ·Λ, with
  the yearly error e and the bias B = b∞·g₁ of the assessment, 0 by default. The rule reads the gap
  (ρ̂ − ρ_s)/ρ_s, as a share of the current return ρ_s of an operator on surveillance. Today ρ_s = ρ_s0, so
  the calibration of v does not change, and as AI raises both returns, the gap stays a relative
  difference, as the evidence of the budget response measures it.
- Λ = [∂(V − C)/∂τ]/(i + δ_τ)·r·m_e·ω_N/c_o is the value of the lessons of one operator-year, with i
  the discount rate and ω_N = ∂n/∂n_w (1 where the analysts plan every attack that the operators can
  start). The derivative is written out for each learning form, with A held and the stocks at rest, in
  risk-neutral terms. More lessons of effects cut the stages that only attacks do, so the slope of the
  attacks started is n_w·γ_c·c_e/c_o·ω_N, with c_e the operators' work of those stages before lessons.
- Where the analysts cannot plan every attack, lessons also cut the analysts' work of planning and
  assessment, P_b and Q_b before lessons, which lets them plan more attacks. The model blends the two
  limits by the share of the attacks wanted that start, ω_N = min(n_s/n_w, 1): the slope of the attacks
  is n_w·γ_c·c_e/c_o·ω_N + (1 − ω_N)·n_s·γ_c·(P_b + Q_b)/(P + Q). The exact slope has a kink where the
  operators' and the analysts' limits meet, and a jump there makes the funding rule chatter, so the blend
  is continuous. It is exact where the operators limit the attacks, and an approximation elsewhere; it
  matters only with foresight (φ > 0).
- Two forms:
  - (I2, default) Logistic target, centered on today's split of the operators: ds/dt = (s* − s)/T_b,
    with s* = s_min + (s_max − s_min)/(1 + e^(−β·(ρ̂ − ρ_s)/ρ_s − c₀)) and
    c₀ = ln(max(s₀' − s_min, 0.001)/max(s_max − s₀', 0.001)). Equal returns give s* = s₀', so any
    steepness β > 0 keeps today's split; the ceiling s_max = 0.9 lies above today's 0.575.
  - (I1) Proportional: ds/dt = κ_f·(s − s_min)(s_max − s)·(ρ̂ − ρ_s)/ρ_s, with each factor of the room
    clipped to [0, 1].
- φ = 0 funds on current results; φ = 1 counts what operations teach.

**Calibration by revealed preference.** v solves ρ̂(t = 0) = ρ_s(0), equal returns today, for both
forms of the rule:
- with foresight, ρ̂ includes φ·Λ₀. Λ₀ is linear in v, so v stays in closed form:
  v = [O_a0·ρ_s0 + C₀ + φ·K₀·W₀] / [X₀R₀/(1 + X₀/X_s) + φ·B₀·W₀]. Here W₀ = δ₀τ₀·k′₀/(i + δ₀)
  is the discounted gain that today's attacks teach in a year, B₀ the growth of today's counted hits
  with the gain, K₀ the growth of today's costs and R₀ today's risk factor, all at κ = 1. B₀ and K₀
  count the share of today's work in the stages that only attacks do. Today the analysts plan every
  attack, so ω_N = 1;
- τ₀ and A₀ start at their rest values.

So the run without AI stays at today's split, and no value is tuned to an outcome. The return of an
operator on surveillance today is that of the operators who gain access and deploy implants, so the
value of one effect is set against it.

**Plans.** The planners test plans of four lengths T ∈ {1 day, 1 week, 1 month, 1 quarter} (the
template `Plan`) by one rule. A plan of length T counts on the share f of the force that serves one
objective: the attacks held ready and those that the force finishes in the plan's time and that the
pools can equip, n_T = α_x·r_e·T. So it counts on
- N_T = max(f·(N_h + n_T), 1) attacks, with X_T = max(f·(X_h + n_T·m_p), 1) targets in all and
  m_T = max((X_h + n_T·m_p)/(N_h + n_T), 1) targets for each attack on average. An attack held ready keeps
  the targets and the correlation of its build, and an attack finished now has m_p targets. At rest
  N_h = n·π_pre(L)/λ;
- a planned share p(1 + e) of targets hit. Here p is the mean share, which the planners learn from pooled
  outcomes, and e is their forecast error, with σ_e² = σ_floor² + (1 − p)/(p·(τ + 1)): a floor that
  lessons do not remove and the sampling error of p from the τ assessed outcomes, not from the prior.

The plan is met when the share hit reaches (1 − η) of the planned share, where η is the tolerance.
Without a shared failure the share hit is p(1 + ε), and ε has the relative variance s_L² + s_C², with
- the luck of each target and of the targets of one attack, s_L² = ((1 − p)/p)·max(X_T^ρ, X_T)/X_T², from
  the plan's targets weighted by the correlation of their attacks,
  X_T^ρ = f·(X_h^ρ + n_T·m_p·(1 + (m_p − 1)ρ_w));
- the common factor of the one defender that all of the plan's attacks face, s_C² = (1 − p)²σ_C², with
  σ_C in log-odds around the mean share p.

**Shared failures.** A capability that the plan's attacks share can fail for all of the attacks that use
it at once: at the start, and while the plan runs as the defenders find it. Each kind of target system
needs its own such capability, and each fails on its own with today's chance j_T = 1 − (1 − j₀)·e^(−r_f·T).
So the number of the plan's shared capabilities that fail is Poisson, with the mean
J_T = (u(m_T)/u₀)·(−ln(1 − j_T)); today u = u₀, and the chance of one failure or more is j_T. A failure
takes the attacks that depend on its capability: the share d = d₀·u₀/u(m_T) of the plan's effect, with d₀
today's share of a plan's effect that depends on one capability that its attacks share (0.5). So k
failures take d_k = min(k·d, 1). As AI widens attacks to more targets, d falls, to about 0.13 at the end
of AI progress, and J_T grows in proportion: the expected share lost, J_T·d = d₀·(−ln(1 − j_T)) before the
cap, stays the same, but it comes in smaller parts.

After k failures, only the luck of the attacks that are left counts: S_k² = (1 − d_k)·s_L² +
(1 − d_k)²·s_C² + (1 − η)²σ_e². With Φ the standard normal distribution function, the chance to meet the
plan after k failures is H_k = Φ((η − d_k)/S_k), and

Π_T = e^(−J_T)·(H_0 + J_T·H_1 + J_T²/2·H_2 + J_T³/6·H_3) + P(K ≥ 4)·H_4,

with H_4 for four failures or more, taken at their mean number: K₄ = E[K | K ≥ 4] = J_T·P(K ≥ 3)/P(K ≥ 4)
(4 when P(K ≥ 4) is below 10⁻¹²), d_4 = min(K₄·d, 1) and no less than min(4d, 1), and while K₄·d < 1, S_4² gains
d²·Var(K | K ≥ 4), with E[K² | K ≥ 4] = (J_T²·P(K ≥ 2) + J_T·P(K ≥ 3))/P(K ≥ 4). This is exact up to the
normal approximation of the share hit and of the tail, which matters only when a plan's attacks reach
many kinds of target system. The
two-sided test of the earlier model is an option: H_k = Φ((d_k + η)/S_k) − Φ((d_k − η)/S_k), with the
same spread for the upper bound. The two-sided chance never exceeds the shortfall chance.
- More targets shrink only s_L², so Π_T ≤ e^(−J_T)·Φ(η/S_∞) + 1 − e^(−J_T), with
  S_∞² = (1 − p)²σ_C² + (1 − η)²σ_e², however many attacks a plan has.
- A longer plan has more attacks and so less luck, but a larger J_T. The best length is a result.
- With d < η, a plan that loses one capability still meets its plan more often than not. Today
  d = 0.5 > η = 0.25, so one failure leaves a chance of about 0.1. With d = 0, a failure would change
  nothing.

**Doctrine.**
- A review passes when the best plan passes: max_T Π_T ≥ Π*. It adds one to P and sets M to 0; a
  missed review adds one to M and sets P to 0. Reviews come yearly in peace and every quarter in war.
- D becomes "formed" when P reaches P_d, and records the length of the best plan then. It becomes
  "lapsed" when M reaches M_d. It can form again. The output `doctrine_counts` is 1 while D is "formed"
  and 0 otherwise, so the mean over a study's samples is the chance that plans count on cyber attacks.
- One use of an attack is not doctrine: doctrine needs reviews that pass again and again.
- With ξ = 0, D only records doctrine, so it imposes no threshold, and Π* changes no other value.

**War.** As an option, the country goes to war at t_w (2026 in the wartime run), from today's
peacetime posture: every stock starts at its peacetime rest. From then the moment to use an attack held
ready comes at λ_w, an attack must land within W_w of the decision, and the planners review every
quarter. So the stock held ready drains at once; while it drains, the operators' hours go to execution
first. Damage assessment takes the analysts' hours only up to its share of the work waiting, so they
still plan new attacks while the queue of assessments grows.

**Noise (stochastic version).** At each yearly assessment the error is
e = clip(σ_A·z, −4, 4), with z ~ N(0, 1) truncated to ±4 and
σ_A² = ((1 − p)/p)·(1 + (m − 1)ρ_w)/(X_n·1yr + 1) + σ_bda²/(r·r_q·(I_q/N_q)·1yr + 1) + σ_c²,
with X_n the targets of the attacks made in a year and r·r_q·I_q/N_q the lessons gained in a year.
The last term is a common error that does not shrink with the number of outcomes, so the spread never
falls below σ_c. The central run takes z = 0, so it is the deterministic model; a Monte Carlo study
draws z each year from the event's seeded stream.

### 4. Timing

The continuous flows move the 47 stocks between moments. Events due at the same time go in the
order of the file, and each reads the values from before its own step:
1. the surge's start and end;
2. the leaders' assessment (the noise);
3. the start of a war, then the planners' review, then the forming or the lapse of doctrine.

So a surge that starts at a review counts in that review.

### 5. Functional forms for robustness

| Part | Forms | Input |
|---|---|---|
| Learning curve | Hill with shape h ∈ [1, 3]; exponential | `curve_shape`, `exponential_curve` |
| Loss of lessons | constant; growing with exposed attacks | `burn_share` |
| Funding rule | logistic target; proportional; both on the return gap relative to surveillance's current return | `proportional` |
| Funding horizon | current results; results and lessons | `foresight` |
| Value function | risk-neutral; risk-averse (mean–variance) | `risk_aversion` |
| Doctrine | indicator only; feedback on value | `doctrine_value` |
| Plan test | shortfall only; two-sided | `two_sided` |
| Planned share | the mean share that pooled outcomes teach (convention) | — |
| Shared failures of a plan | one capability for each kind of target system, each failing on its own: a Poisson count (convention) | — |
| Pace of a step | the lower of its pace by time and the pace that its hours left allow (convention) | — |
| People's hours | to the operations farthest along first (convention) | — |
| Targets of an attack | carried with the attack from its start, with the kinds and the correlation of its effect (convention) | — |
| Implants run | the implants and the collection specialists' reach in series (convention) | — |
| Analysts' staffing | by the value of the work; by the work waiting; fixed at today's split | "Analysts' staffing" group |
| Damage assessment on attacks | at most its share of the analysis work waiting (convention) | — |
| Workforce | fixed groups; idle operators retrain as analysts | "Workforce" group |
| Planning of a new access | AI's help for each target (θ = 1), for the attack (θ = 0), or a mix in log terms | `plan_target_weight` |
| Sources of a zero-day | independent tries on the capabilities in use (convention) | the four source shares |
| Supply of never-used capabilities | smooth below a supply time of asks; the missions start only what the pools can equip (convention) | `supply_time` |
| Research | to each pool's need, with a reserve of t_R years of the current asks (convention) | `reserve_time` |
| Loss of a flaw | three routes, faster in use; AI speeds discovery and patching in every run | the loss rates, `close_gain` |
| Defender attention | saturating in the threat flow, counted in targets (convention) | `attention_cap` |
| Lasting defender gains | none; a yearly trend; the defenders' AI | "Defender hardening" group |
| Work of access | Wright's law in the lessons of access | `access_learning` |
| Tempo | peace; war from its start | "Tempo" group |

### 6. Parameters

A range is a range that a reader can explore, not a measured interval. "Assumed" values are the
scenario's own, with an unreviewed assumption record. The claims verify the facts that they quote,
not the values.

| Input | Default | Range | Basis |
|---|---|---|---|
| `leadership.experts` | 40,535 people | 5,000–100,000 | NSA ~39,000 less ~2,000 cut in 2025 (E-SC45-NSA-WORKFORCE) + 3,535 attack posts (E-SC45-CMF-SIZE) |
| `leadership.share_now` | 0.087 | 0.07–0.16 | 3,535/40,535, staff 10.5:1; range from staff and money ratios (E-SC45-NSA-WORKFORCE, E-SC45-CMF-SIZE, E-SC45-CYBERCOM-BUDGET) |
| `leadership.share_floor`, `share_ceiling` | 0.03, 0.9 | 0.005–0.06, 0.6–0.95 | Assumed; shares of the operators, of whom about 58% are on attacks today |
| `researchers.share` ψ_R | 0.03 | 0.01–0.1 | Assumed; no count is public |
| `researchers.reserve_time` t_R | 1 yr | 0.1–5 | Assumed |
| `researchers.supply_time` t_s | 0.02 yr | 0.005–0.25 | Assumed; about a week of asks |
| `researchers.gain_end` γ_R | 10 | 1–100 | Assumed; AI found and exploited zero-days in every major operating system and browser (E-SC45-MYTHOS-FLAWS); automated systems found 86% of synthetic flaws (E-SC45-AIXCC) |
| `analysts.load_now` ℓ | 0.9 | 0.5–1 | Assumed |
| `analysts.adjust_time` T_N | 1 yr | 0.25–5 | Assumed |
| `analysts.by_value`, `fixed_split` | true, false (option "Work waiting": `by_value` false; "Fixed split": `fixed_split` true) | — | Rule choice (option); no source measures how leaders staff the analysts |
| `analysts.priority_steepness` β_N | 2 | 0–10 | Assumed |
| `operators.retrains`, `retrain_time` T_O, `retrain_efficiency` φ_r | false (Idle operators retrain: true), 3 yr, 0.5 | —, 0.5–20 yr, 0–1 | Assumed; no source measures them |
| `surveillance_program.analysis_share` ψ_A, `plan_share` ψ_P | 0.5, 0.1 | 0.2–0.8, 0.02–0.3 | Assumed; they set the planners and the collection specialists who process the take; the implant program used only part of its implants with its staff (E-SC45-GENIE-2011, unverified) |
| `surveillance_program.analysis_ai_now` → `analysis_ai_end` a_A | 0.1 → 0.6 (payload path) | 0–0.5, 0–0.9 | Assumed; the collection specialists' processing; AI also sorted the stolen data of one espionage campaign (E-SC45-AI-CAMPAIGN) |
| `surveillance_program.process_time` T_Q | 0.1 yr | 0.02–1 | Assumed; no time is public |
| `surveillance_program.plan_target_weight` θ | 1 (Slow planning of surveillance 0) | 0–1 | Assumed; no source measures the planning work of an access |
| `surveillance_program.find_share` φ_f | 0.02 | 0–0.3 | Assumed |
| `effects_program.spy_source`, `reuse_source` p₂₀, p₃₀ (attacks) | 0.1, 0.05 | 0–0.5, 0–0.15 | Assumed; no count is public |
| `surveillance_program.own_source`, `attack_source` p₂₀, p₃₀ (surveillance) | 0.95, 0.0001 | 0.5–0.995, 0–0.0005 | Assumed; attacks keep few capabilities unburned against surveillance's needs |
| `defenders.discovery_now` δ₁, `patch_now` δ₂, `irrelevance_now` δ₃ | 0.057, 0.044, 0.044 /yr | 0–0.145, 0–0.1, 0–0.1 | Private zero-days live 6.9 years on average, 0.145 a year by every route (E-SC45-ZERODAY-LIFE; E-SC45-ZD-LONGEVITY, partial); others rediscover 5.7% a year (E-SC45-ZD-COLLISION, partial); patches and retirement are other routes (E-SC45-ZD-LIFE-STATUS, partial); the even split of the rest is assumed |
| `defenders.use_discovery_now` δ₁ᵤ | 1.08 /yr | 0.057–2 | Zero-days used in attacks lasted about 312 days before their disclosure, 1.17 a year by every route (E-SC45-ZD-IN-USE-LIFE, partial); an upper bracket for a careful force |
| `defenders.close_gain` γ_d | 2 | 0–5 | Assumed; in every run; AI systems found 86% of synthetic flaws and patched 68% of those (E-SC45-AIXCC) |
| `effects_program.concentration_now` d₀ | 0.5 | 0.2–0.9 | Assumed, for today's plan of one kind of target system; a tool rebuilt from the same source code (E-SC45-INDUSTROYER2); variants of patched zero-days within 12 months (E-SC45-ZERODAY-VARIANTS) |
| `effects_program.diversity` μ | 0.1 | 0–1 | Assumed |
| `<pool>.known` K_k, `patch_pace` v_k | 0.8 (movement and collection 0.9); 1 (movement 0.5, effect 0.2, collection 0) | 0–0.99, 0–2 | Assumed; half of known-exploited flaws fixed in about six months (E-SC45-KEV-FIX, partial); 884 new exploited flaws in 2025 (E-SC45-KEV-2025); fixes slowed as flaws grew (E-SC45-DBIR-SATURATION) |
| `leadership.adjust_time` | 3 yr | 1–6 | Assumed; budgets start more than two years before execution (E-SC45-PPBE) |
| `leadership.steepness` | 2 | 0.5–10 | Assumed; 10 points of a 100-point score move budgets 4–5% (E-SC45-PART-BUDGET, partial), mapped to 0.8–4 |
| `leadership.proportional_rate` | 0.5 /yr | 0.1–2 | Assumed |
| `leadership.foresight` | 0 | 0–1 | Rule choice (option) |
| `leadership.discount_rate` | 3%/yr | 2–10% | Assumed |
| `leadership.surge_funding` | 0 (0.25 USD2025_bn/yr in the 2025 surge) | 0–2 | E-SC45-SURGE-2025 |
| `leadership.expert_cost` | 0.42 USD2025_m/person-yr | 0.25–0.6 | Assumed (Cyber Command resources over the Cyber Mission Force) |
| `ai_tools.progress_time` | 5 yr (options 4, 12) | 2–20 | Assumed |
| `ai_tools.reversal_depth`, `reversal_start` | 0, 12 yr | 0–1, 1–24 | Assumed (hysteresis test) |
| `ai_tools.payload_time` T_P | 10 yr | 2–30 | Assumed; the most complex intrusions and attacks on industrial systems stay mostly manual |
| `planning_stage` W, w, a₀ → a∞ | 1, 0.5 py; 0 → 0.2 (payload path) | 0.05–10, 0–10 py | Assumed; approval of one operation took a series of top-level meetings (E-SC45-GLOWING-SYMPHONY) |
| `planning_stage` b₀ → b∞ (`target_ai_now`, `target_ai_end`) | 0.2 → 0.75 (access path); options 0.6, 0.9 | 0–0.9 | Assumed; transfer from kinetic targeting, where AI gains in target output mix AI with workflow and policy |
| `access_stage` W, w, a₀ → a∞, T₀ → T∞ | 0.3, 1.2 py; 0.25 → 0.87; 0.55 → 0.01 yr; held, builds | as above; 0.003–5 yr | Assumed; an AI model took over a 32-step range of about 20 expert-hours in 3 of 10 tries (E-SC45-AISI-RANGE); exploits for known flaws at about USD 3 (E-SC45-CVE-GENIE) |
| `effects_program.initial_share` ψ_i | 0.5 | 0.1–0.9 | Assumed; the share of access that initial access takes |
| `payload_stage` W, w, a₀ → a∞, T₀ → T∞ | 1.6, 0.4 py; 0.05 → 0.57 (payload path); 0.2 → 0.07 yr; held, builds | as above | Assumed; a core team of 5–10 for six months (E-SC45-STUXNET-TEAM); an industrial payload in as little as two months (E-SC45-SANDWORM-2022) |
| `execution_stage` W, w, a₀ → a∞ | 0.4, 0.1 py; 0.3 → 0.9 | as above | Assumed; an automated plan in many networks at once (E-SC45-POLAND-2025) |
| `assessment_stage` W, w, a₀ → a∞, T₀ → T∞ | 1, 0.7 py; 0 → 0.3 (payload path); 0.33 → 0.16 yr | as above | Assumed; assessments of one operation at 30 and 120 days (E-SC45-GLOWING-SYMPHONY); the end time is assumed |
| `assessment_stage` b₀ → b∞ (`target_ai_now`, `target_ai_end`) | 0.1 → 0.6 (payload path); options 0.5, 0.7 (access path) | 0–0.9 | Assumed; AI checks of hit targets in kinetic war; cyber has no mature method of damage assessment |
| `effects_program.supervision` σ_s, `parallel_now` P₀, `parallel_end` P∞ | 0.2, 1, 10 | 0.05–0.5, 1–3, 1–50 | Transfer: AI did 80–90% of an espionage campaign's tactical work on about 30 targets (E-SC45-AI-CAMPAIGN) |
| `effects_program.compute_now` κ₀, `compute_end` κ∞ | USD 0.1 m, 0.01 m per py of AI work | 0.02–2, 0.001–0.4 | Assumed, on about 2,000 working hours a year; one AI-built exploit chain of weeks of expert work cost under USD 2,000 of compute, about USD 0.05 m an expert-year (E-SC45-OP-MYTHOS-COST, partial); a range of about 20 expert-hours ran on a 100M-token budget and was solved in 3 of 10 tries (E-SC45-AISI-RANGE) |
| `effects_program.warning_time`, `waiting_sharpness` | 0.1 yr, 2 | 0.02–0.5, 1–4 | Assumed |
| `effects_program.access_decay`, `upkeep`, `use_rate` | 0.3, 0.2, 0.5 /yr | 0.1–1, 0.05–0.5, 0.1–2 | Assumed; footholds held ≥ 5 yr (E-VOLT-PREPOSITION) |
| `effects_program.cost_learning` γ_c | 0.3 | 0–0.6 | Assumed; it cuts the stages that only attacks do |
| `effects_program.access_learning` λ_a, `access_forget_rate` δ_a, `task_overlap` ω | 0.1, 0.2 /yr, 0.7 | 0–0.3, 0.05–0.5, 0.3–1 | 20% per doubling in industry and 70% task overlap between two aircraft models (E-SC45-BENKARD-LEARNING, unverified); private zero-days live 6.9 years (E-SC45-ZERODAY-LIFE) |
| `effects_program.exposure` χ | 0.25 | 0.02–0.99 | Assumed; no source gives it; a hidden attack keeps its capabilities, and 0.25 burns about 20 to 40 a year, a part of the 63–106 zero-days that defenders catch in use worldwide each year, none attributed to the United States (E-SC45-ZD-2024-COUNT, E-SC45-ZERODAY-2025, E-SC45-ZD-2023-ACTORS, E-SC45-ZD-2024-ACTORS, E-SC45-ZD-2025-ACTORS) |
| `tools_channel`, `infrastructure_channel`, `operators_channel`, `targeting_channel` q₀ → q∞ | 0.4 → 0.05, 0.3, 0.2, 0.2 | 0–0.9 | Assumed; an AI-written wiper gave no attribution, its infrastructure did (E-SC45-POLAND-2025) |
| `effects_program.targets_now`, `targets_end` | 1, 30 /op | 1–3, 1–100 | Assumed; 30+ farms at once (E-SC45-POLAND-2025); ~30 targets (E-SC45-AI-CAMPAIGN) |
| `effects_program.success_now`, `success_best` | 0.2, 0.7 | 0.05–0.4, 0.4–0.95 | Assumed; precedents of low intended effect (V-C01, E-SC45-STUXNET, E-SC45-POLAND-2025) |
| `effects_program.value_scale` | 1 | 0.25–4 | Departure from revealed preference |
| `effects_program.saturation` | 1,000 targets/yr | 100–10,000 | Assumed |
| `effects_program.value_learning` | 1 | 0–3 | Assumed |
| `effects_program.risk_aversion` | 0 | 0–4 | Form choice |
| `effects_program.assessment_reliability` r, `assessment_noise` σ_bda | 0.4, 0.8 | 0.2–0.6, 0.3–2 | Assumed; disputed assessment (E-SC45-CARTER-ISIS); claimed hit rate 80% against 41–60% audited (E-SC45-DESERT-STORM-BDA) |
| `effects_program.common_error` σ_c, `assessment_bias_change` b∞ | 0.3, 0 | 0–1, −0.5–0.5 | Assumed; one shared error across services (E-SC45-DESERT-STORM-BDA); an AI that made up credentials (E-SC45-AI-CAMPAIGN) |
| `effects_program.prior_strength` | 5,000 targets | 300–20,000 | Assumed: a few attacks teach little |
| `effects_program.curve_shape` | 1 | 1–3 | Bayesian weight at 1 (identity); assumed above |
| `effects_program.forget_rate`, `burn_share` | 0.3 /yr, 0 | 0.1–0.7, 0–0.8 | Assumed |
| `defenders.alert_now` A₀, `calm_rate` δ_A | 0.05, 2 /yr | 0–0.2, 1–3 | Assumed; exposed actors returned to their activity after about five months (E-SC45-APT1-RETURN); fast patching sets 0.1 and 1 /yr |
| `defenders.force_share` f, `attention_cap` c | 0.05, 6 | 0.01–0.3, 2–20 | Assumed; 884 new exploited flaws and 90 zero-days in 2025 (E-SC45-KEV-2025, E-SC45-ZERODAY-2025); fixes slowed as the flaws to fix grew (E-SC45-DBIR-SATURATION) |
| `defenders.hardening_rate` h, `ai_hardening` a_H | 0 (Slow hardening 0.05 /yr), 0 (Defenders' AI 0.5) | 0–0.15, 0–1.5 | Assumed; internal detection rose from 43% to 52% (E-SC45-INTERNAL-DETECTION) while dwell rose (E-SC45-ESPIONAGE-DWELL); AI found 86% and patched 68% of synthetic flaws (E-SC45-AIXCC, E-SC45-MYTHOS-FLAWS) |
| `defenders.within_now` ρ₀ | 0.85 | 0.5–1 | Assumed; three utilities lost power together in 2015 (V-C01) |
| `defenders.fix_rate` f, `residual` ρ_k | 1.5 /yr (fast patching 15), 0.25 | 0.2–30, 0.05–0.5 | Median of about six months for known-exploited flaws (E-SC45-KEV-FIX, partial); 92% fixed in three weeks for one famous flaw (E-SC45-PROXYLOGON-FIX) |
| `effects_program.tailoring_end` τ∞ | 0.8 | 0–1 | Assumed |
| `defenders.common_spread` σ_C | 0.3 (dispersed 0.13) | 0.1–0.46 | Assumed, the defenders' side only; drone campaign 0.27–0.46 a month (E-SC45-SHAHED-2026, partial), whose drones were one type of weapon, so it may hold a part from the attacker's side; drift of mass campaigns (E-SC45-COVEWARE-CAMPAIGNS) |
| `defenders.shared_failure` j₀, `failure_rate` r_f | 0.05, 0.6 /yr (dispersed 0.03, 0.24 /yr) | 0–0.3, 0–3 | Assumed; for the shared capability of each kind of target system, each failing on its own |
| `other_states.sanction_cost`, `escalation` | 10 SEV/op, 0 | 1–100, 0–0.01 yr/op | Assumed; 0.01 multiplies today's cost of an attributed attack by about 3.6, at about 260 attributed attacks a year |
| `surveillance_program.returns_scale` ε, `alert_sensitivity` β_s | 0.8, 0.3 | 0.5–1, 0–1 | Assumed |
| `surveillance_program.accesses_now` G₀ | 85,000 accesses | 20,000–300,000 | 85,000–100,000 implants deployed by 2014 (E-SC45-IMPLANT-COUNT); 68,975 in 2011 (E-SC45-GENIE-2011, unverified) |
| `surveillance_program.used_now` u₀ | 0.12 | 0.05–0.5 | 8,448 of 68,975 machines fully used in 2011 (E-SC45-GENIE-2011, unverified); people limit exploitation at scale (E-SC45-TURBINE) |
| `surveillance_program.build_share` φ_b | 0.05 | 0.02–0.15 | 1,870 staff of the implant program in 2011 (E-SC45-GENIE-2011, unverified) over about 37,000 experts |
| `surveillance_program.loss_rate` δ_s | 0.5 /yr (fast patching 1) | 0.1–2 | Assumed; espionage dwell of a median 122 days among found intrusions, one backdoor nearly 400 days (E-SC45-ESPIONAGE-DWELL) |
| `surveillance_program.run_ai_now` → `run_ai_end` a_r | 0.3 → 0.9 | 0–0.9, 0–0.95 | Automated control of implants since 2010 (E-SC45-TURBINE); AI did 80–90% of an espionage campaign (E-SC45-AI-CAMPAIGN) |
| `military_planners.tolerance`, `acceptance` | 0.25, 0.8 | 0.2–0.5, 0.75–0.95 | Assumed, inside ranges from the evidence: a chance of 75% to 95%, higher for effects on which other parts of an operation depend, and a shortfall of 20% to 50%; shortfall only, `two_sided` as an option |
| `military_planners.objective_share` f | 0.2 (dispersed 1) | 0.05–1 | Assumed |
| `military_planners.forecast_floor` σ_floor | 0.1 | 0.1–0.3 | Assumed; claimed hit rate 80% against 41–60% audited (E-SC45-DESERT-STORM-BDA) |
| `military_planners.passes_needed` P_d, `misses_needed` M_d | 3, 2 | 1–10, 1–6 | Assumed; a weapon lost its place within months (E-SC45-EXCALIBUR) |
| `military_planners.doctrine_value` | 0 | 0–1 | Assumed |
| `day_plan`, `week_plan`, `month_plan`, `quarter_plan` `.length` | 1, 7, 30, 91 days | 1–91 days | Assumed |
| `military_planners.war`, `war_start` t_w, `war_review_interval` | false (Wartime true), 0, 0.25 yr | 0–24, 0.1–1 yr | Assumed |
| `effects_program.war_use_rate` λ_w, `war_warning_time` W_w | 12 /yr, 0.02 yr | 2–52, 0.005–0.1 | Assumed; Russia massed its attacks at the war's outset and spent its first stockpiles within weeks (E-SC45-WARTIME-TEMPO) |

Which results each parameter drives is the subject of the sensitivity analysis (Morris screening, then
Sobol indices, in `napkin.dynamics`).

### 7. Calibration notes

The results on the AI paths, in war and in the options are refreshed with the publication of the
rebuilt model; see [results/brief.md](results/brief.md). The notes below give today's state, which the
inputs set.

- **Today's people.** At the defaults: 1,216 researchers; 4,214 operators, 2,424 on attacks and 1,790 on
  surveillance; 32,213 collection specialists, half of whom run implants and half process the take; and
  2,892 analysts, 1,103 on attacks and 1,790 who plan surveillance's new accesses, with a tenth of their
  capacity spare. No operator waits for the analysts.
- **Today's attacks.** 355 attacks a year of one target each. One attack takes 9.9 expert-years: 6.8 of
  operators and 3.1 of analysts. The compute is priced on working hours, so a unit of AI work already
  costs less than a unit by hand (0.44 of it), and AI does 11% of the work. Initial access and movement
  take 0.275 years each and the effect 0.2 years, so an attack takes 9 months to build, and the force
  holds about 700 attacks ready, two years of attacks.
- **Today's surveillance.** 42,500 new accesses a year replace today's losses. About 10,300 accesses wait
  for movement and an implant, and about 74,700 implants collect, of which the collection specialists run
  12%. The take waits about five weeks to be processed. One more analyst-year is worth 41 SEV on attacks
  and 1.9 SEV on the planning of surveillance, so the default staffing rule gives attacks the priority.
- **Today's capabilities.** The researchers find about 2,000 capabilities a year, most for surveillance,
  which draws a never-used capability for one need in twenty. Attacks draw 85% of their zero-days from the
  never-used stocks (95% at the effect). The pools hold about 1,700 never-used capabilities, a year of
  asks. A quarter of the attacks made are exposed and burn what they hold, about 21 capabilities a year,
  and shared burns cost surveillance about one and a half accesses a year.
- **Today's plans.** The best plan today is the one-day plan, with about 140 attacks and a chance of
  0.754 against the 0.8 needed. The force holds about two years of attacks ready, so a longer plan adds
  few attacks but more time for a shared failure: 0.748 for a week, 0.724 for a month and 0.665 for a
  quarter.
- **The shared capability.** Today an attack has one kind of target system, d = 0.5 and a day plan
  expects 0.053 failures, so a failure is rare but leaves the plan a chance of only about 0.1. As AI widens
  attacks to more targets and kinds of target system, d falls and the expected failures rise: in 2051 of
  fast AI an attack has 3.9 kinds, d = 0.13 and a day plan of 32 attacks on about 950 targets expects 0.2
  failures, and one failure leaves it a chance of 0.71. Without AI the kinds and d keep today's values.
- **The ceiling of a plan's chance.** The common factor and the planners' error cap the chance that a
  plan meets its plan, whatever the number of attacks (§3).
- **Today's stability.** Today is a rest point of every run without AI, under both learning forms, both
  funding rules, each staffing rule and each workforce option. It lies on the kink of the operators' limit
  at initial access, so its stability must be read on each side of the kink, and the backlog of initial
  access gives a neutral direction on one side (§3). At the defaults a small move of the lessons decays.
- **The tipping corner.** With a prior strength of about 500 or less and a curve shape above about 2 to
  2.5 (at a prior of 300, above about 1.6), today is a tipping point between two regimes. At a prior of
  300 and a shape of 3, the run without AI that starts with 1% more lessons reaches 0.65 of the operators
  on attacks and about 400 attacks a year in 25 years; with 1% fewer it falls to 0.32 and about 220, and
  later the analysts leave attacks and no attacks are made. The run without AI stays at today only
  because it starts exactly there. The yearly errors of the assessment tip it to one side or the other,
  and the spread `tipping_corner` (brief.toml) draws only those errors in this corner to show the split.
  A model in an unstable region contradicts the persistence of today's split; the analysis must report
  it, not drop it.

### 8. Analysis interface

The 47 continuous stocks form the field of the run. A rest point can lie on the kink of a step's
limit and can have neutral directions, such as the backlog of initial access while the operators limit
the starts (§3); its stability must then be read on each side of the kink and away from the neutral
directions. `napkin.dynamics` offers:
- `vector_field`, `equilibria` and `continue_equilibrium` (in `t` along an AI path, or in any input);
- `fold_curve`;
- `input_threshold` and `state_threshold` (for example the smallest surge that tips the split);
- `morris` and `sobol`.

A Monte Carlo study (`evaluate_uncertainty`) draws the yearly assessment errors and any input given
a distribution. The output `doctrine_counts` gives the share of a study's samples in which plans count
on cyber attacks.

### 9. How the structure differs from the closest work

The literature that the essay cites (Sulmeyer, Lohn, Withers, Huskaj, Maschmeyer) asks what AI adds to
today's operations. This pass has not reviewed it.

In `cyber_learning_loop`, the volume of attacks, the lessons and the funding are outcomes of feedback. So the model
can have no rest point, one or several, and the question becomes where AI moves the rest points and
their stability, not how much it multiplies today's effects.
