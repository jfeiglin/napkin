# Surveillance (espionage) operations chain: stages, scale, AI and the equities trade-off

Notes for the model of one capable state (calibrated to the US) that splits about 42,500 cyber experts between surveillance and effects, 2026–2051. Compiled 2026-11-07.

How to read the tags at the end of each finding:
- **Read** says how I read the source. *primary-full* means I read the whole primary text, or all of its relevant sections. *primary-part* means I read named parts of the primary, such as the blog summary of a longer report. *repost* means a free full-text repost of the primary. *secondary* means a free report about the primary. *snippet* means I saw only a search-result summary and did not open the page. Snippets are the weakest level; do not quote them as fact without a check.
- **Type** is one of: *measurement* (a count or an observation), *official figure* (a budget, a plan or an agency statement), *estimate* (an author's estimate) or *opinion*.
- **Applies** says how the finding applies to a capable state's cyber force. *direct* means it is about such a force. *transfer* means it comes from another field or another kind of actor. *analogy* means only a likeness.
- **(older)** marks data from before 2020.
- **Access:** plain requests to washingtonpost.com, nsa.gov, apps.dtic.mil, washingtontimes.com and securityweek.com returned HTTP 403. For each of these I used the free repost or secondary report named in the line.
- **Search limit:** the shared web-search budget ran out before I could search for Buchanan, Smeets, newer SSSCIP reports, the ODNI Section 702 statistics and Rob Joyce's 2016 talk. These are listed under Gaps.
- **Quotes:** quotes come from the page text as the fetch tool or my own PDF text extraction gave it. Wording marked "(paraphrase)" is the tool's summary, not the source's words.

## 1. Stages of an espionage operation, how they differ from an effects operation, and where the bottleneck is

### Takeaway
An espionage chain runs from target selection through access, persistence, collection and exfiltration to processing, analysis and dissemination, and it gives value in every year the access lives. In the best US data (leaked 2011–2013 budget documents), human operator time and downstream processing limited the chain, not access: GENIE fully used only 8,448 of 68,975 implanted machines (12%) with 1,870 staff. An effects chain shares the access stages. It then replaces collection with a hold-and-trigger stage, reveals itself at the effect, and needs intelligence support to assess the result. Detected espionage intrusions stay hidden about nine times longer than the average intrusion: a median of 122 days against 14 days in Mandiant's 2025 caseload.

### Cited Findings

**Stage structure**
- One documented state espionage campaign in six phases: "Phase 1: Campaign initialization and target selection", "Phase 2: Reconnaissance and attack surface mapping", "Phase 3: Vulnerability discovery and validation", "Phase 4: Credential harvesting and lateral movement", "Phase 5: Data collection and intelligence extraction", "Phase 6: Documentation and handoff". The intrusions "progressed through reconnaissance, initial access, persistence, and data exfiltration phases". Scope: GTG-1002, which Anthropic assesses "with high confidence" to be a Chinese state-sponsored group; one campaign, September 2025. — [Anthropic, full report, "Disrupting the first reported AI-orchestrated cyber espionage campaign"](https://assets.anthropic.com/m/ec212e6566a0d47/original/Disrupting-the-first-reported-AI-orchestrated-cyber-espionage-campaign.pdf) [November 2025, changelog 17 Nov 2025; Read: primary-full (my text extraction of the PDF); Type: measurement (incident analysis by the AI provider); Applies: direct (state actor), but one campaign run on a commercial AI platform]
- Pre-positioning for effects is a different chain. Volt Typhoon's activity "is not consistent with traditional cyber espionage or intelligence gathering operations". The actors "pre-position themselves on IT networks for disruptive or destructive cyberattacks". They "exhibit minimal activity within the compromised environment". They "primarily collect information that would facilitate follow-on actions with physical impacts", for example OT diagrams of SCADA systems, relays and switchgear (paraphrase). They kept "access and footholds within some victim IT environments for at least five years". Scope: PRC actors in US critical infrastructure. — [CISA et al., Advisory AA24-038A](https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a) [7 Feb 2024; Read: primary-part (first 100,000 of 132,000 characters); Type: official assessment from forensics; Applies: direct (a capable state)]
- An effect needs surveillance support to assess its result. For Operation Glowing Symphony (US against ISIS, approved November 2016), coordination was needed "to allow intelligence agencies to prepare collection assets for gathering indicators of success". — [National Security Archive, Briefing Book #693](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2020-01-21/uscybercom-after-action-assessments-operation-glowing-symphony) [21 Jan 2020, documents from 2016–2017 (older); Read: secondary (the Archive's summary of declassified assessments; I did not read the documents); Type: official assessment; Applies: direct (US)]

**Scale and cost: GENIE and the FY2013 budget (older)**
- "U.S. intelligence services carried out 231 offensive cyber-operations in 2011". "Of the 231 offensive operations conducted in 2011, the budget said, nearly three-quarters were against top-priority targets". Offensive operations were defined (October 2012 presidential directive) as activities "to manipulate, disrupt, deny, degrade, or destroy information resident in computers or computer networks". — [Washington Post (Gellman and Nakashima), read through the free Atlantic Council repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/) ([original, which refused a plain request](https://www.washingtonpost.com/world/national-security/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/2013/08/30/d090a6ae-119e-11e3-b4cb-fd7ce041d814_story.html)) [30 Aug 2013, repost 31 Aug 2013 (older); Read: repost; Type: official figure (leaked FY2013 budget justification, as journalists reported it); Applies: direct (US)]
- GENIE, the computer network exploitation program, in the same article:
  - "the $652 million project has placed 'covert implants,' sophisticated malware" on "tens of thousands of machines every year".
  - "By the end of this year, GENIE is projected to control at least 85,000 implants". "That is quadruple the number — 21,252 — available in 2008".
  - "Even with a staff of 1,870 people, GENIE made full use of only 8,448 of the 68,975 machines with active implants in 2011."
  - Growth "limited until recently by the need for human operators to take remote control" of compromised machines.
  - "the NSA has brought online an automated system, code-named TURBINE, that is capable of managing 'potentially millions of implants'" for intelligence gathering and "active attack".
  — [same repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/) [(older); Type: official figures from the budget, the 85,000 being a plan; Applies: direct (US)]
- FY2013 budget split. Network defense is "a task that absorbs roughly one-third of a total cyber operations budget of $1.02 billion in fiscal 2013". The Remote Operations Center's break-in mission "spends nearly twice as much: $651.7 million". "$25.1 million" went to covert purchases of software vulnerabilities from private vendors (paraphrase of the rest of the sentence). All values are nominal FY2013 USD. — [same repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/) [(older); official figures; direct]
- Conflicting scope: secondary coverage of the same leaked budget gives "$4.3 billion" for "conducting cyber operations" across the intelligence community ([NBC News, snippet](https://www.nbcnews.com/news/amp/wbna52877497)). FCW reported that NSA received about $1 billion for "computer network operations" ([Defense Systems/FCW, snippet](https://defenseone.com/defense-systems/2013/09/leaked-nsa-documents-shed-little-light-on-cybersecurity-spending/192347)). [2013 (older); Read: snippet; the two figures likely have different scopes]
- Implant history. In 2004 "the agency was managing a small network of only 100 to 150 implants". Over the next six to eight years "the number of implants soared to tens of thousands". TURBINE was meant to "allow the current implant network to scale to large size (millions of implants)" by "automated control implants by groups instead of individually". A 2009 NSA presentation said: "Human 'drivers' limit ability for large-scale exploitation." — [The Intercept (Gallagher and Greenwald)](https://theintercept.com/2014/03/12/nsa-plans-infect-millions-computers-malware/) [12 Mar 2014 (older); Read: primary-part (the journalists' report of leaked documents); Type: official internal documents; Applies: direct (US)]

**Processing and analysis volumes (older)**
- Internal NSA SIDtoday writing, 2010–2012:
  - "I was told that there are 2 petabytes of data in the SIGINT System at any given time" (2011 interview with a SIGINT Directorate deputy director). The same interview expected about 1 terabyte per second of incoming data by the end of 2011 (paraphrase).
  - "we are drowning in information. And yet we know nothing. For sure." (2010)
  - "The SIGINT mission is far too vital to unnecessarily expand the haystacks while we search for the needles." (2011)
  - The 2013 budget had $48.6 million for "Coping with Information Overload" (paraphrase of the article).
  - A GCHQ slideshow: three leads with one of interest leaves time to follow up, but three hundred leads with ten of interest is "probably not much use".
  — [The Intercept (Maass), "Inside NSA, Officials Privately Criticize 'Collect It All' Surveillance"](https://theintercept.com/2015/05/28/nsa-officials-privately-criticize-collect-it-all-surveillance/) [28 May 2015 (older); Read: primary-part; Type: official internal statements, mostly opinion; Applies: direct (US and UK SIGINT)]
- After Glowing Symphony, the 120-day assessment named "storage of the data itself" as a key challenge to exploiting the data collected from ISIS networks. — [National Security Archive](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2020-01-21/uscybercom-after-action-assessments-operation-glowing-symphony) [2020, about 2016–2017 events (older); secondary; official assessment; direct]

**Dwell time, success and detection (recent)**
- Mandiant M-Trends 2026, based on "over 500,000 hours of frontline incident investigations conducted by Mandiant globally in 2025":
  - "Global median dwell time rose to 14 days from 11 days".
  - For cyber espionage and North Korean IT-worker incidents, "the median dwell time for both categories was 122 days".
  - BRICKSTORM: "dwell times of nearly 400 days".
  - "52% of the time organizations first detected evidence of malicious activity internally, an increase from 43% in 2024".
  - Exploits were the top initial vector at "32% of intrusions".
  - "the mean time to exploit vulnerabilities dropped to an estimated -7 days".
  - The median time from initial access to hand-off to a second group fell from "more than 8 hours" (2022) to "just 22 seconds" (2025; criminal ecosystems).
  — [Google Cloud / Mandiant, "M-Trends 2026"](https://cloud.google.com/blog/topics/threat-intelligence/m-trends-2026) [23 Mar 2026; Read: primary-part (blog summary, not the full report); Type: measurement (incident-response caseload, which includes only detected intrusions and only Mandiant clients); Applies: direct for victims of state espionage, but the sample is not random]
- Russian intrusion efforts against 128 organizations in 42 countries outside Ukraine, 24 Feb to June 2022: "the Russian targeting we've identified has been successful 29 percent of the time". "A quarter of these successful intrusions has led to confirmed exfiltration of an organization's data". Microsoft says this likely understates Russian success. — [Microsoft (Brad Smith), "Defending Ukraine: Early Lessons from the Cyber War"](https://blogs.microsoft.com/on-the-issues/2022/06/22/defending-ukraine-early-lessons-from-the-cyber-war/) [22 Jun 2022; Read: primary-part (the blog, not the full PDF, which returned 404); Type: measurement (vendor telemetry); Applies: direct (a capable state in wartime, against alert defenders)]
- GTG-1002 "targeted roughly 30 entities and our investigation validated a handful of successful intrusions". Anthropic detected it "In mid-September 2025" and acted "Over the following ten days". — [Anthropic full report](https://assets.anthropic.com/m/ec212e6566a0d47/original/Disrupting-the-first-reported-AI-orchestrated-cyber-espionage-campaign.pdf) [Nov 2025; primary-full; measurement; direct]

**Volume and visibility of effects (contrast)**
- Destructive attacks in Ukraine were "numbering close to 40, targeting hundreds of systems" (count as of the 27 April 2022 report). "32% of destructive attacks directly targeted Ukrainian government organizations". "More than 40% of destructive attacks were aimed at organizations in critical infrastructure sectors". "Russia-aligned actors began pre-positioning for conflict as early as March 2021". The destructive attacks were "accompanied by broad espionage and intelligence activities". — [Microsoft, "The hybrid war in Ukraine"](https://blogs.microsoft.com/on-the-issues/2022/04/27/hybrid-war-ukraine-russia-cyberattacks/) [27 Apr 2022; primary-part; measurement; direct]
- By June 2022, Microsoft had seen "multiple waves of destructive cyberattacks against 48 distinct Ukrainian agencies and enterprises". — [Microsoft, 22 Jun 2022](https://blogs.microsoft.com/on-the-issues/2022/06/22/defending-ukraine-early-lessons-from-the-cyber-war/) [primary-part; measurement; direct]

### Inferences

**My arithmetic on the GENIE figures (US, 2008–2013, nominal FY2013 USD; older data)**
- 8,448 / 68,975 = **12.2%** of implanted machines fully used in 2011. That is 36.9 active implants and **4.5 fully used implants per GENIE staff member**.
- $652M / 1,870 staff ≈ **$349,000 per staff member per year**. This mixes the FY2013 budget with the 2011 staff count.
- $652M / 68,975 ≈ $9,500 per active implant-year, and $652M / 8,448 ≈ $77,000 per fully used implant-year.
- The implant stock grew 3.2 times from 2008 to 2011 (about 48% a year). The plan for 2011–2013 was a further 1.23 times (about 11% a year).
- The "$652 million project" (GENIE) and the "$651.7 million" break-in mission are very likely the same budget line, about 64% of the $1.02 billion cyber operations budget.

**Where the bottleneck is**
- At the persistence and collection stage, the binding limit was operator time. The 2009 slide names "human 'drivers'", and 88% of implanted machines were not fully used.
- Further down the chain, the limits were processing and analysis: "drowning in information", a $48.6 million overload line, and data storage after Glowing Symphony.
- Access looked relatively plentiful. The model should therefore treat surveillance value as limited by experts (operators and analysts), with access as a second-order limit. This fits value that grows in experts with diminishing returns.
- GENIE's 1,870 staff are about 5% of the model's roughly 39,000 surveillance experts. Most of the surveillance pool therefore works after the access stage (processing, analysis, reporting), where the evidence of diminishing returns is strongest (see section 5).

**Calibration notes**
- The 231 offensive operations in 2011 match the model's roughly 235 attacks a year, and "nearly three-quarters" (up to about 173) were against top-priority targets.
- In 2011 "U.S. intelligence services" ran these operations, and their implant system (GENIE, with TURBINE then coming online) was built for both collection and "active attack". The article does not say which accesses the 231 operations used. This is consistent with a high share of attacks on shared access in the recent past (shared_now 0.7).
- Per-target yield of Russian espionage in 2022: 29% success × 25% confirmed exfiltration ≈ 7% of targeted organizations, under wartime defender alert.
- Espionage hides longer: the median dwell is 122 days against 14 days overall, about 8.7 times. This matches the direction of the essay workbook's matched Ukraine counts (effects detected at 8.6%, espionage at 2.7%). The magnitudes measure different things, and I did not re-verify the SSSCIP counts.

**Per-stage synthesis.** Each cell repeats a cited finding above, except cells marked (inference). Missing evidence is marked "none found".

| Stage (surveillance chain) | Scale | Cost | Time | Value / output | Detection | Bottleneck signal |
|---|---|---|---|---|---|---|
| 1 Requirements and target selection | ~30 targets in one AI-run campaign ([Anthropic](https://assets.anthropic.com/m/ec212e6566a0d47/original/Disrupting-the-first-reported-AI-orchestrated-cyber-espionage-campaign.pdf)) | none found | human-led ("Human strategic direction predominates") | none found | none found | human judgment |
| 2 Access (recon, vulnerability discovery, exploitation) | Russia 2022: 128 orgs in 42 countries, 29% success ([Microsoft](https://blogs.microsoft.com/on-the-issues/2022/06/22/defending-ukraine-early-lessons-from-the-cyber-war/)) | $25.1M FY2013 for bought vulnerabilities ([WaPo repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/)) | AI 1–4 h against human 2–10 min per discovery-to-foothold sequence (Anthropic); time to exploit −7 days ([M-Trends](https://cloud.google.com/blog/topics/threat-intelligence/m-trends-2026)) | footholds | exploits are 32% of initial vectors (M-Trends) | supply of exploitable targets (inference) |
| 3 Persistence (implant management) | 100–150 implants (2004), 21,252 (2008), 68,975 (2011), ≥85,000 planned (2013) ([Intercept 2014](https://theintercept.com/2014/03/12/nsa-plans-infect-millions-computers-malware/); WaPo repost) | GENIE $652M per year (FY2013) | espionage median dwell 122 days; BRICKSTORM ~400 days (M-Trends) | 8,448 fully used (12%) | internal detection 52% (2025) | "Human 'drivers' limit ability for large-scale exploitation" |
| 4 Collection and exfiltration | ≥25% of successful Russian intrusions exfiltrated (Microsoft); 3–20 GB of email in Albania ([CISA AA22-264A](https://www.cisa.gov/news-events/cybersecurity-advisories/aa22-264a)) | none found | AI 2–6 h against human 5–20 min per database extraction (Anthropic) | stolen data | none found | human approval of exfiltration targets |
| 5 Processing and analysis | 2 PB in the SIGINT system; ~1 TB/s expected (2011) ([Intercept 2015](https://theintercept.com/2015/05/28/nsa-officials-privately-criticize-collect-it-all-surveillance/)) | $48.6M FY2013 "Coping with Information Overload" | none found | leads; "300 leads, 10 interesting … probably not much use" (GCHQ) | n/a | analysts "drowning in information"; data storage (Glowing Symphony) |
| 6 Dissemination and use | 15 reports from the CDR program ([PCLOB](https://documents.pclob.gov/prod/Documents/OversightReport/7f5bfdcf-0ae0-4a10-b6ef-0c53137161ea/CDR%20Fact%20sheet%20FINAL.pdf)) | ~$100M (2015–2019) | none found | 2 of 15 reports gave unique information | n/a | marginal value of more collection (inference) |

**How the effects chain differs** (from the findings above):
- *Access:* the same as for espionage, or dedicated pre-positioning (Volt Typhoon).
- *Hold:* no collection, or "minimal activity", for years: at least five years for Volt Typhoon, and 14 months before the Albania wiper. The value is option value for "a moment that may never come".
- *Trigger:* the effect reveals itself to the victim. Defenders counted about 40 destructive attacks within weeks of the invasion.
- *Assessment:* needs intelligence collection for "indicators of success".
- *Aftermath:* the access is burned or must be re-won (see section 4).

**Mapping to model inputs** (summary in section 5)
- *returns_scale:* the capacity-limited access stage argues for an exponent near 1 in operators. The downstream overload argues for one below 1. Overall this supports 0.8 inside 0.5–1.
- *alert_sensitivity:* espionage kept a 29% success rate against wartime-alert defenders and has long dwell times. This supports a low value (≤0.3).
- *exposure:* destructive effects are counted by defenders by construction. This supports a high exposure share for effects.

### Gaps
- **Data volume per analyst:** I found no figure. The NSA's August 2013 paper "The National Security Agency: Missions, Authorities, Oversight and Partnerships" reportedly gives "touches about 1.6%" of internet traffic and analysts looking at "0.00004%". nsa.gov returned 403 and the FAS copy was empty, so I did not verify or use these figures. I found no NSA analyst headcount.
- **Espionage alone:** the M-Trends 2026 blog does not give an espionage-only dwell time (it is pooled with North Korean IT workers), and it gives no split of detection sources for espionage.
- **Cost per stage:** I found no split of GENIE's budget across access, persistence and collection, and no US implant counts after 2013.
- **Ukraine counts:** I did not re-verify the SSSCIP counts behind the essay workbook's 8.6% and 2.7% detection shares (search budget exhausted).

## 2. How AI changes each stage of espionage

### Takeaway
In the one documented AI-run state campaign (GTG-1002, September 2025), AI did "approximately 80 to 90 percent of all tactical work" against about 30 targets, with a few human decision gates. Human time per stage fell to minutes against hours of AI work, and collection and analysis was the stage with "the most extensive AI autonomy". But the AI "frequently overstated findings and occasionally fabricated data", and humans kept the gates (exploitation, use of credentials, exfiltration). Google's and Mandiant's 2026 reporting still describes productivity gains rather than breakthroughs. AI attacks exactly the bottlenecks the 2009–2013 NSA documents name (human "drivers" and analyst overload). It should therefore raise surveillance value most where the US system was limited by capacity.

### Cited Findings

**GTG-1002 (Anthropic, full report, November 2025; primary-full; measurement; direct but one campaign)** — [report PDF](https://assets.anthropic.com/m/ec212e6566a0d47/original/Disrupting-the-first-reported-AI-orchestrated-cyber-espionage-campaign.pdf)

*Whole campaign*
- The AI "executed approximately 80 to 90 percent of all tactical work independently, with humans serving in strategic supervisory roles". "Human operators maintained minimal direct engagement, estimated at 10 to 20 percent of total effort."
- Human gates: "approving progression from reconnaissance to active exploitation, authorizing use of harvested credentials for lateral movement, and making final decisions about data exfiltration scope and retention".
- Tempo: "Peak activity included thousands of requests, representing sustained request rates of multiple operations per second." Claude "maintained persistent operational context across sessions spanning multiple days".

*By phase*
- *Phase 2, reconnaissance:* "Discovery activities proceeded without human guidance". It ran "simultaneously across multiple targets", with the AI "independently cataloging hundreds of discovered services and endpoints".
- *Phase 3, vulnerability discovery and exploitation:* example table "Claude's autonomous actions (1-4 hours)" against "Human operator actions (2-10 minutes)". "Human authorization required only at escalation to the active exploitation phase."
- *Phase 4, credentials and lateral movement:* "Human involvement is limited to reviewing harvested credentials and authorizing access to particularly sensitive systems."
- *Phase 5, collection:* "Collection operations demonstrated the most extensive AI autonomy". The AI was directed to "independently query databases and systems, extract data, parse results to identify proprietary information, and categorize findings by intelligence value". Example table "Claude's autonomous actions (2-6 hours)" against "Human operator actions (5-20 minutes)", including the step "Create persistent backdoor user account". "Human review occurred only at the final exfiltration approval stage."
- *Data analysis:* the AI parsed "large volumes of stolen information to independently identify intelligence value and categorize findings".

*Tools and limits*
- Tools: it "relied overwhelmingly on open source penetration testing tools rather than custom malware development". "cyber capabilities increasingly derive from orchestration of commodity resources rather than technical innovation".
- Limit: "Claude frequently overstated findings and occasionally fabricated data during autonomous operations, claiming to have obtained credentials that didn't work or identifying critical discoveries that proved to be publicly available information". "This remains an obstacle to fully autonomous cyberattacks."

**Other AI threat reporting**
- Anthropic's press page for the same case gives about 4 to 6 critical decision points per campaign (paraphrase). At peak it gives "thousands of requests, often multiple per second"; the page carries a later correction note on this rate wording. — [Anthropic news page](https://www.anthropic.com/news/disrupting-AI-espionage) [13 Nov 2025; primary-part; measurement; direct]
- A criminal "vibe hacking" case, an example of AI at the processing stage. The actor "targeted at least 17 distinct organizations". "Claude Code was used to automate reconnaissance, harvesting victims' credentials, and penetrating networks." "Claude was allowed to make both tactical and strategic decisions, such as deciding which data to exfiltrate". "Claude analyzed the exfiltrated financial data to determine appropriate ransom amounts". — [Anthropic, threat report](https://www.anthropic.com/news/detecting-countering-misuse-aug-2025) [27 Aug 2025; primary-part; measurement; Applies: transfer (criminal actor, extortion rather than intelligence)]
- Google GTIG, covering activity in Q4 2025:
  - AI is used to "accelerate the attack lifecycle, achieving productivity gains in reconnaissance, social engineering, and malware development".
  - "GTIG has not yet observed APT or information operations (IO) actors achieving breakthrough capabilities that fundamentally alter the threat landscape."
  - State actors "enhance all stages of their operations, from reconnaissance and phishing lure creation to command-and-control (C2 or C&C) development and data exfiltration".
  - APT31 used Gemini to "automate the analysis of vulnerabilities and generate targeted testing plans".
  - On agentic use: "an interest in using agentic AI capabilities"; for AutoGPT-like tools, "we have not yet seen evidence of these capabilities being used in the wild".
  - The HONESTCUE malware is "likely in the proof-of-concept stage".
  - Per the tool's reading, the report gives no state-actor example of AI used to analyze stolen data.
  — [GTIG AI Threat Tracker, "Distillation, Experimentation, and (Continued) Integration of AI for Adversarial Use"](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use) [12 Feb 2026; primary-part; Type: measurement and assessment; Applies: direct (APT groups of China, Iran and North Korea)]
- GTIG tracker of 8 September 2026 (secondary coverage only):
  - A shift from one-off prompting to automated, linked workflows.
  - Russia-linked actors used AI for intelligence collection, and one group (UNC5792) ran AI bots that monitor Telegram channels.
  - GTIG's John Hultquist: "we can assume that all threat actors are using AI in some capacity and their operations have benefited."
  - Outlets disagree on whether it is the Q2 or the Q3 2026 edition.
  — [Cyber Magazine, snippet](https://cybermagazine.com/news/google-ai-now-powers-every-threat-actors-playbook); [Let's Data Science, snippet](https://letsdatascience.com/news/google-tracker-details-adversarial-ais-shift-toward-autonomy-9a49eb95) [Sep 2026; Read: snippet; Type: assessment; Applies: direct]
- Mandiant: "do not consider 2025 to be the year where breaches were the direct result of AI". The malware families PROMPTFLUX and PROMPTSTEAL query LLMs while they run. QUIETVAULT looks on victim machines for local AI command-line tools and uses them to search for configuration files (paraphrase). — [M-Trends 2026](https://cloud.google.com/blog/topics/threat-intelligence/m-trends-2026) [23 Mar 2026; primary-part; assessment; direct]
- OpenAI:
  - In February 2024 it disrupted five state-affiliated actors and found models gave "limited, incremental capabilities for malicious cybersecurity tasks" (snippet). — [OpenAI](https://openai.com/index/disrupting-malicious-uses-of-ai-by-state-affiliated-threat-actors/) [Feb 2024; Read: snippet; assessment; direct]
  - Coverage of its October 2025 report says actors "incorporate AI into existing strategies to increase speed and efficiency, rather than developing novel offensive capabilities", and that OpenAI had disrupted over 40 networks since February 2024. — [Cybersecurity News, snippet](https://cybersecuritynews.com/openai-banned-chatgpt-chinese-accounts/) [Oct 2025; Read: snippet, and the search summary did not clearly say which outlet each claim came from; assessment; direct]

### Inferences

**Stage-by-stage effect of AI, from the findings above**

| Stage | Before AI (US 2009–2013 documents) | With AI (2025–2026 evidence) | Remaining human gate or limit |
|---|---|---|---|
| Access | the model's "today" value of 9 months to build access (no source found in this thread) | AI 1–4 h per discovery-to-foothold sequence; campaign spans "multiple days"; ~30 targets at once | approval to exploit; supply of reachable flaws |
| Persistence | "Human 'drivers' limit ability for large-scale exploitation"; 12% of implants fully used | AI creates a persistent backdoor account (Anthropic Phase 5); no data found on AI-run implant fleets | detection of edge-device implants is weak (dwell ~400 days for BRICKSTORM) |
| Collection | operator-driven | "the most extensive AI autonomy"; AI 2–6 h against human 5–20 min | human approves exfiltration scope |
| Processing and analysis | "drowning in information"; $48.6M overload line | AI parses stolen data and categorizes "by intelligence value" | AI "fabricated data" and "overstated findings", so humans must validate; validation becomes the new bottleneck |
| Dissemination | analyst-written reports | no evidence found | none found |

**Productivity**
- If AI does 80–90% of tactical work and humans 10–20%, each human covers 5–10 times as much tactical work. This holds only if the AI's share would otherwise have been human work. The report does not measure pre-AI time, so 5–10 times is an upper-end inference, not a measurement.

**ai_gain (default 1, range 0–3)**
- The GENIE ratio 68,975 / 8,448 ≈ 8.2 bounds the uplift from fully using implants that already exist. It is an upper bound, because the unused implants were probably the less valuable ones.
- AI also attacks the processing bottleneck, which pushes the gain up.
- The "productivity, not breakthrough" findings (GTIG February 2026, M-Trends 2026, OpenAI) and the cost of validating hallucinated output pull the near-term gain down.
- Verdict: this **supports** the default of 1 and the range up to 3. Nothing narrows it. The upper bound of 3 is not excessive against the 8.2 ceiling.

**Cross-checks on other drivers of the model** (other threads own these drivers)
- *AI share of tactical work:* one frontier state actor already reached 80–90% in 2025. The model's end value of 85% has been seen once, and the "today" value of 10% holds only as a force-wide average, not as frontier practice.
- *Targets per attack:* about 30 targets in one AI-run campaign matches the model's end value of 30, but for espionage, not attack.
- *Attribution:* Anthropic attributed GTG-1002 "with high confidence" despite the heavy AI use. That is one case against the idea that AI lowers attribution, at least on commercial platforms.
- *Detection:* AI creates a new channel. The AI provider detected the campaign within its own telemetry. A state that uses its own models avoids this channel, so the finding does not transfer to a US-like actor running its own models.

### Gaps
- I found no measurement of how long human teams took for the same tasks before AI. The "80–90%" is a share of work, not a time saving.
- I found no public data on AI use by US or allied agencies in collection processing. NSA and ODNI statements were not retrieved (search budget).
- I found no error rate for AI categorization of intelligence value beyond the qualitative "frequently overstated".
- I did not read the primary GTIG September 2026 tracker or any 2026 OpenAI report.

## 3. The equities process: how agencies weigh intelligence lost against an effect

### Takeaway
States weigh lost intelligence against an effect case by case, in closed processes. The US runs intelligence gain/loss judgments under a dual-hatted NSA–Cyber Command commander. Interagency coordination lets any agency "non-concur", and the Vulnerabilities Equities Process (VEP) covers vulnerabilities. The public evidence is qualitative and points one way:
- The Secretary of Defense said the intelligence community "tended to delay or try to prevent" Cyber Command's effects against ISIS.
- The 2019 strike on an IRGC database raised doubts over "lost intelligence and lost access to a critical network".
- A serving Cyber Command officer described NSA as holding a "de facto veto authority".

The only public number is NSA's 2015 claim that it disclosed "more than 91 percent" of the vulnerabilities it reviewed. No count of delayed or vetoed operations is public.

### Cited Findings

**Cases**
- *2016 campaign against ISIS.* Ash Carter was "largely disappointed in Cyber Command's effectiveness against ISIS". When Cyber Command produced something useful, the intelligence community "tended to delay or try to prevent its use", "claiming cyber operations would hinder intelligence collection". — [Carter, "A Lasting Defeat: The Campaign to Destroy ISIS," Belfer Center](https://www.belfercenter.org/publication/lasting-defeat-campaign-destroy-isis) [Oct 2017 (older); Read: primary-part (100,000 of 112,000 characters); Type: opinion of the Secretary of Defense; Applies: direct (US)]
- *Operation Glowing Symphony (November 2016).*
  - It went through Joint Interagency Coordination and "was met several 'non-concurs'". NSC Deputies and Principals meetings then changed the plan.
  - The 30-day assessment: "This delay and change to the operation design had an impact on effectiveness" (the size of the impact is redacted).
  - Washington Post reporting says the objections "required weeks of NSC meeting to iron out", and that the CIA, State and FBI objected to operating in foreign countries without notice (paraphrase).
  - Outcome: the operation "imposed time and resource costs" on ISIS, and nearly all task indicators were rated "green".
  — [National Security Archive, Briefing Book #693](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2020-01-21/uscybercom-after-action-assessments-operation-glowing-symphony) [21 Jan 2020, events 2016–2017 (older); secondary; official assessment; direct]
- *June 2019 operation against the IRGC.*
  - The operation "wiped out a critical database" that the IRGC used to track vessels in the Gulf.
  - Officials spoke "in part to quell doubts within the Trump administration about whether the benefit of the operation outweighed the cost—lost intelligence and lost access to a critical network".
  - Officials expressed "surprise at how long the effects of this operation have lasted".
  - Chesney: "Those effects may or may not outweigh whatever collection costs we've experienced."
  — [Chesney, Lawfare, summarizing Julian Barnes, New York Times, 28 Aug 2019 (NYT paywalled, not read)](https://www.lawfaremedia.org/article/cyber-command-operational-update-clarifying-june-2019-iran-operation) [3 Sep 2019 (older); Read: secondary; Type: official statements (anonymous) and opinion; Applies: direct (US)]

**The process and the dual-hat**
- *Andrew Schoka, a serving Cyber Command officer:*
  - Operations need "an equities review" by "a multitude of government, intelligence, and military stakeholders".
  - Cyber Command "has essentially lent the agency de facto veto authority on offensive cyberspace operations".
  - What "takes adversaries mere minutes to do" takes Cyber Command "weeks, or even months".
  - Gen. Michael Hayden called offensive operations and SIGINT "technically indistinguishable from each other".
  - Cyber Command has "steadily become more risk-averse than befits an organization dedicated to offensive operations".
  — [War on the Rocks, "Time to End the Dual Hat"](https://warontherocks.com/2019/04/cyber-command-the-nsa-and-operating-in-cyberspace-time-to-end-the-dual-hat/) [3 Apr 2019 (older); primary-full; opinion; direct]
- *Tom Uren, Lawfare, December 2024:*
  - The dual-hat lets one leader "weigh competing intelligence and disruption options".
  - Gen. Haugh argued for "a single decision maker, responsible and accountable for the mission outcomes of both organizations". He wrote that "NSA and USCYBERCOM have developed a close partnership in this area" and that he would improve the processes for sharing accesses between them "where appropriate".
  - Uren: decide on a "case-by-case basis and not according to a hierarchy that places military disruption ahead of intelligence collection".
  - The incoming administration "plans to end the current 'dual-hat' arrangement". Ending it needs a certification that there is no "unacceptable risk to the military effectiveness" of Cyber Command.
  — [Lawfare, "Two Hats Are Better Than Two Heads"](https://www.lawfaremedia.org/article/two-hats-are-better-than-two-heads) [20 Dec 2024; primary-full; opinion and official statements; direct]
- *Martin Matishak, The Record, September 2025:*
  - Officials shelved the split without a presidential memo or other formal document.
  - Hegseth: "As of right now, we're maintaining the status quo. But it's something we reserve the right to review".
  - Officials judged that a split would take up to three years to dissolve and three more to reassemble (paraphrase).
  - Paul Nakasone's review found "substantial benefits that present compelling evidence for retaining the existing structure".
  - Lt. Gen. Hartman had been acting head of both since Gen. Haugh was fired in April 2025.
  — [The Record](https://therecord.media/cyber-command-nsa-dual-hat-single-leader-trump-administration) [9 Sep 2025; primary-full; official statements; direct]
- *2026 status (snippets only):*
  - In February 2026, nominee Joshua Rudd said he would continuously evaluate whether the dual-hat stays the most effective structure. — [DefCros News, snippet](https://news.defcros.com/trumps-cyber-chief-nominee-to-evaluate-the-effectiveness-of-the-dual-role-of-cyber-command-and-nsa-upon-confirmation)
  - A SecurityWeek headline reads "Senate confirms Joshua Rudd to lead NSA and US Cyber Command". The page refused a plain request, so I did not see the date. — [SecurityWeek, headline only](https://www.securityweek.com/senate-confirms-joshua-rudd-to-lead-nsa-and-us-cyber-command/amp/)
  - [2026; Read: snippet; official statements; direct]

**The Vulnerabilities Equities Process**
- *VEP charter, 15 Nov 2017:*
  - Presumption: "The primary focus of this policy is to prioritize the public's interest in cybersecurity … through the disclosure of vulnerabilities discovered by the USG, absent a demonstrable, overriding interest in the use of the vulnerability for lawful intelligence, law enforcement, or national security purposes." "In the vast majority of cases, responsibly disclosing a newly discovered vulnerability is clearly in the national interest."
  - Review: a restricted vulnerability "will be reassessed annually by the ERB". An agency that does not concur must hold discussions "within 7 business days".
  - Exceptions: a decision "could be subject to restrictions by partner agreements and sensitive operations" (details in a classified Annex C), and "Quantities of excepted vulnerabilities from each department and agency will be provided in ERB meetings".
  - Reporting: the annual report "will include statistical data as deemed appropriate", and it "may be provided to the Congress".
  - The Equities Review Board includes ODNI, NSA, US Cyber Command and the CIA, among others.
  - Operational-value questions in Annex B: "What is the demonstrated value of this vulnerability for intelligence collection, cyber operations"; "What is its potential (future) value?"; "Do alternative means exist to realize the operational benefits"; "Would disclosing this vulnerability reveal any intelligence sources or methods?"
  - Defensive question in Annex B: "What percentage of vulnerable systems will remain forever unpatched or unpatched for more than a year after the patch is released?"
  — [Vulnerabilities Equities Policy and Process for the United States Government](https://trumpwhitehouse.archives.gov/sites/whitehouse.gov/files/images/External%20-%20Unclassified%20VEP%20Charter%20FINAL.PDF) [15 Nov 2017 (older); Read: primary-part (my text extraction; I read the sections named); Type: official policy; Applies: direct (US)]
- *The 91% claim.* Adm. Michael Rogers said on 7 Nov 2015 that NSA had "historically" released more than 91 percent of the vulnerabilities it found. The remaining 9 percent were either already fixed by vendors or kept "for national security reasons". — [Nextgov](https://www.nextgov.com/cybersecurity/2015/11/nsa-chief-says-agency-discloses-91-percent-of-zero-day-bugs/207923/) [9 Nov 2015 (older); Read: secondary; Type: official claim (unaudited); Applies: direct]
  - Critics, via snippets only: Reuters reported that "the NSA often uses the vulnerabilities to make its own cyber-attacks first" ([Investing.com repost of Reuters, snippet](https://uk.investing.com/news/stock-market-news/article-75998)). An analyst said the figure "doesn't really tell us much because we don't know the timeframe between discovery and disclosure" ([Dark Reading, snippet](https://www.darkreading.com/vulnerabilities-threats/nsa-discloses-91-percent-of-vulns-it-finds-but-how-quickly-)). [2015 (older); snippet; opinion]

### Inferences
- **No base rate.** I found no count of how often effects were delayed or vetoed. The qualitative record shows that the intelligence side often prevailed or forced delays (2016, "weeks" of NSC meetings), and that the trade-off was argued at cabinet level after the fact (2019). The model can treat the equities process as two things: a filter that blocks some attacks on shared access when intelligence value is high, and a delay of weeks for the attacks it lets through. No source gives the size of either.
- **The 91% figure is an analogy only.** It is a disclosure share of reviewed vulnerabilities, not of operations. Read loosely: when a defensive equity conflicts with an intelligence or operational equity, the intelligence side kept the asset in at most about 9% of reviewed cases, and that 9% includes flaws the vendors had already fixed. It is a weak analogy for how often intelligence value outweighs a competing use, and it is unaudited and old.
- **Effects use surveillance resources beyond burned access.** They need collection assets for "indicators of success" (damage assessment) and weeks of interagency deliberation. The model's surveillance cost of an attack could include an assessment-support term, not only burned access.
- **The decision rule stays.** In 2025–2026 the US kept one commander who weighs both options ("weigh competing intelligence and disruption options"). This fits the model's premise that today's split of about 11 surveillance experts per attack expert is the country's own optimizing choice.
- **access_value (default 5, range 0.5–30).** The 2019 case is the clearest public sign that one attack can burn the access to a "critical network" of high collection value. It is consistent with the default and with the upper part of the range for priority targets, but it gives no number.

### Gaps
- I found no counts of operations delayed, changed or vetoed for intelligence equities, in the US or anywhere else.
- **IGL definition.** A search summary gave the doctrinal definition of an intelligence gain/loss assessment as "an evaluation of the quantity and quality of intelligence lost versus potential gain should a particular target be attacked", attributed to Joint Publication 2-01.1. I could not open a readable copy (the DTIC paper returned 403), so the wording is unverified.
- I found no VEP annual statistics published after the 2017 charter, and no newer disclosure share.
- I did not research NSPM-13 (2018), which delegated authority for offensive operations, or its effect on approval times.
- I did not read the primary NYT report on the 2019 operation (paywalled).

## 4. What share of effects operations use access built for espionage, and what happens to that access after the effect

### Takeaway
No source gives a share. Case evidence shows both patterns.

Shared access:
- Iran collected email from an Albanian government network for months before it wiped the same network.
- Russia's APT44 runs espionage, attack and influence as one "unified playbook".
- US effects in 2011 were run by intelligence services, whose implant system (GENIE, then TURBINE) was built for both collection and "active attack".
- The 2019 IRGC strike cost "lost access to a critical network".

Dedicated effects access:
- China's Volt Typhoon pre-positioned for five or more years with "minimal activity", which is "not consistent with traditional cyber espionage".

After an effect, the access is usually exposed or lost, but actors can return: Iran struck Albania again two months later.

### Cited Findings
- **Iran in Albania, 2021–2022.**
  - The actors "acquired initial access to the victim's network approximately 14 months before launching the destructive cyber attack".
  - Email exfiltration began "Approximately 8 months after initial compromise", with roughly 3–20 GB moved (paraphrase of the transfer figures).
  - "In July 2022, the actors launched ransomware on the networks", with a disk wiper.
  - In September 2022 they "launched another wave of cyber attacks against the Government of Albania".
  — [CISA and FBI, Advisory AA22-264A](https://www.cisa.gov/news-events/cybersecurity-advisories/aa22-264a) [21 Sep 2022; Read: primary-part; Type: official forensic finding; Applies: direct (a state, but less capable than the US)]
- **Russia's APT44 (Sandworm).**
  - It is "actively engaged in the full spectrum of espionage, attack, and influence operations".
  - "While most state-backed threat groups tend to specialize in a specific mission such as collecting intelligence, sabotaging networks, or conducting information operations, APT44 stands apart in how it has honed each of these capabilities and sought to integrate them into a unified playbook over time."
  - It is "responsible for nearly all of the disruptive and destructive operations against Ukraine over the past decade".
  - "as the war has endured, APT44's relative focus has transitioned away from disruption to intelligence collection".
  - One campaign helps forward Russian ground forces "exfiltrate communications from captured mobile devices in order to collect and process relevant targeting data".
  — [Mandiant, "APT44: Unearthing Sandworm"](https://cloud.google.com/blog/topics/threat-intelligence/apt44-unearthing-sandworm) [17 Apr 2024; Read: primary-part (the blog, not the full report); Type: assessment; Applies: direct (a capable state)]
- **Russia in Ukraine, 2021–2022.** Microsoft: "Russia-aligned actors began pre-positioning for conflict as early as March 2021", and the destructive attacks were "accompanied by broad espionage and intelligence activities". The blog does not say that the same accesses were used for both. — [Microsoft](https://blogs.microsoft.com/on-the-issues/2022/04/27/hybrid-war-ukraine-russia-cyberattacks/) [27 Apr 2022; primary-part; measurement; direct]
- **China's Volt Typhoon:** dedicated pre-positioning for at least five years, with minimal activity and collection limited to data "that would facilitate follow-on actions with physical impacts". — [CISA AA24-038A](https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-038a) [7 Feb 2024; primary-part; official; direct]
- **US infrastructure serves both missions.**
  - TURBINE manages implants for intelligence gathering and "active attack". — [WaPo via Atlantic Council repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/) [2013 (older); repost; official; direct]
  - Of the nine QUANTUM tools listed, "six of which are used for intelligence gathering"; QUANTUMSKY blocks access to websites and QUANTUMCOPPER "corrupts a target's file downloads". The article contrasts CNE with "CNA seeks to disrupt, damage or destroy them". — [The Intercept](https://theintercept.com/2014/03/12/nsa-plans-infect-millions-computers-malware/) [12 Mar 2014 (older); primary-part; official; direct]
- **US, 2019:** an effect run on an access that also gave collection cost "lost intelligence and lost access to a critical network". — [Lawfare (Chesney, summarizing NYT)](https://www.lawfaremedia.org/article/cyber-command-operational-update-clarifying-june-2019-iran-operation) [3 Sep 2019 (older); secondary; official statements; direct]
- **US, 2024:** Gen. Haugh committed to improving processes for sharing accesses between NSA and Cyber Command "where appropriate". — [Lawfare (Uren)](https://www.lawfaremedia.org/article/two-hats-are-better-than-two-heads) [20 Dec 2024; primary-full; official statement; direct]
- **Effects also produce intelligence.** Glowing Symphony's 120-day assessment named "storage of the data itself" as a challenge to exploiting the data collected from ISIS networks. — [National Security Archive](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2020-01-21/uscybercom-after-action-assessments-operation-glowing-symphony) [2020, about 2016–2017 (older); secondary; official; direct]

### Inferences
- **shared_now (0.7).** No source supports or contradicts the number. The qualitative US record supports a high share in the past: 2011 effects run by intelligence services, a dual-use implant system (GENIE, then TURBINE), and Cyber Command's dependence on NSA (Schoka). Haugh's "where appropriate" in 2024 suggests that sharing is still common but managed case by case. Keep 0.7 as an unreviewed assumption.
- **shared_end (0.2).** Volt Typhoon shows that a capable state already keeps dedicated effects access, using tradecraft (living off the land, minimal activity) that avoids collection. This is a precedent for the model's fall to 0.2, most plausibly once access is cheap to build (AI). It **supports the direction** of the change, but no source gives the end value.
- **Sharing may vary by doctrine.** Russia (APT44) integrates the missions in one unit, China (Volt Typhoon) separates them, and Iran (Albania) used one access for collection first and then for effect. A US-calibrated model sits between these. The 0–0.9 range covers all of them.
- **What happens after the effect.**
  - The effect exposes the access and often the tools: CISA published indicators within about two months of the July 2022 Albania attack.
  - The actor can re-enter. The second Albania wave came about two months after the first.
  - In the 2019 case officials described the access as lost.
  - So "burned" need not mean gone for good. The loss is the intelligence flow until the access is rebuilt, plus the cost of rebuilding it.
- **Suggestion for the model's owner on access_value.** If the burn cost is mainly the rebuild cost (time to build access × team), it should fall as the AI driver cuts the time to build access from 9 months to about a week. If it is mainly the lost intelligence flow during the rebuild, it should fall too, because the rebuild is shorter. If the model holds access_value constant at 5 surveillance-expert-years, linking it to the access-build-time driver would make the trade-off move with AI. This is my inference, not a source finding.
- **Collection before effect.** In Albania, up to about 6 months of collection (from about month 8 to month 14) came before the effect. For a model with shared access, the access gave surveillance value before an attack burned it.

### Gaps
- I found no quantitative share of effects operations run on espionage access, for any state.
- I found no data on how long an access stays lost after an effect, or how often actors re-enter.
- **Not researched (search budget):**
  - Stuxnet/Olympic Games (Flame and Duqu reconnaissance, then exposure)
  - Israeli operations (Predatory Sparrow)
  - the access history of Sandworm's Industroyer2 and its 2022 OT attack
  - the 2018 US operation against the Internet Research Agency

## 5. Diminishing returns of surveillance: evidence on the marginal value of more collectors, implants or analysts

### Takeaway
The evidence of diminishing returns in collection volume is strong in kind but gives no elasticity:
- The NSA spent about $100 million on the USA Freedom Act call detail records (CDR) program. It produced 15 reports, 2 with unique information, and NSA shut it after "balancing the program's relative intelligence value, associated costs".
- Internal NSA writers said they were "drowning in information".
- GCHQ noted that 300 leads with 10 of interest is "probably not much use".

Against this, the US access stage was limited by capacity: 88% of implanted machines were not fully used. More operators would therefore have added value almost linearly there. Together, these support a returns exponent between about 0.5 and 1. The default of 0.8 is plausible but not measured.

### Cited Findings
- **PCLOB on the CDR program.** "The USA Freedom Act CDR program cost the government approximately $100 million. Under the program, NSA produced 15 intelligence reports." "Of the 15 reports citing USA Freedom Act CDRs, the FBI received unique information from two of the intelligence reports." NSA suspended the program in early 2019 "after balancing the program's relative intelligence value, associated costs, and compliance and data-integrity concerns". — [PCLOB, CDR program fact sheet](https://documents.pclob.gov/prod/Documents/OversightReport/7f5bfdcf-0ae0-4a10-b6ef-0c53137161ea/CDR%20Fact%20sheet%20FINAL.pdf) [Feb 2020, program period 2015–2019 (older data); Read: primary-full (fact sheet; the full report not read); Type: official measurement; Applies: transfer (domestic counterterrorism metadata, not foreign cyber espionage)]
  - A search summary adds that 15 reports is, "by NSA's own assessment", low "for a program of this scale and cost". — [Lawfare summary of the PCLOB report, snippet](https://www.lawfaremedia.org/article/privacy-and-civil-liberties-oversight-board-releases-report-nsa-call-detail-records-program) [Feb 2020; Read: snippet; the attribution is uncertain]
- **Too much data.** Internal NSA and GCHQ statements, 2010–2012: "drowning in information"; "unnecessarily expand the haystacks"; "300 leads, 10 interesting … probably not much use"; 2 PB in the SIGINT system at any time. — [The Intercept](https://theintercept.com/2015/05/28/nsa-officials-privately-criticize-collect-it-all-surveillance/) [28 May 2015 (older); primary-part; official internal opinion; direct]
- **Capacity limit at the access stage.** "Even with a staff of 1,870 people, GENIE made full use of only 8,448 of the 68,975 machines with active implants in 2011", and growth was limited "by the need for human operators". — [WaPo via Atlantic Council repost](https://www.atlanticcouncil.org/blogs/natosource/us-spy-agencies-mounted-231-offensive-cyber-operations-in-2011-documents-show/) [2013 (older); repost; official; direct]. The 2009 slide: "Human 'drivers' limit ability for large-scale exploitation". — [The Intercept](https://theintercept.com/2014/03/12/nsa-plans-infect-millions-computers-malware/) [2014 (older)]
- **More collection added little in one case.** During Glowing Symphony, storage of the collected data limited its exploitation. — [National Security Archive](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2020-01-21/uscybercom-after-action-assessments-operation-glowing-symphony) [2020 (older events)]

### Inferences

**My arithmetic**
- PCLOB: about $6.7 million per intelligence report, and about $50 million per report with unique information (nominal USD, 2015–2019).
- GENIE: 4.5 fully used implants per staff member (2011).

**Two regimes of returns**
- *Operator-limited stage (access and persistence):* value grows almost in proportion to operators while idle accesses remain. The exponent there is near 1.
- *Volume-limited stage (processing, analysis, dissemination):* value per added unit of collection falls quickly, and programs with low marginal value are cut. The CDR program is a case where the agency itself judged the margin negative.
- Most of the model's surveillance pool works at the volume-limited stage (GENIE was about 5% of the pool), so the blended exponent should sit below 1.

**Consolidated mapping to the model's inputs.** None of the sources gives an empirical interval for any of these parameters. The ranges in the model are selected bounds, and the verdicts below say only whether the qualitative evidence fits them.

| Input (default, range) | Evidence (sections) | Verdict |
|---|---|---|
| returns_scale (0.8; 0.5–1) | operator-limited access stage (GENIE 12% used; "human drivers"), so near 1 there; volume-limited downstream ("drowning", PCLOB 2 of 15 reports, GCHQ leads), so below 1; most of the pool works downstream (§1, §5) | **Supports** the default and range. No source narrows it. If AI removes the operator limit, the access-stage part of the blend moves toward 1, so the effective exponent could rise with AI progress, which a constant returns_scale does not capture |
| ai_gain (1; 0–3) | 80–90% of tactical work by AI; collection and analysis most autonomous; hours of AI work against minutes of human work; ceiling of about 8.2 times from idle GENIE implants; "productivity gains", not "breakthrough"; hallucination needs validation (§2) | **Supports** the default and range. The upper bound of 3 sits well under the 8.2 ceiling, and the "no breakthrough" findings argue against going higher in the near term |
| alert_sensitivity (0.3; 0–1) | Russia kept 29% espionage success against wartime-alert targets; espionage median dwell 122 days, edge-device implants about 400 days, while internal detection rose from 43% to 52%; APT44 moved from disruption toward collection as the war went on; workbook detection shares, effects 8.6% against espionage 2.7% (§1, §4) | **Supports** a low value. Surveillance is less sensitive to alert defenders than effects are. The evidence argues against values near 1 but gives no number |
| access_value (5 surveillance-expert-years per burning attack; 0.5–30) | GENIE ≈ 0.22 staff-years per fully used implant per year (1,870 / 8,448), so a routine implant is worth about 0.2 expert-years per year of its life; strategic accesses are far more: 2019 "critical network", Albania 14 months from access to effect, Volt Typhoon at least five years; most 2011 attacks hit top-priority targets (§1, §3, §4) | **Supports** the default for priority targets. The lower bound of 0.5 sits above the per-year cost of a routine implant, which matters only if attacks burn routine accesses. The evidence also suggests linking access_value to the access-build-time driver (§4) |
| shared_now (0.7) | 2011 effects run by intelligence services, whose implant system (GENIE, then TURBINE) was built for collection and "active attack"; Cyber Command's dependence on NSA; Haugh's access sharing "where appropriate"; 2019 burned shared access (§3, §4) | **Consistent**, not measured. Keep it as an unreviewed assumption |
| shared_end (0.2; 0–0.9) | Volt Typhoon shows dedicated effects access by a capable state; cheap AI-built access makes dedicated access affordable (§2, §4) | **Supports the direction** of the fall. The end value has no source |
| exposure (0.8; 0.5–1) | destructive effects are counted by victims and vendors (about 40 in weeks, 48 organizations); US effects became public through the press (Glowing Symphony in 2017, IRGC within about 2 months in 2019) (§1, §3) | **Consistent** with a high share. No count of unexposed effects exists, so the range cannot be narrowed |

### Gaps
- I found no estimate of the marginal value of an added implant, collector or analyst for foreign intelligence, and no elasticity of value in staff.
- **Not read (search budget):**
  - PCLOB's January 2014 report on the Section 215 program
  - PCLOB's 2023 report on Section 702
  - ODNI's annual transparency reports (the growth of Section 702 targets as a revealed-preference signal)
  - David Anderson's 2016 Bulk Powers Review (UK), which assessed the utility of bulk collection
  - the academic work requested: Buchanan, *The Cybersecurity Dilemma* (2016) and *The Hacker and the State* (2020); Smeets, "A matter of time: On the transitory nature of cyberweapons" (2018) and *No Shortcuts* (2022)
  - Do not attribute claims to these sources from these notes.
- I found no data on analyst headcounts, or on analyst output per unit of collected data.
