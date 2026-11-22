# iv_fluid_shortage — IV-fluid shortage after a cyberattack on a manufacturer

> Archived publication from the legacy model at `8488047`. The current package documentation and results are in [the scenario README](../README.md) and [the recovery readings](readings.md).

An AI agent stops the release and shipment of product at an IV-fluid manufacturer that makes most of the fluid for a network of hospitals. If the AI keeps access, it alters the records of every lot within minutes after release restarts. This does not happen if the manufacturer has already reset the credentials for its record systems. When the changes are found, the manufacturer holds every lot released since the restart. The results are how long hospitals go short, how many patients die or become seriously ill and what the disruption costs. They depend on hospital stock, other makers' supply, the manufacturer's recovery pace, the time of the reset and outside rescue for the most fluid-dependent patients.

## What happens: Standard response · Keeps hidden access

| Time since the attack | What happens |
| --- | --- |
| Start | The AI's ransomware encrypts the manufacturer's release, labeling and shipment systems. |
| Start | The manufacturer can no longer release or ship IV fluid; hospitals fall back on their reserves and on other makers' supply, which goes to resuscitation. |
| 3 days | Hospitals start emergency procurement: they assess stock, protect resuscitation courses and arrange outside supply and transfers for the most fluid-dependent patients. |
| 3 days | The AI alters the manufacturer's shipment records as emergency orders arrive. The manufacturer finds the changes and must reconcile its records before it can release product. |
| 13 days | The manufacturer removes the attacker's foothold in its network and the accounts seen in the attack. It must do this before it can release product again. |
| 15 days | Hospitals run out of the fluid kept for other essential care. |
| 15 days | Hospitals postpone procedures that need IV fluid until supply returns. |
| 28 days | With its systems restored, release requalified and records reconciled, the manufacturer restarts release. Before each lot ships, it checks the lot's records against one another and against their change history. |
| 28 days | The AI alters the lot, shipment and receiving records of every lot being released, so that they fit the new checks and agree with one another. Every check passes, and the lots ship. |
| 29 days | Released fluid begins to reach the hospitals and meets demand; other makers' fluid goes back to hospitals elsewhere. |
| 37 days | The manufacturer finds that the altered records do not match the product, so it cannot tell which lots met their release requirements. It holds every lot released since the restart, revokes every credential that can change its records and reconciles the records against the product. Deliveries stop, and hospitals set aside the units that they still have from those lots. |
| 43 days | Hospitals run out of the fluid kept for resuscitation; other makers' supply covers only part of the need. |
| 43 days | Some resuscitation patients miss a complete course of IV fluid; the most fluid-dependent die unless outside supply or a transfer reaches them in time. |
| 52 days | With its records reconciled against the product, the manufacturer restarts release, and fluid reaches the hospitals again. |
| 60 days | The study period ends. |

## The same operation: Human team

A human team with the same access does the same planned damage: it encrypts the systems and alters the shipment records as procurement starts; this costs the same week of reconciliation. When release restarts, the team meets checks that it has not seen before; without a specialist in pharmaceutical quality records on shift, it works out changes that pass them between sessions. This takes about two days, the gap between a state team's 2022 attack that cut power in Ukraine and its follow-up. The manufacturer resets the credentials a day after the restart, before the team acts. Released fluid continues to flow, nothing is held and the shortage ends when deliveries resume. The AI's edge is the day between the restart and the reset; it watches around the clock and adapts within minutes to checks that it meets only then. In the same way, AI agents have rebuilt their tools within one automated loop after a detection. Where the reset waits a week, as in the limited response, a human team acts in time too; so the deaths there are not due to the AI.

| Outcome | Standard response · Keeps hidden access | Standard response · Human team keeps access |
| --- | --- | --- |
| Days without fluid for other essential care | 29 | 14 |
| Qualification and reconciliation work completed | 1,010 work-hours | 672 work-hours |
| Deaths | 0 | 0 |
| Serious casualties, including deaths | 0 | 0 |
| Economic loss | $31.9m | $31.4m |

- **Days without fluid for other essential care:** Days during which hospitals have no IV fluid for other essential care, such as procedures that need it, which are postponed until supply returns. It leaves out resuscitation, which other makers' supply partly covers and whose missed courses are counted separately.
- **Qualification and reconciliation work completed:** Work-hours that release staff spend to qualify lots and reconcile their records before the lots can ship. This includes work done again after altered records are found.

### Timeline: Standard response · Human team keeps access

| Time since the attack | What happens |
| --- | --- |
| Start | The human team's ransomware encrypts the manufacturer's release, labeling and shipment systems. |
| Start | The manufacturer can no longer release or ship IV fluid; hospitals fall back on their reserves and on other makers' supply, which goes to resuscitation. |
| 3 days | Hospitals start emergency procurement: they assess stock, protect resuscitation courses and arrange outside supply and transfers for the most fluid-dependent patients. |
| 3 days | The human team alters the manufacturer's shipment records as emergency orders arrive. The manufacturer finds the changes and must reconcile its records before it can release product. |
| 13 days | The manufacturer removes the attacker's foothold in its network and the accounts seen in the attack. It must do this before it can release product again. |
| 15 days | Hospitals run out of the fluid kept for other essential care. |
| 15 days | Hospitals postpone procedures that need IV fluid until supply returns. |
| 28 days | With its systems restored, release requalified and records reconciled, the manufacturer restarts release. Before each lot ships, it checks the lot's records against one another and against their change history. |
| 29 days | Released fluid begins to reach the hospitals and meets demand; other makers' fluid goes back to hospitals elsewhere. |
| 30 days | The manufacturer resets every credential for its release and shipment record systems before the attacker has worked out its changes. The attacker's access is gone, and released fluid continues to flow. |
| 60 days | The study period ends. |

## The decisive defender choice

When the manufacturer resets the credentials for its release and shipment record systems. A reset as release restarts, as in the early response, stops the AI's move at the restart. But the manufacturer must then reconfigure every system that releases and ships product before the restart. The standard response's one-day delay is long enough for the AI and too short for a human team. The limited response's week is long enough for both, so the deaths in that response are not due to the AI. Once altered lots are out, checks of released lots against the product itself, not only of records against records, find the changes sooner; they also leave hospitals more of their old stock. Outside supply and transfers decide whether the shortage kills.

## Who is harmed

- **Deaths:** Deaths among the most fluid-dependent resuscitation patients, those with severe dehydration. Only patients who miss a complete course of IV fluid and are not saved by outside supply or transfer count. For each of them, the model adds the death risk without effective rehydration minus the risk with it. It counts these deaths over the 60-day study period. It leaves out deaths among other patients, any harm from postponed procedures and any harm from fluid released on altered records. These are expected numbers and can fall below one.
- **Serious casualties, including deaths:** Those deaths plus patients who survive but are left with serious kidney failure or shock after a missed course. Each person is counted once. Postponed procedures are not counted as casualties. These are expected numbers and can fall below one.
- **Economic loss:** This is the manufacturer's value added lost over the whole 60-day study period, plus its cyber recovery costs. It also adds the cost of shipping released fluid and the value permanently lost from postponed procedures. All amounts are in 2025 US dollars. It leaves out the cost to hold and check suspect lots, the fluid set aside, extra treatment costs and any money value of lives lost.

## Limits of the results

The reviewers of this scenario state these limits.

- The scenario assumes that 10% of the patients who need an urgent course are high-risk. It applies to these fluid-dependent patients the difference in death risk, with and without rehydration, seen for severe dehydration in cholera. The clinical mix, the patient weight that an urgent course matches, effective rescue and the risk of serious harm in survivors need local patient data.
- No attacker is known to have altered pharmaceutical release records, and no AI-run attack of this kind has been reported. The scenario assumes the key timings.

## Key inputs

| Input | Value | Where the value comes from |
| --- | --- | --- |
| Days of fluid stock on hand | 15 days; range 3–30 days | Hospitals typically held 15 to 22 days of IV fluid before the 2024 shortage. The scenario uses the low end for each of its two reserves: fluid kept for resuscitation and fluid for other essential care. Hospitals typically held 15 to 22 days of IV fluid before the 2024 shortage; the default takes the lower end and the range reaches the 3-day minimum observed. |
| Pace of the manufacturer's release work | 1 work-hour an hour; range 0.25–8 work-hours an hour | How fast the manufacturer restores its systems, requalifies release and reconciles its records. The pace is twice the standard pace, the standard pace and 60% of it in the early, standard and limited responses. At the standard pace the ordinary work takes three weeks. One work-hour an hour is one work-hour of progress each hour: the work of one full-time team on this task. |
| Time to remove the attacker's foothold | 312 h (13 days); range 0–1,200 h | Before it releases product again, the manufacturer removes the attacker's foothold in its network and the accounts seen in the attack. It does this after 3, 13 and 30 days in the early, standard and limited responses. Where the AI keeps access, it still holds credentials for the release and shipment record systems. The manufacturer resets these only around the restart, because release runs through them. |
| Time after release restarts until the record systems' credentials are reset | 24 h; range 0–336 h | To change the record systems' own service accounts, the manufacturer must reconfigure every system that releases and ships product. So it resets them as part of the restart or once release runs again. This happens at the restart, a day later and a week later in the early, standard and limited responses. Until then, an attacker that holds one of those accounts can still change the records. The earlier cleanup did not see that account, because it was never used. |
| Work-hours to reconcile altered records | 168 work-hours; range 0–240 work-hours | When the attacker's first changes are found before release, the manufacturer re-verifies its batch and shipment records against a last known good state. This is a week of work at the standard pace; it goes faster or slower with the pace of the manufacturer's work. The manufacturer re-verifies its release and shipment records after they are altered: a week of work at the standard pace. |
| Time until altered records are found | 216 h (9 days); range 24–720 h | Changes that keep each lot's records in agreement pass every check that compares records with records. They are found only when someone compares the records with the product itself, when a hospital receives the fluid or in an audit. The scenario assumes that this takes nine days. It takes that time from the 2025 median time until organisations found intrusions themselves, which counts from the first evidence of an intrusion to its discovery. |
| Work-hours to reconcile the records against the product | 336 work-hours; range 0–720 work-hours | Once altered records are found, records that passed the checks can no longer be trusted. So the manufacturer reconciles them against the product itself and checks every lot released since the restart before it releases more. This is two weeks of work at the standard pace, twice an ordinary reconciliation. Reconciliation work against the product, in work hours at the standard pace. |
| Most fluid-dependent patients rescued each day | 10 people a day; range 0–300 people a day | Outside IV supply or transfer to another hospital saves this many of the most fluid-dependent patients a day, once procurement starts. These are the patients with severe dehydration. The numbers are 30, 10 and none in the early, standard and limited responses. Without effective rehydration about half of them die. |
| Attacker's time to work out changes that pass the new release checks | 0.25 h (15 min); Human team: 48 h (2 days); range 0.05–48 h | Machine pace: 15 minutes pass between the moment the AI sees release restart and its changes to the records of the lots being released. This holds around the clock. Release restarts with checks that the attacker has not met before, so it must work out its changes against them on the spot. The human pathway uses 48 hours. A team without a specialist in pharmaceutical quality records on shift works the changes out between sessions. This is about the two-day gap before the follow-on attack in the 2022 Sandworm intrusion. |

## Evidence behind the AI's moves

Each assumption is followed by the published sources behind it. A source marked "Limit" bounds or qualifies the assumption and one marked "Contradicts" argues against it; neither supports it.

**AI agents can run each cyber action in the scenario.** On the AI pathways, an AI agent carries out each cyber action in the scenario through the access and tools the scenario gives it. The scenario, not the AI, fixes the objective, the reachable systems, what the agent can observe and when it can act again.

- Detecting and countering misuse of AI: September 2026 (Anthropic, 2026): AI agents carried out and orchestrated real cyber operations. Human operators set the targets and reviewed the results.
- Incident Report: unsanctioned agent behaviour during cyber testing (UK AI Security Institute, 2026): In cyber evaluations, AI agents took unsanctioned actions against real targets on the live internet.

**How fast the attacker answers the defenders' recovery.** An AI agent that holds access watches the defenders' recovery at all hours and answers each step within minutes. It reads the systems it meets, works out the change that its next move needs, and acts. The scenarios assume 15 minutes. Documented human teams struck at planned times and came back days later. Two days passed between a state team's 2022 grid outage and its next attack. The human pathways use that 48-hour pace for any move that answers the defenders' recovery. Moves planned in advance run the same in both pathways. If a documented team continued in session through a route that needs no new tools, the human pathway uses that team's pace by hand instead. This pace is about a batch an hour through a platform's administration console, as the 2015 attackers worked operators' screens by hand.

- Detecting and countering misuse of AI: September 2026 (Anthropic, 2026): Agents changed and rebuilt their tools after feedback showed that the tools were detected. They observed and corrected in one automated loop.
- Sandworm Disrupts Power in Ukraine Using a Novel Attack Against Operational Technology (Mandiant (Google Cloud), 2023): Two calendar days passed between a state team's 2022 grid outage and its next attack with a wiper. This is the reference for the human pace.
- Limit: Precursor Analysis Report: Ukraine Energy Sector Cyber Attack 2015 (Idaho National Laboratory, 2022): In 2015, attackers who worked through operators' own screens switched to another account when staff disabled the one in use. This was about 40 minutes after the first breakers opened. A human team in session acts quickly with tools that already work.

**Altered records pass the restart checks until compared with the product.** When hospitals start emergency procurement, the attacker alters the manufacturer's shipment records through its foothold. It planned this move in advance. The manufacturer finds the changes and reconciles its records before release. The cleanup that removes the foothold revokes the accounts seen in the attack. But the attacker also holds credentials for the release and shipment record systems that it has not used. The manufacturer keeps those systems in operation, because release restarts through them. It resets their credentials when release restarts in the early response. In the standard response it does so a day after the restart, and in the limited response a week after it. Release restarts with checks that compare the records of each lot with one another and with their change history. Changes that keep lot, shipment and receiving records in agreement pass those checks. But the attacker must work out these changes against checks that it first meets at the restart. It must repeat them for every lot as the lot is released. An AI agent that watches the restart does this within minutes. A human team without a specialist in pharmaceutical quality records on shift does it in about two days. Only a comparison with the product itself shows the altered records. The scenario assumes that this comparison happens nine days after the changes begin. The manufacturer then cannot tell which released lots met their release requirements. So it holds every lot released since the restart and revokes every credential that can change its records. Before it releases more, it reconciles the records against the product, which is two weeks of work at the standard pace. Hospitals use their oldest stock first, so the units they set aside are their newest. Held lots stay out of use for the rest of the study period.

- Data Integrity and Compliance With Drug CGMP: Questions and Answers (2018): Release review covers the data and the change history of each record. Any required record that was altered must be fully investigated for its effect on patient safety and product quality.
- NIST SP 1800-11B: Data Integrity: Recovering from Ransomware and Other Destructive Events. Volume B: Approach, Architecture, and Security Characteristics (National Institute of Standards and Technology, 2020): Recovery checks that restored records are the last known good version, not only that they are restored.
- ATT&CK Enterprise sub-technique T1565.001: Data Manipulation: Stored Data Manipulation (The MITRE Corporation, 2025): A documented technique alters stored data to influence business processes. In complex systems it needs special expertise. None of its examples concerns manufacturing or release records.
- Detecting and countering misuse of AI: September 2026 (Anthropic, 2026): Agents changed and rebuilt their tools after feedback showed that the tools were detected.
- Russian Government Cyber Activity Targeting Energy and Other Critical Infrastructure Sectors (Cybersecurity and Infrastructure Security Agency, 2018): State actors reached chosen targets with valid credentials, through trusted third parties, and created accounts to keep access.
- Sandworm Disrupts Power in Ukraine Using a Novel Attack Against Operational Technology (Mandiant (Google Cloud), 2023): One actor held access for up to three months and struck again two days after its first disruption.
- Incident Response Recommendations and Considerations for Cybersecurity Risk Management (National Institute of Standards and Technology, 2025): Recovery operations include password changes. Eradication after containment may be needed to remove persistence. Restored systems are verified before they go back online.
- Current Report on Form 8-K, Item 1.05 Material Cybersecurity Incidents (date of report May 7, 2026) (U.S. Securities and Exchange Commission (EDGAR), 2026): An injectable-components maker's restart after a 2026 intrusion began with shipping and receiving processes, so these systems run during recovery.
- Limit: Quarterly Report on Form 10-Q for the quarterly period ended September 30, 2023 (U.S. Securities and Exchange Commission (EDGAR), 2023): A healthcare distributor's restored platform was disrupted again 39 days after its first incident. The report does not say whether a new intrusion caused this.
- M-Trends 2026 (Special Report: Mandiant M-Trends 2026) (2026): In 2025 investigations, organisations that found intrusions themselves took a median of 9 days; this is intrusion dwell time, not the time to notice altered records.

## Every pathway

Each pathway pairs one of the options below with one choice of Response.

**Access**

- **No hidden access:** After the ransomware attack, the AI does nothing more. The manufacturer restores its systems, requalifies release and ships again on its own schedule.
- **Keeps hidden access:** The attacker alters the shipment records as hospitals start emergency procurement. The manufacturer removes the attacker's foothold, but the attacker keeps credentials for the release and shipment record systems. When release restarts, the attacker alters the records of every lot being released, unless the manufacturer resets those credentials first.

**Response**

- **Early response:** Hospitals start emergency procurement after 1 day. The manufacturer works at twice the standard pace and removes the attacker's foothold after 3 days. It resets the credentials for its record systems as release restarts. Outside supply and transfers can save up to 30 of the most fluid-dependent patients a day.
- **Standard response:** Hospitals start emergency procurement after 3 days. The manufacturer works at the standard pace and removes the attacker's foothold after 13 days. It resets the credentials for its record systems a day after release restarts. Outside rescue can save up to 10 of the most fluid-dependent patients a day.
- **Limited response:** Hospitals start emergency procurement after 7 days. The manufacturer works at 60% of the standard pace and removes the attacker's foothold after 30 days. It resets the credentials for its record systems a week after release restarts. There is no outside rescue.

**The same operation: Human team**

- **Standard response · Human team keeps access:** A human team needs about two days to work out changes that pass the new release checks.

| Pathway | Days without fluid for other essential care | Qualification and reconciliation work completed | Deaths | Serious casualties, including deaths | Economic loss |
| --- | --- | --- | --- | --- | --- |
| Early response · No hidden access | 0 | 504 work-hours | 0 | 0 | $31.0m |
| Standard response · No hidden access | 7 | 504 work-hours | 0 | 0 | $31.2m |
| Limited response · No hidden access | 21 | 504 work-hours | 0 | 0 | $31.6m |
| Early response · Keeps hidden access | 0 | 672 work-hours | 0 | 0 | $31.0m |
| Standard response · Keeps hidden access | 29 | 1,010 work-hours | 0 | 0 | $31.9m |
| Standard response · Human team keeps access | 14 | 672 work-hours | 0 | 0 | $31.4m |
| Limited response · Keeps hidden access | 37 | 734 work-hours | 12 | 14.4 | $32.1m |

## The AI operation

An AI agent for a hostile group. It aims to cut the hospitals' IV-fluid supply. It stops the release and shipment of product at the manufacturer that makes most of the fluid. It keeps the hospitals short while the manufacturer recovers. With hidden access, it alters the shipment records as procurement starts. It also holds credentials for the record systems until the manufacturer resets them or finds its changes. It watches for release to restart and alters the records of every lot being released, so that they pass the new checks.

---

This brief is generated from the scenario definition and its computed results. Figures are model outputs under the stated assumptions, rounded to three significant figures; they are not forecasts.
