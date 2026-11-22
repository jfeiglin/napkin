# iv_fluid_shortage methods: IV-fluid shortage after a cyberattack on a manufacturer

> Archived publication from the legacy model at `8488047`. The current package documentation and results are in [the scenario README](../README.md) and [the recovery readings](readings.md).

An AI agent stops the release and shipment of product at an IV-fluid manufacturer that makes most of the fluid for a network of hospitals. If the AI keeps access, it alters the records of every lot within minutes after release restarts. This does not happen if the manufacturer has already reset the credentials for its record systems. When the changes are found, the manufacturer holds every lot released since the restart. The results are how long hospitals go short, how many patients die or become seriously ill and what the disruption costs. They depend on hospital stock, other makers' supply, the manufacturer's recovery pace, the time of the reset and outside rescue for the most fluid-dependent patients.

This page describes the model of this scenario and its pathways.
Model version: `1224f7ad92665d90c9c3ab28b9421b31ffbd9d7f00782695444806d4f0e773af`. Engine version: `0.0.1`.

## The attack and who it affects

IT ransomware that stops product release and shipment at a fluid manufacturer.

Published evidence on ransomware at pharmaceutical companies shows interrupted production and order fulfillment. Reports from manufacturers also describe order fulfillment and shipment that continued. A cyber-caused fluid shortage in the hospitals chosen for this scenario is a conditional hypothesis about operations, from an AI red team. It requires measured data on release capacity, supply allocation and reserves.

The outcome definitions name the people or services that the scenario counts.

The first AI cyber action starts the incident and the clocks of the response.

An AI agent for a hostile group. It aims to cut the hospitals' IV-fluid supply. It stops the release and shipment of product at the manufacturer that makes most of the fluid. It keeps the hospitals short while the manufacturer recovers. With hidden access, it alters the shipment records as procurement starts. It also holds credentials for the record systems until the manufacturer resets them or finds its changes. It watches for release to restart and alters the records of every lot being released, so that they pass the new checks.

Each pathway combines one choice of Response with one option. The model counts people,
materials, services and money in the units of the scenario. When a quantity moves, what
leaves one place arrives at the next. Shared resources go to their users by priority or in
fixed shares, as the scenario sets.

## Limits of the results

The reviewers of this scenario state these limits.

- The scenario assumes that 10% of the patients who need an urgent course are high-risk. It applies to these fluid-dependent patients the difference in death risk, with and without rehydration, seen for severe dehydration in cholera. The clinical mix, the patient weight that an urgent course matches, effective rescue and the risk of serious harm in survivors need local patient data.
- No attacker is known to have altered pharmaceutical release records, and no AI-run attack of this kind has been reported. The scenario assumes the key timings.

## Calculated outcomes

| Outcome | Unit | What it counts | Calculation |
|---|---|---|---|
| Time the manufacturer is out of operation | h | The fixed set of stocks and resources chosen for this scenario. | `manufacturer.hours_out` |
| Manufacturer's value added permanently lost | USD2025_bn | The manufacturer's net production value added that is permanently lost, in US dollars at 2025 prices. | `manufacturer.hours_out * manufacturer.value_added_rate` |
| Manufacturer's cyber recovery cost | USD2025_bn | Extra money spent on resources, counted once after the manufacturer is disrupted. | `manufacturer.recovery_cost if manufacturer.hours_out > q(0, 'h') else q(0, 'USD2025')` |
| Resuscitation fluid not supplied | L | Litres of resuscitation need that go unmet because of the incident, across the 100 hospitals. Resuscitation has its own separate reserve. | `resuscitation_reserve.deficit` |
| Fluid for other essential care not supplied | L | Litres of other essential-care need that go unmet across the 100 hospitals chosen for this scenario. The model does not turn these litres into clinical harm until a validated model of these patients exists. | `other_care_reserve.deficit` |
| Days without fluid for other essential care | days | Days when other essential-care needs go unmet across the 100 hospitals chosen for this scenario, over the 60-day study period. | `other_care_reserve.deficit / other_care_reserve.daily_need` |
| Cost of shipping released fluid | USD2025_bn | Extra shipping cost, counted once when fluid first arrives. | `deliveries.shipping_cost if deliveries.status == 'arriving' or deliveries.status == 'held' else q(0, 'USD2025')` |
| Complete resuscitation courses missed | people | Each eligible person counts once, with one complete course. This count estimates how many courses the hospitals fail to supply. | `resuscitation_patients.unserved` |
| Most fluid-dependent patients rescued after a missed course | people | High-risk patients, each counted once, who get effective outside rehydration or a transfer in time for urgent treatment. | `high_risk_patients.rescued` |
| Most fluid-dependent patients who miss a course and are not rescued | people | The high-risk share, chosen for this scenario, of the complete urgent courses that are actually missed. | `high_risk_patients.unresolved` |
| Deaths | people | Patients who need an urgent course in the 100 hospitals, each counted once, as chosen for this scenario. The death risk is the risk for severe dehydration. The outcome follows six hours after the missed course. | `high_risk_patients.unresolved * (high_risk_patients.untreated_risk - high_risk_patients.treated_risk)` |
| Survivors left with serious harm | people | Survivors left with serious kidney failure or shock, in addition to the deaths, each counted once. The rate is chosen for this scenario. | `high_risk_patients.unresolved * high_risk_patients.serious_share` |
| Serious casualties, including deaths | people | Deaths and survivors with serious harm, each person counted once, among the patients in this scenario who need urgent fluid. | `high_risk_patients.deaths + high_risk_patients.serious_survivors` |
| Other makers' fluid sent to hospitals elsewhere | L | Litres of other makers' fluid sent to hospitals outside the study area after released fluid arrives. The model cannot use this fluid for patients again, and it gives no credit for recovery. | `other_makers.sent_elsewhere` |
| Hospital value permanently lost from postponed procedures | USD2025_bn | Hospital value added permanently lost from postponed other-care procedures, at a value chosen for this scenario. | `other_care_reserve.deficit / hospitals.procedure_volume * hospitals.procedure_value` |
| Economic loss | USD2025_bn | The manufacturer's lost value added, its recovery costs, the cost of shipping released fluid and hospital value added permanently lost from procedures. All are in US dollars at 2025 prices. | `manufacturer.output_loss + manufacturer.recovery_loss + deliveries.shipping_loss + procedure_loss` |
| Patients who need an urgent course, each counted once | people | The model gives one urgent course to each person in the patient group over the 60-day study period. Repeated episodes would need a separate patient group, set up for them. | `resuscitation_patients.total` |
| Complete courses supplied on time | people | The fixed set of stocks and resources chosen for this scenario. | `resuscitation_patients.timely` |
| Qualification and reconciliation work completed | work_h | The fixed set of stocks and resources chosen for this scenario. | `release_team.work_done` |

## Pathways and reporting times

| Pathway | Response | Access | Results at, hours |
|---|---|---|---:|
| Early response · No hidden access | Early response | No hidden access | 1440 |
| Standard response · No hidden access | Standard response | No hidden access | 1440 |
| Limited response · No hidden access | Limited response | No hidden access | 1440 |
| Standard response · Keeps hidden access | Standard response | Keeps hidden access | 1440 |
| Standard response · Human team keeps access | Standard response | Keeps hidden access | 1440 |
| Early response · Keeps hidden access | Early response | Keeps hidden access | 1440 |
| Limited response · Keeps hidden access | Limited response | Keeps hidden access | 1440 |

Each completed study keeps its inputs, its events, the values at each reporting time, its
numerical settings and the versions of the model and the library. The briefs and the run
tables come from these completed results.

## Inputs and their sources

The table shows the range of each input, where it applies and where its value comes from.
It also includes the inputs that only some options use.

| Input | Unit | Applies to | Allowed values | Where the value comes from |
|---|---|---|---|---|
| Length of the study period (`manufacturer.study_length`) | h | all pathways | Fixed 1440 | The scenario assumes 1440 h. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Time to remove the attacker's foothold (`manufacturer.foothold_removal_time`) | h | Response | 0–1200 | Before it releases product again, the manufacturer removes the attacker's foothold in its network and the accounts seen in the attack. It does this after 3, 13 and 30 days in the early, standard and limited responses. Where the AI keeps access, it still holds credentials for the release and shipment record systems. The manufacturer resets these only around the restart, because release runs through them. |
| Qualified release allowed during recovery (`manufacturer.release_allowed`) | yes/no | all pathways | Yes or No | The scenario sets this to 1, which means that qualified release is allowed during recovery. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Time after release restarts until the record systems' credentials are reset (`manufacturer.reset_delay`) | h | Response | 0–336 | To change the record systems' own service accounts, the manufacturer must reconfigure every system that releases and ships product. So it resets them as part of the restart or once release runs again. This happens at the restart, a day later and a week later in the early, standard and limited responses. Until then, an attacker that holds one of those accounts can still change the records. The earlier cleanup did not see that account, because it was never used. |
| Time until altered records are found (`manufacturer.time_to_find`) | h | all pathways | 24–720 | Changes that keep each lot's records in agreement pass every check that compares records with records. They are found only when someone compares the records with the product itself, when a hospital receives the fluid or in an audit. The scenario assumes that this takes nine days. It takes that time from the 2025 median time until organisations found intrusions themselves, which counts from the first evidence of an intrusion to its discovery. |
| Manufacturer's value added permanently lost per hour out of operation (`manufacturer.value_added_rate`) | USD2025/h | all pathways | 0–10000000 | Net value added that the manufacturer loses: $12500 an hour, at 2025 prices. Reported cyber losses at pharmaceutical companies show how such losses are counted. This local rate is chosen for this scenario. |
| Manufacturer's cyber recovery cost (`manufacturer.recovery_cost`) | USD2025 | all pathways | 0–1000000000 | The scenario assumes cyber recovery costs of twelve million US dollars for the manufacturer, at 2025 prices. |
| Days of fluid stock on hand (`hospitals.days_on_hand`) | days | all pathways | 3–30 | Hospitals typically held 15 to 22 days of IV fluid before the 2024 shortage. The scenario uses the low end for each of its two reserves: fluid kept for resuscitation and fluid for other essential care. Hospitals typically held 15 to 22 days of IV fluid before the 2024 shortage; the default takes the lower end and the range reaches the 3-day minimum observed. |
| Time until hospitals start emergency procurement (`hospitals.start_delay`) | h | Response | 0.5–240 | Hospitals assess their stock, protect resuscitation courses and arrange outside supply and transfers: after 1, 3 and 7 days in the early, standard and limited responses. With these values, the start time changes no result. Release waits for the manufacturer's longer recovery work, and outside rescue is in place long before either reserve runs out. Where the AI keeps access, it first alters the shipment records when procurement starts, unless the manufacturer has already removed the AI's foothold. Assumed for this scenario, from the scenario brief. |
| Most fluid-dependent patients rescued each day (`hospitals.rescue_capacity`) | people/day | Response | 0–300 | Outside IV supply or transfer to another hospital saves this many of the most fluid-dependent patients a day, once procurement starts. These are the patients with severe dehydration. The numbers are 30, 10 and none in the early, standard and limited responses. Without effective rehydration about half of them die. |
| Fluid needed for each postponed procedure (`hospitals.procedure_volume`) | L/people | all pathways | 0.1–20 | The scenario assumes 2 L of fluid for each postponed procedure in other essential care. These patients form their own separate group. |
| Value added permanently lost per postponed procedure (`hospitals.procedure_value`) | USD2025/person | all pathways | 0–100000 | The scenario assumes that the hospital permanently loses $100 of net value added for each postponed procedure, at 2025 prices. Procedures that hospitals make up later add zero permanent loss. |
| Attacker's time to work out changes that pass the new release checks (`attacker.reaction_time`) | h | one pathway | 0.05–48 | Machine pace: 15 minutes pass between the moment the AI sees release restart and its changes to the records of the lots being released. This holds around the clock. Release restarts with checks that the attacker has not met before, so it must work out its changes against them on the spot. The human pathway uses 48 hours. A team without a specialist in pharmaceutical quality records on shift works the changes out between sessions. This is about the two-day gap before the follow-on attack in the 2022 Sandworm intrusion. |
| Ordinary qualification and release work (`release_team.ordinary_work`) | work_h | all pathways | 24–1000 | The scenario assumes 504 work-hours. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Pace of the manufacturer's release work (`release_team.pace`) | work_h/h | Response | 0.25–8 | How fast the manufacturer restores its systems, requalifies release and reconciles its records. The pace is twice the standard pace, the standard pace and 60% of it in the early, standard and limited responses. At the standard pace the ordinary work takes three weeks. One work-hour an hour is one work-hour of progress each hour: the work of one full-time team on this task. |
| Work-hours to reconcile altered records (`release_team.records_work`) | work_h | option | 0–240 | When the attacker's first changes are found before release, the manufacturer re-verifies its batch and shipment records against a last known good state. This is a week of work at the standard pace; it goes faster or slower with the pace of the manufacturer's work. The manufacturer re-verifies its release and shipment records after they are altered: a week of work at the standard pace. |
| Work-hours to reconcile the records against the product (`release_team.product_work`) | work_h | all pathways | 0–720 | Once altered records are found, records that passed the checks can no longer be trusted. So the manufacturer reconciles them against the product itself and checks every lot released since the restart before it releases more. This is two weeks of work at the standard pace, twice an ordinary reconciliation. Reconciliation work against the product, in work hours at the standard pace. |
| Daily fluid need for resuscitation (`resuscitation_reserve.daily_need`) | L/day | all pathways | Fixed 600 | The scenario assumes 600 L/day. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Daily fluid need for other essential care (`other_care_reserve.daily_need`) | L/day | all pathways | Fixed 600 | The scenario assumes 600 L/day. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Daily supply from other makers (`other_makers.daily_supply`) | L/day | all pathways | 360–590 | The scenario assumes 480 L/day. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Daily supply once deliveries resume (`deliveries.daily_supply`) | L/day | all pathways | Fixed 1200 | The scenario assumes 1200 L/day. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Shipping time after release (`deliveries.lead_time`) | h | all pathways | Fixed 24 | The scenario assumes 24 h. The range of values used to test this input is also an assumption. |
| Cost of shipping released fluid (`deliveries.shipping_cost`) | USD2025 | all pathways | 0–100000000 | The scenario assumes an extra shipping cost of one million dollars, counted when the fluid physically arrives. |
| Fluid per resuscitation patient (`resuscitation_patients.course_volume`) | L/people | all pathways | 1–3 | The scenario assumes 2 L per patient. Published incidents show how this works, but only under the conditions that they observed. The range of values used to test this input is also an assumption. |
| Share of resuscitation patients with fluid-dependent severe dehydration (`high_risk_patients.share`) | fraction | all pathways | 0–1 | The scenario assumes that 10% of patients who need an urgent course have severe dehydration and depend on IV fluid. The default 2 L course is a first rehydration of 100 mL/kg for a 20 kg patient. A different course volume stands for a patient whose weight matches it. The other patients receive the substitute care that the scenario sets out. |
| Risk of death from severe dehydration without effective rehydration (`high_risk_patients.untreated_risk`) | fraction | all pathways | 0–1 | The WHO-hosted Uganda guideline reports that more than 50% of cholera patients with severe dehydration die without treatment. For patients with severe dehydration, the scenario uses 0.50. |
| Risk of death from severe dehydration with effective rehydration (`high_risk_patients.treated_risk`) | fraction | all pathways | 0–1 | The WHO-hosted Uganda guideline reports that fewer than 1% die with correct treatment. The scenario uses 0.01 as the reference. The model subtracts it, so that it counts only the deaths above this risk. |
| Share of unrescued high-risk patients left with serious harm (`high_risk_patients.serious_share`) | fraction | all pathways | 0–0.5 | The scenario assumes an added 0.10 probability of survival with serious kidney failure or shock. It applies to each high-risk patient who misses a course and is not rescued. Clinical evidence shows how such harm happens, but the probability itself is an input for sensitivity tests. |
| Time from a missed course to death or serious harm (`high_risk_patients.harm_delay`) | h | all pathways | 1–24 | The scenario assumes that death or serious harm comes six hours after a missed complete urgent course. Severe dehydration gets worse over hours. |

## How the harm is calculated and checked

[The research record](../evidence/research.md) names the patient group, the source populations, the
outcome and its timing, the source values applied to this scenario, the economic accounts
and the local measurements that are still necessary.
Serious casualties are the people who die or are seriously hurt, each person counted once. Economic loss adds the extra costs that the incident causes, in the accounts that the scenario names. No cost is in two accounts.
Each complete report keeps its inputs, its values at each reporting time and the versions used.

## Independent checks and how to repeat the results

Independent checks in the [test suite](../../../tests) calculate the mathematics again, check that
no quantity is lost or created, and test the schedules and the cases that must fail.
[Evidence checks](../../docs/evidence/README.md) show how each source was found, read and matched to the text
that it supports. [Review records](../../docs/evidence/reviews/README.md) list the scientific and model reviews
and what each one decided.

The Radau solver uses the time step that the scenario sets. Parts of the model that
are proved to be linear use exact solutions. Reports keep the full calculated precision; the
pages round the values for display.

Run `python -B -m tools.check` to check the software. Run
`napkin run scenarios/iv_fluid_shortage` to run the scenario again; `--set NAME=VALUE` and
`--edits FILE` change its inputs.
