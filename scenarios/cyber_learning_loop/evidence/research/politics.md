# Attribution, sanctions and escalation after state cyber attacks, and how AI changes attribution

Notes for the model of one capable country (calibrated to the US) that splits about 42,500 cyber experts
between surveillance and effects operations, 2026–2051. Research date: 2026-11-07.

How to read the tags on each finding:

- **Scope**: who, where, period, sample.
- **Quote**: a short exact quote. For pages marked "fetch extract", the quote is the text that the fetch
  tool returned from the primary page; for pages marked "full text", I read the extracted text myself.
- **Date**: publication date of the source.
- **Access**: *full text* (primary source read in full), *fetch extract* (primary page read through the
  fetch tool, which returns extracts), *abstract*, *secondary* (news or aggregator report of the primary),
  *search summary* (only a search-result summary; not read; treat as unverified).
- **Kind**: measurement, author's estimate, official statement, or opinion.
- **Fit**: *direct* (measures state cyber operations or the responses to them), *transfer* (from a related
  population, for example all incident types including crime), or *analogy*.
- **Older**: data from before 2020.

Model inputs: attribution_now (default 0.7, range 0.3–0.95), attribution_end (0.4, range 0.05–0.95),
sanction_cost (10 expert-years of surveillance value per attributed attack, range 1–100), escalation (0,
range 0–0.1, rise in the cost of each attack per attack attributed in a year). No source in these notes gives
an empirical interval for any of these four inputs. The ranges stay selected bounds.

Access limits in this pass: the shared web-search budget ran out part-way through. These primary pages
refused a plain request or failed, so I used summaries or secondary reports, as marked: Council of the EU
timeline (HTTP 403), BleepingComputer (403), Taylor & Francis (403), ieu-monitoring (403), GlobalSecurity
(403), Journal of National Security Law & Policy PDF (503), ETH Research Collection (500), the Obama White
House archive page on the December 2016 measures (404), the Dutch government page on the OPCW operation (404),
and the DOJ release of October 2020 (no text returned). The host core-prod.cambridgecore.org is outside this
session's allowed network domains; it has to be allowed in the session's network settings before Schneider,
Schechter & Shaffer (2023) can be read.

## 1. What share of state effects operations are publicly attributed, how fast, and by whom?

### Takeaway

Most publicly reported cyber operations get some public attribution (65% of 895 operations in 2023; about
56% of 162 in Q2 2026, preliminary), but almost half of those attributions are the attackers' own claims and
only about one in eight comes from a victim government; government attribution rates for incidents in their
own country were 3–17% in 2023. Large destructive state attacks are different: all six cases reviewed here
were attributed, and the lag fell from 7–8 months (2017) to 1–2.5 months (2022–2026), except for the
false-flag case (about 32 months).

### Cited Findings

#### Share attributed

- **65% of publicly reported operations had at least one public attribution; 35% had no attributed
  initiator.** Scope: 895 cyber operations of all kinds (state, criminal, hacktivist) that the European
  Repository of Cyber Incidents (EuRepoC) recorded in 2023, worldwide. Quote: "Almost two-thirds (65%) of
  the cyber operations recorded in 2023 had at least one public attribution reference assigned." and "For
  35% of the operations recorded in 2023 the initiator remains unattributed." Date: briefing "2023 in
  review", PDF created 31 January 2024. Access: full text (PDF text extracted). Kind: measurement (database
  count of publicly reported incidents only). Fit: transfer (all actor types; covert operations that never
  become public are not in the denominator). Input: attribution_now. —
  [EuRepoC Cyber Conflict Briefing 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **About 56% of publicly reported incidents in Q2 2026 were attributed (preliminary).** Scope: 162 new
  operations added in Q2 2026, all actor types; Iran led the attributed states with 13 incidents. Quote: "So
  far, approximately 56% of publicly reported cyber incidents recorded in Q2 have been attributed, with the
  CRINK countries (China, Russia, Iran, and North Korea) once again topping the list". Date: Q2 2026
  briefing, PDF created 23 July 2026. Access: full text. Kind: measurement (provisional; can rise as
  attributions arrive). Fit: transfer. Input: attribution_now. —
  [EuRepoC Cyber Conflict Briefing Q2 2026](https://eurepoc.eu/wp-content/uploads/2026/07/Q2-2026-English-2.pdf)
- **Victim governments made only 12% of the attributions; the US government made 28, Ukraine 13, the UK 7,
  South Korea 6.** Scope: 650 attribution findings on the 2023 operations. Quote: "With 12%, attributions
  from governments/state entities of targeted countries made up a comparatively small share. The United
  States topped the list with 28 attributions, followed by Ukraine (13), the United Kingdom (7), and South
  Korea (6)." Date: January 2024. Access: full text. Kind: measurement. Fit: transfer (all incident types),
  but this is the kind of attribution that can lead to sanctions. Input: attribution_now. —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Government attribution rates of incidents in their own country: Germany 3% (2 of 59), UK 17%, US 11%.**
  Scope: 2023 incidents that targeted entities in each country. Quote: "Germany attributed only 2 out of the
  59 incidents recorded in 2023 that targeted entities within the country." and "UK and US counterparts,
  which clock attribution rates of 17% and 11%, respectively." Date: January 2024. Access: full text. Kind:
  measurement. Fit: transfer (includes crime), the closest measure found of official attribution per
  incident. Input: attribution_now (contradicts 0.7 if the input means official attribution). —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Few public operations are attributed to the US as initiator: 7 operations (1%) in 2023, and four of the
  five state operations were FBI disruption campaigns.** Scope: suspected country of origin of the 895
  operations of 2023. Quote: "United States 7 - 1%" (chart) and "Four of the five recorded operations
  attributed to state/state-affiliated actors from the US were conducted by the FBI, as part of its
  expanding disruption campaigns against criminal and state-sponsored hacking networks." Date: January
  2024. Access: full text. Kind: measurement. Fit: direct for the country that the model is calibrated to,
  but the public record of US operations is censored (covert operations are not counted). Input:
  attribution_now. —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **CFR Cyber Operations Tracker: 34 suspected sponsor states since 2005; China, Russia, Iran and North
  Korea sponsored 77%; 76 operations in 2019, most espionage.** Scope: publicly known state-sponsored
  incidents, 2005–2024 (year filter), updated quarterly. Quote: "thirty-four countries are suspected of
  sponsoring cyber operations", "China, Russia, Iran, and North Korea sponsored 77 percent of all suspected
  operations" and "In 2019, there were a total of seventy-six operations, most being acts of espionage."
  Date: undated live page (read 2026-11-07). Access: fetch extract (the page text has no counts by type or
  by response). Kind: measurement (curated list). Fit: direct. Limit: the tracker lists only operations with
  a suspected state sponsor, so it cannot give the share of operations that is attributed. —
  [CFR Cyber Operations Tracker](https://www.cfr.org/cyber-operations)

#### Speed of attribution

- **Public attribution came on average 10 months after the start of an operation; victim governments took
  12.5 months, IT security firms 10.8, attackers' own claims 1.3.** Scope: attributions of the 2023
  operations, by source; media 15 months, international organisations 13, third parties 12.8, victim
  organisations 5.3. Quote: "public attributions were made, on average, 10 months after the operation's
  recorded start date" and "government entities took an average of 2 months longer than IT community
  companies to attribute cyber operations in which they were the targets." Date: January 2024. Access: full
  text. Kind: measurement. Fit: transfer. Input: timing of sanctions (same-year counting in the escalation
  term). —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Operations with zero-day exploits took 15 months on average to attribute, 5 months more than others.**
  Scope: 22 operations recorded in 2023 that used a zero-day. Quote: "It took on average 15 months to
  publicly attribute incidents with zero days reported in 2023, this is 5 additional months on average
  compared to incidents without zero days." Date: January 2024. Access: full text. Kind: measurement (small
  sample). Fit: transfer; relevant because capable states use more zero-days. —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Disruptive operations become public about 2 months after initial access; espionage-type operations 7.7
  to 12.8 months.** Scope: 2023 operations, months from initial access to public disclosure: all 6,
  disruption 2, ransomware 2.8, data theft 7.7, hijacking without misuse 12.8. Quote: "Operations involving
  disruption and/or ransomware were generally revealed quicker, typically within 2 to 2.8 months" and "data
  theft and/or hijacking without misuse were often reported much later, averaging 7.7 and 12.8 months after
  initial access". Date: January 2024. Access: full text. Kind: measurement. Fit: transfer; directly useful
  for separate surveillance and effects kill chains (exposure comes faster for effects). —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Most attributions come within four months; some take 50 months or more.** Scope: EuRepoC Attribution
  Tracker, attributions from 2022 onward (earlier versions back to 2000). Quote: "The majority of
  attributions occur within the first four months after the start of a cyber incident." and some take "50
  months or longer". Self-attribution and unofficial policy attribution are faster; official policy and legal
  attribution are slower. Date: undated live page. Access: fetch extract (charts not readable). Kind:
  measurement. Fit: transfer. — [EuRepoC Attribution Tracker](https://eurepoc.eu/?p=10917)
- **Case lags for large destructive state attacks (days from attack to first official or national-CERT
  attribution):**
  - WannaCry: UK attribution on 19 December 2017, about 221 days (7.3 months) after the May 2017 outbreak (the
    12 May date is common knowledge, not taken from the page). Quote: "highly likely that North Korean actors
    known as the Lazarus Group". Access: fetch extract. Kind: official statement. Fit: direct. Older (2017).
    — [UK FCO, 19 Dec 2017](https://www.gov.uk/government/news/foreign-office-minister-condemns-north-korean-actor-for-wannacry-attacks)
  - NotPetya: White House attribution on 15 February 2018, 233 days (7.7 months) after the 27 June 2017
    attack (the statement says "June 2017"; the day is common knowledge), which supports the brief's "about
    eight months". Quote: "In June 2017, the Russian military
    launched the most destructive and costly cyber-attack in history." Access: fetch extract. Kind: official
    statement. Fit: direct. Older (2018). —
    [White House, 15 Feb 2018](https://trumpwhitehouse.archives.gov/briefings-statements/statement-press-secretary-25/)
  - Olympic Destroyer: UK attribution on 19 October 2020, about 983 days (32 months) after the 9 February 2018
    opening ceremony (date common knowledge; the page cites the opening ceremony). The false flag (see question
    5) delayed but did not stop attribution. Quote: "almost certainly (95%+)". Access: fetch extract. Kind:
    official statement. Fit: direct. —
    [UK FCDO, 19 Oct 2020](https://www.gov.uk/government/news/uk-exposes-series-of-russian-cyber-attacks-against-olympic-and-paralympic-games)
  - Viasat KA-SAT: joint EU, UK and US attribution on 10 May 2022, 75 days (2.5 months) after the attack of
    24 February 2022. Quote: "it is almost certain Russia was responsible for the subsequent cyber-attack
    impacting Viasat on 24 February" and "the EU, UK, US and other allies have announced today". Access:
    fetch extract. Kind: official statement. Fit: direct. —
    [UK Government, 10 May 2022](https://www.gov.uk/government/news/russia-behind-cyber-attack-with-europe-wide-impact-an-hour-before-ukraine-invasion)
  - Albania: US attribution on 7 September 2022, 54 days after the attack of 15 July 2022. Quote: "We have
    concluded that the Government of Iran conducted this reckless and irresponsible cyberattack". Access:
    fetch extract. Kind: official statement. Fit: direct. —
    [NSC statement, 7 Sep 2022](https://bidenwhitehouse.archives.gov/briefing-room/statements-releases/2022/09/07/statement-by-nsc-spokesperson-adrienne-watson-on-irans-cyberattack-against-albania/)
  - Poland energy sector: CERT Polska's report of 30 January 2026 came 32 days after the attacks of 29
    December 2025. This is a technical attribution to an infrastructure cluster, not a government statement.
    Quote: "this is the first publicly described destructive activity attributed to this cluster." Access:
    full text. Kind: national-CERT technical assessment. Fit: direct. —
    [CERT Polska report, 30 Jan 2026](https://cert.pl/uploads/docs/CERT_Polska_Energy_Sector_Incident_Report_2025.pdf)

#### Who attributes, and joint attributions

- **Of 650 attribution findings in 2023: attackers' own claims 295 (45%), IT security community 227 (35%),
  victim governments 80, third parties 27, media 26, victim organisations 19.** Leading firms: Microsoft 16
  operations, Symantec 8, ESET, Kaspersky and Palo Alto Networks 7 each, Mandiant 6. Quote: "In most cases,
  threat actors directly claimed responsibility n the course of or following an operation (45% of
  attributions)." and "The IT security community was the second most common source of attribution,
  representing 35% of attributions". Date: January 2024. Access: full text. Kind: measurement. Fit:
  transfer (self-claims are mostly ransomware gangs and hacktivists, not capable states). —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Joint government attributions are rare: the 2023 briefing lists nine operations with joint attributions
  by victim governments, out of 895.** My count from the chart "Cyber operations with joint attributions by
  receiver governments in 2023" (Andariel 2; BlackTech, APT28 twice, APT29, Volt Typhoon with the Five Eyes,
  Kimsuky and Lazarus 1 each). The Attribution Tracker says "The majority of attributions are made by a
  single state." Date: January 2024 and undated. Access: full text (briefing); fetch extract (tracker).
  Kind: measurement. Fit: direct for state actors. —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf);
  [EuRepoC Attribution Tracker](https://eurepoc.eu/?p=10917)
- **No joint attribution for an incident that targeted the EU (EuRepoC 2025 report on the EU).** Access:
  search summary only (not read). Kind: measurement as reported. Fit: direct. —
  [EuRepoC Cyber Activity Balance 2025: the EU in focus](https://eurepoc.eu/publication/cyber-activity-balance-2025-the-european-union-in-focus/)
- **States differ on the same incident: in 2026 Dutch intelligence named Russia for phishing over Signal and
  WhatsApp, while the German government had not attributed it.** Quote: "While Dutch intelligence agencies
  explicitly named Russia as the responsible state, the German federal government has not yet officially
  attributed the incident." Date: July 2026. Access: full text. Kind: measurement (case). Fit: direct;
  attribution is a political choice of each state. —
  [EuRepoC Q2 2026](https://eurepoc.eu/wp-content/uploads/2026/07/Q2-2026-English-2.pdf)
- **Egloff & Smeets: public attribution is a strategic choice with risks; they recommend "strategic,
  coordinated pragmatism".** Scope: conceptual framework for government decisions to attribute publicly, no
  counts. Journal of Strategic Studies 46(3), 2023, pp. 502–533; online 10 March 2021. Access: search
  summary only (ETH repository returned HTTP 500 and the publisher HTTP 403, so I did not read the abstract
  myself). Kind: author's framework. Fit: analogy for the model (attribution depends on the victim's
  willingness, not only on technical evidence). —
  [ETH Research Collection entry](https://www.research-collection.ethz.ch/entities/publication/8be4a9bd-c100-4d99-8222-cf5435a46dc2)

### Inferences

- Two different quantities are mixed in one input. Technical exposure or cluster attribution (by firms or a
  national CERT) is common for visible attacks and comes fast. Official attribution by a government, which is
  what triggers sanctions, is rare (12% of findings; 3–17% of incidents per country) and slower (12.5
  months on average in 2023).
- For large, visible, destructive attacks, the default 0.7 is plausible and may be low: the six cases above
  were all attributed. This is a selected sample: famous cases are famous partly because they were
  attributed.
- For the average attack, official attribution is probably far below 0.7. The model at its defaults has
  about 235 × 0.7 ≈ 165 attributed US attacks a year. EuRepoC recorded 28 attributions by US government
  bodies in all of 2023, and only 7 public operations attributed to the US. So, for the model, 0.7 can
  hold only if "attribution" means attribution by the target state, mostly not public, or if most of the
  235 attacks a year are small operations that never become public.
- Attribution has become faster for large attacks: 7–8 months in 2017–2018, 1–2.5 months in 2022–2026. This
  supports counting attributed attacks within the same year, as the escalation term does.
- Exposure is faster for effects operations (about 2 months) than for espionage (7.7–12.8 months). In
  separate kill chains, the chance of exposure per operation should be higher on the effects chain.
- Mapping to attribution_now (0.7; 0.3–0.95): supports the default for technical or cluster attribution of
  significant attacks. It contradicts the default if the input must be the chance of an official
  attribution that triggers a response for a typical attack; for that meaning the evidence points to about
  0.1–0.2, below the range's lower bound of 0.3. A proposal for the report writer: split the input into a
  chance of exposure (which drives defender alertness and burned access) and a chance of official
  attribution (which drives sanctions), or state which of the two the input means.

### Gaps

- CFR counts by type and by sponsor for 2005–2024 were not obtained: the page text has no tallies, and I did
  not fetch the CSV. The brief's figures (719 espionage and 102 effects operations, 2005–2023) remain
  unverified.
- No source gives the share of all state effects operations, including the covert ones that never become
  public, that victims attribute privately. The denominator is unknown.
- No EuRepoC speed-of-attribution figures for 2024–2026 were read; the 2023 briefing is the latest with lag
  numbers.
- Egloff & Smeets was not read beyond a search summary.

## 2. What responses follow attribution, with counts, and what do they cost the attacker?

### Takeaway

Formal responses are few, slow and mostly aimed at individuals and units. The EU had listed 17 individuals
and 4 entities under its cyber sanctions regime by May 2025 (the first listings date from July 2020; that
date was not verified in this pass) and added about 16 more listings in 2026; the DOJ brought 14 indictments of state-linked hackers from 2014 to mid-2019, with 2
enforcement actions. Large packages (the US sovereign-debt directive of 2021, the designation of Iran's
intelligence ministry after the Albania attack of 2022) follow a few high-salience cases and bundle several
activities. I found no source that prices the cost to the attacker.

### Cited Findings

#### EU cyber sanctions

- **17 individuals and 4 entities were listed as of May 2025; the legal framework runs to 18 May 2028.**
  Measures: asset freeze, ban on making funds available, EU travel ban; listings reviewed every 12 months
  (then to 18 May 2026). Quote: "Currently, the restrictive measures apply to 17 individuals and four
  entities." Date: 13 May 2025. Access: secondary (ANI/WAM agency report of the Council release; the Council
  site refused a plain request). Kind: official count, as reported. Fit: direct. Input: sanction_cost. —
  [Tribune India (ANI/WAM), 13 May 2025](https://www.tribuneindia.com/news/world/eu-extends-sanctions-legal-framework-against-cyberattacks)
- **16 March 2026: measures against 3 entities (Implementing Regulation (EU) 2026/589).** Quote: "On 16
  March 2026, the Council of the European Union adopted restrictive measures against 3 entities." A search
  summary of another report says the listing also covered two Chinese individuals who co-founded a company,
  for a total of 19 individuals and 7 entities; I could not read that report (HTTP 403), so this is
  unverified. Access: secondary (policy tracker). Kind: official act, as reported. Fit: direct. —
  [Digital Policy Alert](https://digitalpolicyalert.org/event/38481-council-of-the-european-union-adopted-council-implementing-regulation-eu-2026589-implementing-regulation-eu-2019796-concerning-restrictive-measures-against-cyber-attacks-threatening-the-union-or-its-member-states)
- **13 July 2026: nine Russian individuals and four entities, the first time the EU and the UK sanctioned at
  the same time.** Targets include the bulletproof hosting firm Media Land LLC and its owner. Quote: "On July
  13, 2026, the Council of the European Union Announced sanctions on nine Russian individuals and four
  entities" and "For the first time, the EU and the United Kingdom have adopted sanctions simultaneously".
  Conflict: a Brussels Times report (search summary only) gives eight individuals and four entities under the
  cyber regime plus a GRU officer under the hybrid regime. Date: 17 July 2026. Access: secondary (abstract;
  the rest is paywalled). Kind: official act, as reported. Fit: direct. —
  [IELR, 17 Jul 2026](https://ielr.com/node/9491)

#### US Treasury designations

- **15 April 2021: a directive barring US financial institutions from the primary market for Russian
  sovereign bonds issued after 14 June 2021, and designation of six Russian technology companies that support
  the FSB, GRU and SVR cyber programs.** The release cites SolarWinds (an espionage operation) and GRU
  hack-and-leak operations against elections. Quote: "the 2020 exploit of the SolarWinds Orion platform"
  that "compromised thousands of U.S. government and private sector networks". Access: fetch extract. Kind:
  official act. Fit: direct; note that the largest package followed espionage, not an effects operation. —
  [US Treasury, 15 Apr 2021](https://home.treasury.gov/news/press-releases/jy0127)
- **9 September 2022: designation of Iran's Ministry of Intelligence and Security (MOIS) and its minister
  under E.O. 13694 for the July 2022 attack on Albania, 56 days after the attack.** Quote: actors "assessed
  to be sponsored by the Government of Iran and MOIS disrupted Albanian government computer systems, forcing
  the government to suspend online public services for its citizens." The release states that MOIS was
  already designated under E.O. 13224, 13472 and 13553. Access: fetch extract. Kind: official act. Fit:
  direct; shows saturation (the target was already sanctioned three times). —
  [US Treasury, 9 Sep 2022](https://home.treasury.gov/news/press-releases/jy0941)
- **15 March 2018: Treasury sanctions that cite NotPetya together with election interference.** This is the
  model's existing evidence; not re-read in this pass. Older (2018). —
  [US Treasury, 15 Mar 2018](https://home.treasury.gov/news/press-releases/sm0312)

#### DOJ indictments

- **39 DOJ cyber indictments from 2014 to mid-2019, of which 14 (36%) involved state-backed actors; 2
  enforcement actions (arrest, extradition or conviction) in state cases against 13 in criminal cases.**
  Scope: DOJ press releases. Quote: "Figure 1 shows a total of 39 indictments since 2014." and "Far fewer
  enforcement activities occur (2) when states are implicated versus cyber criminals (13)." The author
  concludes that indictment "alone is not capable of resulting in enforcement or accomplishing deterrence."
  Date: 30 July 2019. Access: fetch extract. Kind: measurement (author's count) and opinion. Fit: direct.
  Older (2019). —
  [Internet Governance Project, 30 Jul 2019](https://www.internetgovernance.org/2019/07/30/are-indictments-in-absentia-an-effective-deterrent-for-cyber-attacks/)
- **Hinck & Maurer: charges against foreign state hackers have grown since 2014; the defendants are
  "unlikely ever to be arrested by U.S. law enforcement".** A search snippet of the full article reads
  "Sixteen of the 24 have come in the Trump administration", but I could not read what the 24 counts (the
  PDF returned HTTP 503). Date: 24 January 2020. Access: fetch extract of the Carnegie summary; search
  summary for the count. Kind: author's analysis. Fit: direct. —
  [Carnegie Endowment, 24 Jan 2020](https://carnegieendowment.org/posts/2020/01/persistent-enforcement-criminal-charges-as-a-response-to-nation-state-malicious-cyber-activity?lang=en)
- **October 2020: US charges against GRU officers of the destructive unit (GTsST, Unit 74455), with the UK
  attribution of the same unit at "almost certainly (95%+)".** The UK page confirms the US charges but not
  their number. Access: fetch extract. Kind: official statement. Fit: direct. —
  [UK FCDO, 19 Oct 2020](https://www.gov.uk/government/news/uk-exposes-series-of-russian-cyber-attacks-against-olympic-and-paralympic-games)

#### Statements, counter-operations and replies to US operations

- **Official statements promise consequences without naming them.** NotPetya: "will be met with
  international consequences" (White House, 15 February 2018; older). Albania: the US "will take further
  action to hold Iran accountable" (NSC, 7 September 2022). Access: fetch extract. Kind: official statement.
  Fit: direct. — [White House, 15 Feb 2018](https://trumpwhitehouse.archives.gov/briefings-statements/statement-press-secretary-25/);
  [NSC, 7 Sep 2022](https://bidenwhitehouse.archives.gov/briefing-room/statements-releases/2022/09/07/statement-by-nsc-spokesperson-adrienne-watson-on-irans-cyberattack-against-albania/)
- **Counter-operations against the attacker's infrastructure.** In 2026, after a UK advisory on APT28 DNS
  hijacking, "US authorities also took operational action to shut down the US portion of the compromised
  router network" (EuRepoC Q2 2026, full text). In 2023, four of the five public US state operations were
  FBI disruption campaigns (EuRepoC 2023, full text). After law-enforcement actions, EuRepoC "did not record
  any incidents involving the notorious Russian hacktivist group NoName057(16) in Q2" 2026. Kind:
  measurement (case records). Fit: direct for the replies of a capable state; the NoName057(16) case is a
  transfer from a proxy group. — [EuRepoC Q2 2026](https://eurepoc.eu/wp-content/uploads/2026/07/Q2-2026-English-2.pdf);
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **Replies to US operations are public accusations.** In October 2025 China's Ministry of State Security
  accused the NSA of attacks on the National Time Service Center, with 42 types of "special cyberattack
  weapons"; the NSA "did not confirm nor deny" (news reports). An opinion piece says Harbin police named three
  NSA agents after the Asian Winter Games of April 2025. Access: search summary only (not read). Kind: an
  adversary's official accusation as reported, and opinion. Fit: direct for a US attacker, unverified. —
  [Arab News](https://www.arabnews.com/node/2619423/world); [IPS opinion piece](https://ipsnews.net/business/?p=237129)

### Inferences

- Formal sanctions are rare compared with attributed attacks. The EU made 21 listings by May 2025, about 4 a
  year for all attacker states together if the listings began in July 2020 (a start date not verified
  here); the model at its defaults has about 165 attributed
  attacks a year by one state. So most attributed attacks draw no formal sanction, and the formal responses
  are rare events that bundle many activities (2018: elections and NotPetya; 2021: SolarWinds and elections).
- Arithmetic on the model's defaults (identity, not evidence): one attack uses about 42,500 × 0.083 / 235 ≈
  15 expert-years. At sanction_cost 10, the expected sanction per attack is 0.7 × 10 = 7 expert-years of
  surveillance value, and the yearly total is 1,645, or 4.2% of the yearly surveillance value of about
  38,970 experts. At 100 these become 70 per attack and 42% a year; at 1, 0.7 per attack and 0.4% a year.
- The evidence (rare listings, individuals who never travel, re-designation of bodies already sanctioned,
  indictments without arrest) suggests that for routine attacks the mean cost per attributed attack lies in
  the lower half of the range (1 to 10), with a heavy tail: a few salient attacks draw large packages. This
  neither supports nor contradicts the default 10 with a measurement. A proposal: make sanction_cost depend
  on the severity or visibility of the attack, or treat large packages as rare events.
- For the US as the attacker, the states most likely to attribute US effects operations (China, Russia,
  Iran) cannot impose effective financial sanctions on the US. The observed reply is public naming. The real
  cost is more likely to come as counter-operations and as lost trust of allies, which the model calls
  "replies"; no source measures either.
- Real responses also follow espionage (SolarWinds) and respond to the pattern of behaviour, not to single
  attacks. The model charges political cost only on effects attacks.

### Gaps

- No estimate of the cost to the attacker of any response, in currency or in lost capability.
- The counts of GRU officers charged in July 2018, October 2018 and October 2020 were not verified (the DOJ
  page returned no text). My recollection (12, 7 and 6 officers) is unverified and is not used above.
- The composition of the EU listings of 2020–2025 by attack (for example WannaCry, NotPetya, Cloud Hopper,
  the OPCW attempt, the Bundestag hack, Estonia) was not verified: the Council pages refused a plain
  request.
- Expulsions were not verified: the page on the US measures of December 2016 returned 404, and so did the
  Dutch page on the OPCW operation of 2018. Albania's reported break of diplomatic relations with Iran
  (September 2022) is not in the NSC statement and was not verified.
- No total of OFAC designations under the cyber authorities (E.O. 13694) was found.

## 3. Do responses grow with the number or the severity of attacks (escalation)?

### Takeaway

Surveys and wargames show restraint. Escalation is the least chosen response (US 9.9%, Russia 15.8%, Israel
5.5% of 2,993 respondents); support for airstrikes after a cyberattack is 34% against almost 57% after an
equivalent conventional attack; Lonergan & Lonergan find that cyber operations did not escalate conflicts in
2005–2020. Severity, in particular casualties, raises support for retaliation. No study found measures whether
responses grow with the number of attacks; NATO says cumulative activity "might" amount to an armed attack,
which is a threshold, not a steady rise.

### Cited Findings

- **Cross-national survey experiment: escalation was the least chosen posture; US respondents 39.0%
  de-escalate, 51.2% proportional, 9.9% escalate; Russia 51.0%, 33.2%, 15.8%; Israel 47.1%, 47.4%, 5.5%.**
  Scope: YouGov, 1,000 adults each in the US, Russia and Israel, December 2018 to January 2019, 2,993 valid
  responses, fictional crisis with and without a cyber trigger and cyber response options. Quote:
  "escalatory responses were the least frequently occurring posture across each country" and "the presence
  of cyber triggering events and cyber response options did not seem to alter escalation preferences
  outside of Russia." Date: November 2019. Access: full text (PDF text extracted). Kind: measurement
  (survey experiment). Fit: transfer (public opinion, not decision makers). Older (2018–2019 data). Input:
  escalation. — [Jensen & Valeriano, Atlantic Council](https://www.atlanticcouncil.org/wp-content/uploads/2019/11/What_do_we_know_about_cyber_escalation_.pdf)
- **Wargames: officials were reluctant to escalate and used offensive cyber only after conventional
  strikes.** Scope: UC Berkeley CLTC simulations (2016) and Schneider's analysis of war games of 2011–2016,
  as reported by Jensen & Valeriano. Quote: "participants were reluctant to use high-end offensive cyber
  capabilities even during militarized disputes" and "Schneider found that participants only used offensive
  cyber capabilities after conventional military strikes". Date: November 2019. Access: full text of the
  brief (secondary report of the wargames). Kind: measurement (wargame observation). Fit: transfer (games,
  not real crises). Older. —
  [Jensen & Valeriano, Atlantic Council](https://www.atlanticcouncil.org/wp-content/uploads/2019/11/What_do_we_know_about_cyber_escalation_.pdf)
- **Kreps & Schneider: a "firebreak" between cyber and other attacks; 34% support for airstrikes after a
  cyberattack against almost 57% after an equivalent conventional attack; the cyber scenario never reached a
  majority for any effect.** Scope: Amazon Mechanical Turk sample of US adults, about 1,061 observations,
  fielded 4–8 August 2017; attack on a power plant, by cyber, conventional or nuclear means, with economic,
  casualty or radiation effects. Quote: "For no type of effect did the cyber scenario reach a majority of
  support (over 50%)" and "a difference in support between 34% for cyber and almost 57% for the equivalent
  attack perpetrated by a conventional weapon". Casualties, compared with economic damage, raised support
  for strikes (values only in a figure). Date: 29 September 2019. Access: fetch extract of the open article
  (first part of the page; figures not read). Kind: measurement (survey experiment). Fit: transfer (US
  public; for a US attacker, the relevant public is the victim's). Older (2017 data). Input: escalation
  (severity, not number). —
  [Kreps & Schneider, Journal of Cybersecurity](https://academic.oup.com/cybersecurity/article/5/1/tyz007/5575971)
- **Later survey work contests the firebreak when cyberattacks kill people.** A 2024 article reports that
  studies by Kreps and Das and by Gross and colleagues found that lethal cyberattacks drew a forceful
  response like conventional attacks. Access: search summary only (not read). Kind: author's review of
  experiments. Fit: transfer. — [International Interactions, 2024](https://informahealthcare.com/doi/full/10.1080/03050629.2024.2310014)
- **Lonergan & Lonergan (2023): cyber operations have not escalated conflicts; the need to attribute slows
  responses and breaks escalatory cycles.** Scope: theory, US case studies and a dataset of publicly
  reported incidents of 2005–2020, as described by the reviewers. Quote (from the book, quoted by
  reviewers): "attribution requirements place a pause on response times, they inject a break into a
  potential escalatory cycle"; "offensive cyber operations are challenging, unreliable, and limited in their
  decisiveness" (p. 78); "cyber operations constitute signals of a willingness to avoid escalation". The
  reviews do not say whether responses grow with the number or severity of attacks. Date: roundtable 6
  December 2024; book 2023. Access: secondary (scholarly reviews), fetch extract. Kind: authors' findings.
  Fit: direct (state rivals). Input: escalation. —
  [H-Diplo/ISSF Roundtable 16-17](https://issforum.org/roundtables/h-diplo-rjissf-roundtable-16-17-on-lonergan-and-lonergan-escalation-dynamics-in-cyberspace)
- **NATO doctrine: cumulative cyber activity might amount to an armed attack, decided case by case.**
  Quote: "significant malicious cumulative cyber activities might, in certain circumstances, be considered
  as amounting to an armed attack" and the decision on Article 5 is taken "on a case-by-case basis". Date:
  Brussels Summit Communiqué, 14 June 2021, paragraph 32. Access: fetch extract. Kind: official doctrine.
  Fit: direct (an alliance response rule). Input: escalation (supports a rise with accumulated attacks, in a
  threshold form). — [NATO Brussels Summit Communiqué](https://www.nato.int/cps/en/natohq/news_185000.htm)
- **Sanctions saturate on a target already sanctioned.** Iran's MOIS was designated for the Albania attack
  in 2022 after earlier designations under three other executive orders (see question 2). Access: fetch
  extract. Kind: official act. Fit: direct. —
  [US Treasury, 9 Sep 2022](https://home.treasury.gov/news/press-releases/jy0941)

### Inferences

- The default escalation of 0 is consistent with the surveys, the wargames and the historical record, which
  show restraint after cyberattacks. These sources test severity and means, not the number of attacks.
- The upper part of the range is very strong at today's tempo. With about 164.5 attributed attacks a year,
  the cost multiplier 1 + escalation × attributed attacks is 17.45 at 0.1, 2.65 at 0.01 and 1.16 at 0.001
  (arithmetic on the model's defaults). No evidence found shows responses that grow seventeenfold with
  tempo. A proposal: narrow the range to about 0 to 0.01, or replace the linear term with a threshold term
  for cumulative harm (NATO's wording), and add a term for severity (casualties raise support for
  retaliation).
- The marginal cost of an attributed attack can also fall with the number of attacks: the same units and
  ministries are sanctioned again, and responses bundle many attacks. The sign of the escalation term is
  uncertain; the range 0–0.1 excludes the falling case.
- Attribution lags act as a brake on escalation (Lonergan & Lonergan). With AI-faster attribution (question
  5), this brake may weaken; no source measures that effect.

### Gaps

- Schneider, Schechter & Shaffer, "Hacking Nuclear Stability" (International Organization, 2023), a large
  wargame on cyber and escalation, was not read: core-prod.cambridgecore.org is outside the allowed network
  domains of this session.
- No dataset links the size of responses to the number of attributed attacks per year by the same state.
- The Kreps & Schneider results by casualty level are only in a figure that I did not read.

## 4. Collateral damage and blowback, and how they enter decisions

### Takeaway

Attacks that spread beyond the target were attributed by coalitions and drew the strongest statements and
sanctions: NotPetya (more than $10 billion of damage; it struck Russia's own Rosneft), WannaCry (300,000
computers in 150 countries) and Viasat (wind farms and internet users in central Europe). Spill-over makes
more states into victims, which raises the chance and the speed of joint attribution. The literature names
unpredictable effects as a main limit of cyber operations. No source measures how collateral damage enters
the attacker's decisions.

### Cited Findings

- **WannaCry: 300,000 computers in 150 countries, including 48 NHS trusts; attributed by the UK to North
  Korea's Lazarus Group.** Quote: "one of the most significant to hit the UK in terms of scale and
  disruption" (the figures are from the same page). Date: 19 December 2017. Access: fetch extract. Kind:
  official statement. Fit: direct. Older (2017). —
  [UK FCO, 19 Dec 2017](https://www.gov.uk/government/news/foreign-office-minister-condemns-north-korean-actor-for-wannacry-attacks)
- **NotPetya: "the most destructive and costly cyber-attack in history"; more than $10 billion of damage by a
  White House estimate; the attack spread back to Russia and struck Rosneft.** Quote (White House): "In June
  2017, the Russian military launched the most destructive and costly cyber-attack in history." The damage
  figure and Rosneft come from WIRED, which is the model's existing evidence and was not re-read in this
  pass. Date: 15 February 2018; WIRED 21 August 2018. Access: fetch extract (White House). Kind: official
  statement; journalism citing an official estimate. Fit: direct. Older (2017–2018). —
  [White House, 15 Feb 2018](https://trumpwhitehouse.archives.gov/briefings-statements/statement-press-secretary-25/);
  [WIRED, 21 Aug 2018](https://www.wired.com/story/notpetya-cyberattack-ukraine-russia-code-crashed-the-world/)
- **Viasat: the attack on the Ukrainian military spilled over to "wind farms and internet users in central
  Europe"; "tens of thousands of terminals have been damaged, made inoperable and cannot be repaired";
  attributed jointly by the EU, the UK, the US and other allies 75 days later.** Date: 10 May 2022. Access:
  fetch extract. Kind: official statement. Fit: direct. —
  [UK Government, 10 May 2022](https://www.gov.uk/government/news/russia-behind-cyber-attack-with-europe-wide-impact-an-hour-before-ukraine-invasion)
- **Olympic Destroyer: judged "almost certainly sabotage"** of the 2018 Winter Games, attributed at 95%+ to
  GRU Unit 74455. Date: 19 October 2020. Access: fetch extract. Kind: official statement. Fit: direct. —
  [UK FCDO, 19 Oct 2020](https://www.gov.uk/government/news/uk-exposes-series-of-russian-cyber-attacks-against-olympic-and-paralympic-games)
- **Unpredictable effects limit cyber operations: some spill over (NotPetya), others have limited effect
  (Stuxnet).** A reviewer paraphrases the book's point that "one of the key limitations of cyber operations
  is their unpredictability". Date: 6 December 2024. Access: secondary, fetch extract. Kind: authors'
  argument. Fit: direct. —
  [H-Diplo/ISSF Roundtable 16-17](https://issforum.org/roundtables/h-diplo-rjissf-roundtable-16-17-on-lonergan-and-lonergan-escalation-dynamics-in-cyberspace)

### Inferences

- Collateral damage raises both the chance and the cost of attribution: the attacks with wide spill-over
  (WannaCry, NotPetya, Viasat) were attributed by coalitions, and the political cost spreads to the states
  of the collateral victims.
- In the model, AI raises the targets per attack from 1 to 30. More targets per attack means more victims
  and more states that can attribute, which may offset part of the fall in attribution that the model
  assumes. A proposal: make the chance of attribution, or sanction_cost, rise with the targets or the
  collateral damage per attack.
- Blowback on the attacker itself (Rosneft) is a direct cost that the model does not represent; it is
  separate from sanctions.

### Gaps

- No quantitative study found of how collateral damage changes the attacker's decision or the size of the
  response.
- The damage to Rosneft was not quantified in the sources read.
- Declassified US records on collateral-effects reviews (for example Operation Glowing Symphony against ISIS)
  were not searched because the search budget ran out.

## 5. How does AI change attribution, and at which stage of an operation does attribution evidence arise?

### Takeaway

Up to November 2026, every AI-assisted state operation found was still attributed, at least to a cluster or a
"nexus", and often with high confidence (a selected sample: a report calls an operation a state operation
only after it attributes it). AI removes tool fingerprints (CERT Polska: an LLM-written wiper
"cannot be used in attribution") and gives groups a fresh profile, but attribution rests mostly on
infrastructure, time zone, language, victimology, operational security errors and, now, the telemetry of AI
providers. The evidence supports a moderate fall of tool-based attribution, not a collapse. It does not
support attribution_end as low as 0.05; 0.4 is a pessimistic but plausible value.

### Cited Findings

#### AI-written malware and its attribution

- **CERT Polska, Poland, 29 December 2025: an LLM probably wrote most of one wiper (LazyWiper), which
  therefore gave no attribution evidence; the attribution came from infrastructure.** Scope: coordinated
  destructive attacks on "numerous wind and solar farms, a private company in the manufacturing sector, and
  a combined heat and power (CHP) plant supplying heat to nearly half a million customers". Quotes: "The LazyWiper script was likely generated
  largely by an LLM and does not contain distinctive features. For this reason, it cannot be used in
  attribution."; the overwrite function "contains nonsensical comments that would likely not be written by
  a human developer"; "the infrastructure used to obtain initial access, exfiltrate data, establish VPN
  tunnels for wiper malware deployment, and damage the server's RAID array disks overlaps with the 'Static
  Tundra' infrastructure"; for the second wiper, DynoWiper, "the level of similarity is too low to
  attribute DynoWiper to previously used wiper families"; and CERT Polska "cannot conclusively determine
  whether the actor behind the 'Sandworm' activity cluster participated in the attack to any extent."
  Access before the attack: at the plant, "the attacker's first activities took place between March and
  May of 2025", and "The destructive attack was preceded by a long‑term infiltration of the infrastructure
  and the theft of sensitive information". Date: 30 January 2026. Access: full text (46-page PDF,
  extracted). Kind: national-CERT technical assessment. Fit: direct. Input: attribution_end (limits a large
  fall). — [CERT Polska report](https://cert.pl/uploads/docs/CERT_Polska_Energy_Sector_Incident_Report_2025.pdf);
  [summary page](https://cert.pl/en/posts/2026/01/incident-report-energy-sector-2025/)
- **Google GTIG, May 2026: suspected Russia-nexus actors used LLM-generated decoy code in malware against
  Ukraine; LLM code style is itself recognisable.** Quotes: "Russia-nexus intrusion activity targeting
  Ukrainian organizations to deliver AI-enabled malware" (CANFAIL, LONGSTREAM); CANFAIL has LLM comments on
  code "likely incorporated as filler content designed to obfuscate malicious activity"; LONGSTREAM has "32
  instances of the code querying the system's daylight saving status"; and "AI-driven coding has
  accelerated the development of infrastructure suites and polymorphic malware by adversaries." For a
  criminal zero-day, GTIG has "high confidence that the actor leveraged an AI model", based on signs such as
  "a hallucinated CVSS score". The page does not say whether AI made attribution harder. Date: 11 May 2026.
  Access: fetch extract. Kind: vendor threat intelligence (measurement of cases). Fit: direct. —
  [GTIG AI Threat Tracker, 11 May 2026](https://cloud.google.com/blog/topics/threat-intelligence/ai-vulnerability-exploitation-initial-access)
- **GTIG, May 2026: a Chinese state actor used Gemini to build software for an anonymising relay network.**
  Quote: APT27 "has leveraged Gemini to accelerate the development of a fleet management application likely
  to support the management of an operational relay box (ORB) network." This is AI applied to the
  infrastructure stage, the stage that gave the Polish attribution; the activity itself was attributed
  through the AI provider's telemetry. Date: 11 May 2026. Access: fetch extract. Kind: vendor threat
  intelligence. Fit: direct. —
  [GTIG, 11 May 2026](https://cloud.google.com/blog/topics/threat-intelligence/ai-vulnerability-exploitation-initial-access)
- **GTIG, November 2025: Russia's APT28 used malware that queries an LLM in live operations, and it was still
  attributed to APT28.** Quote: "APT28's use of PROMPTSTEAL constitutes our first observation of malware
  querying an LLM deployed in live operations" (reported by CERT-UA as LAMEHUG). Another family, PROMPTFLUX,
  was "unattributed to a specific threat actor". GTIG calls the capabilities "still nascent". Date: 5
  November 2025. Access: fetch extract. Kind: vendor threat intelligence. Fit: direct. —
  [GTIG AI Threat Tracker, 5 Nov 2025](https://cloud.google.com/blog/topics/threat-intelligence/threat-actor-usage-of-ai-tools)
- **Anthropic, November 2025: AI did 80–90% of an espionage campaign, and Anthropic still attributed it with
  high confidence to a Chinese state-sponsored group.** Quotes: the campaign was run by a group that Anthropic
  assesses "with high confidence was a Chinese state-sponsored group"; the actor could "use AI to perform
  80-90% of the campaign"; it attempted "roughly thirty global targets" and "succeeded in a small number of
  cases"; "The barriers to performing sophisticated cyberattacks have dropped substantially." The page does
  not say what evidence the attribution used. Date: 13 November 2025. Access: fetch extract. Kind: AI
  developer's incident report. Fit: direct for espionage; transfer to effects operations. —
  [Anthropic, 13 Nov 2025](https://www.anthropic.com/news/disrupting-AI-espionage)
- **WithSecure, May 2026: a Russia-nexus group (GREYVIBE) used AI for lures, malware and commands, which gave it "a largely
  fresh operational profile that complicates tracking and attribution", yet WithSecure attributed it with
  high confidence through time zone, language and victimology.** Quotes: AI use is "integrated throughout
  operations, not used in isolation"; "High-confidence attribution to Russian-speaking operators in the
  Moscow time zone"; "Repeated operational security failures"; "design flaws in LLM-assisted malware allowed
  WithSecure to monitor" the group across victim machines for several months. Date: 28 May 2026. Access:
  fetch extract. Kind: vendor threat intelligence. Fit: direct (a state-aligned, low-to-moderate
  sophistication group). — [WithSecure, 28 May 2026](https://www.withsecure.com/en/resources-hub/w-labs/10919/)
- **OpenAI, October 2025: three coordinated efforts from Russia, North Korea and China used ChatGPT for
  malware and phishing; the models often refused direct malicious requests; one cluster's code overlapped
  with the known malware GOVERSHELL and HealthKick.** Access: search summary only (not read). Kind: AI
  developer's report, as summarised. Fit: direct. —
  [eSecurity Planet](https://www.esecurityplanet.com/de/news/chatgpt-cyberattacks/)

#### False flags

- **Olympic Destroyer (2018): the attackers forged a compiler artefact to point at North Korea's Lazarus
  group; vendors first pointed at China, North Korea or Russia; the forgery was found in about a month.**
  Quote: "the set of features was simply forged to perfectly match the fingerprint used by Lazarus" and
  "don't rush with attribution". Date: 8 March 2018. Access: fetch extract. Kind: vendor analysis. Fit:
  direct. Older (2018). —
  [Kaspersky Securelist, 8 Mar 2018](https://securelist.com/olympicdestroyer-is-here-to-trick-the-industry/84295/)
- **The UK later attributed Olympic Destroyer to the GRU at 95%+ and stated the false flag.** Quote: the
  GRU's cyber unit "attempted to disguise itself as North Korean and Chinese hackers". The official
  attribution came about 32 months after the attack. Date: 19 October 2020. Access: fetch extract. Kind:
  official statement. Fit: direct. —
  [UK FCDO, 19 Oct 2020](https://www.gov.uk/government/news/uk-exposes-series-of-russian-cyber-attacks-against-olympic-and-paralympic-games)
- **Contested attributions are rare: five incidents in 2023, including "an alleged Ukrainian false-flag
  operation masquerading as the Russian Wagner group".** Quote: "Only five incidents added in 2023 included
  contested attributions/information". Date: January 2024. Access: full text. Kind: measurement. Fit:
  transfer. —
  [EuRepoC 2023](https://eurepoc.eu/wp-content/uploads/2024/01/EuRepoC-Cyber-Conflict-Briefing-2023-Cyber-Activity-Balance.pdf)
- **States hide behind criminal personas.** Quote: the link between Chaos ransomware and the Iranian group
  MuddyWater "once again underscored the fact that what appear to be criminal ransomware attacks may in
  reality be the work of state-affiliated actors." Date: July 2026. Access: full text. Kind: case record.
  Fit: direct. — [EuRepoC Q2 2026](https://eurepoc.eu/wp-content/uploads/2026/07/Q2-2026-English-2.pdf)
- **Opinion: AI may make state hackers impossible to tell from teenage criminals and make false flags
  easier** (Alistair Macrae, an investigator of the 2011 PlayStation Network breach). Access: search summary
  only. Kind: opinion. Fit: analogy. —
  [Cybernews](https://cybernews.com/ai-news/ai-hackers-identification-attribution/)

#### Stage of an operation where attribution evidence arises (from the cases above)

| Stage | Evidence | Cases | What AI does to it |
|---|---|---|---|
| Building tools | Code similarity, compiler artefacts, coding style | DynoWiper similarity "too low"; Olympic Destroyer forged artefact | Removes distinctive features (LazyWiper), refreshes profiles (GREYVIBE), adds decoy code (CANFAIL, LONGSTREAM). LLM style reveals AI use, not the user. |
| Use of AI services | Account telemetry at the AI provider | Anthropic (high confidence, Chinese state group); GTIG (named state groups using Gemini) | A new source of attribution; an attacker that uses its own models avoids it. |
| Infrastructure: initial access, command and control, exfiltration, relays | Overlap with infrastructure of known clusters | CERT Polska: initial access, exfiltration and VPN tunnels overlap with Static Tundra | AI helps build relay networks (APT27); this could erode the stage later. |
| Effects | Visible damage, target choice, timing | Disruptions become public in about 2 months (EuRepoC 2023) | More targets per attack means more victims who look. |
| People | Time zone, language, operational security errors | GREYVIBE: Moscow time zone, Russian-speaking operators, repeated errors | Fewer human steps (80–90% AI in the Anthropic case), but LLM-made flaws exposed GREYVIBE. |
| Strategic context | Victimology, fit with state aims | GREYVIBE; CERT Polska (the actor's known interest in energy) | Not changed by AI. |

Sources for the table: the findings above.

### Inferences

- The surveillance chain and the effects chain expose their operator at different stages. Espionage is
  found late, often "uncovered, for example, through telemetry data" (EuRepoC Q2 2026), on average 7.7–12.8
  months after access. Effects show at once (about 2 months). In the Polish case the destructive attack was
  built on months of access and data theft, and its attribution came from infrastructure that overlapped with
  a cluster known for espionage, this being "the first publicly described destructive activity attributed to
  this cluster." So an effects attack on access shared with surveillance inherits the exposure of the
  surveillance infrastructure.
- The model lowers the share of attacks run on access shared with surveillance from 70% to 20%. By the
  inference above, that change lowers attribution on its own, separately from AI-written code. The model
  could link the chance of attribution to the share of shared access, stage by stage, as 1 − Π(1 − p_stage).
- AI lowers the evidence from tools; it raises the evidence from AI services and from defenders' use of AI;
  it leaves people and strategic context mostly unchanged. The net direction is uncertain. In every 2025–2026
  case found, attribution still reached a state or a nexus.
- Mapping to attribution_end (0.4; 0.05–0.95): the evidence narrows the range. The lower bound 0.05 has no
  support; 0.4 is pessimistic but plausible for tool-based and official attribution; the upper bound 0.95 is
  plausible if the telemetry of AI providers and defenders' AI dominate.

#### Consolidated mapping to the model's inputs

| Input | Default and range | Main evidence | Verdict |
|---|---|---|---|
| attribution_now | 0.7; 0.3–0.95 | 65% (2023) and about 56% (Q2 2026) of public incidents have some attribution; only 12% of attributions come from victim governments; government rates 3–17%; all six large destructive cases attributed, in 1–32 months | Supports 0.7 for technical or cluster attribution of significant attacks. Contradicts 0.7 if the input means official attribution of a typical attack (about 0.1–0.2, below the range). State the meaning or split the input. |
| attribution_end | 0.4; 0.05–0.95 | CERT Polska, GTIG, WithSecure, Anthropic: AI-assisted state operations still attributed; AI removes tool evidence only | Narrows: lower bound unsupported; 0.4 pessimistic but plausible; the fall could be smaller, or attribution could rise. |
| sanction_cost | 10; 1–100 expert-years of surveillance value per attributed attack | Rare and mostly symbolic listings (about 4 a year in the EU, 2020–2025); 14 state indictments in five years with 2 enforcement actions; large packages after a few salient cases; no cost estimate | No measurement supports or contradicts 10. Weakly favours the lower half for routine attacks, with a heavy tail. Consider severity dependence. |
| escalation | 0; 0–0.1 per attributed attack in a year | Surveys, wargames and history show restraint; NATO's cumulative threshold; sanctions saturate | Supports 0. The upper end gives a seventeenfold cost at today's tempo, which no evidence supports. Consider 0–0.01, a threshold form, or a severity term. |

### Gaps

- No measurement of the chance of attribution as a function of AI use: the cases are few, recent and
  selected (published reports describe attributed cases).
- No primary OpenAI report of 2025–2026 was read; the October 2025 report is known here only from a search
  summary.
- The CERT-UA report on LAMEHUG and its confidence wording was not read.
- Whether the EU listings of July 2026 cover the Polish attacks of December 2025 was not checked.
- No source quantifies how often attribution rests on each stage (infrastructure, tools, timing, human
  error) across many cases. The stage table rests on six case reports.
