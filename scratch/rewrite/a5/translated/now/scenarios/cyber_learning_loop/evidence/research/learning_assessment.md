# Learning, forgetting, damage assessment and budget response: evidence for the model

Conventions used in these notes. Each finding has a tag: *Date* (publication date; "older" means before 2020), *Read* (full text, abstract, or secondary report), *Type* (measurement, author's estimate or opinion) and *Applies* (direct measurement for a capable state's cyber force, transfer from another field, or analogy). A "yearly loss rate" is the continuous rate k for which the share kept after one year is e^(−k). Where I convert a source's number to a yearly rate, the conversion is mine and is marked as such. Access limits: USNI Proceedings, FDD, RAND's report page, sud.ua, MSSP Alert and one abstract index refused plain requests (HTTP 403); NPR returned 503; Springer and the Liberty-ship PDF host required a login or gave an empty page; PubMed needed cookies, so I used the official Europe PMC API for that abstract instead. The shared web-search budget ran out before the end of the research, so some items stay in the Gaps lists unverified. The model's formulas quoted below are from a read-only look at the model file. I changed no file except this one.

## 1. Learning curves: how much do cost or errors fall per doubling of cumulative experience?

### Takeaway
In industry, cost usually falls by about 20% per doubling of cumulative output. The reported spread is about 10–40% per doubling (progress ratios of about 0.60–0.95), and repetitive or purchased work learns least. Military cases show large step gains after a deliberate review and training, not only after more combat. I found no published learning-curve measurement for offensive cyber teams. At its defaults the model learns much more slowly than industry does per doubling: about 1.7% lower attack cost per doubling of today's lessons, and at most about 5.5%.

### Cited Findings
**General learning-curve evidence**
- **Wright's "20 percent learning curve": 20% fewer inputs per doubling of cumulative output** (aircraft, 1930s). Quote: "wide acceptance of the "20 percent learning curve" in the engineering literature, which has the interpretation that production input requirements reduce by 20 percent for every doubling of cumulative past production." — [Benkard, NBER WP 7127 (AER 2000)](https://www.nber.org/papers/w7127.pdf). *Date: 1999 working paper, AER 2000 (older); Read: full text; Type: measurement (Wright 1936), reported by Benkard; Applies: transfer.*
- **Lockheed L-1011, traditional learning model, first 112 units: 30% learning rate (progress ratio 0.70).** Scope: "four basic models of L-1011 in only 250 units produced and production rates varied widely", 1970–1984. Quote: "The implied learning rate is slightly higher than average at 30 percent". — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: measurement (econometric estimate); Applies: transfer.*
- **L-1011 with forgetting in the model: 35–40% per doubling of the depreciated experience stock (progress ratio 0.60–0.65).** Quote: "the learning rates in Table 3 (35-40 percent) are much higher than those estimated under traditional learning hypothesis". Adding forgetting cut the sum of squared residuals: "With the addition of only one parameter, the SSR to falls from 12.9 to 2.9." — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: measurement; Applies: transfer.*
- **Learning and forgetting cannot be told apart when output is steady.** Quote: "data could be consistent with either a 20 percent learning rate or a 25 percent learning rate with 5 percent forgetting". — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: author's illustration; Applies: transfer (calibration warning).*
- **Know-how is specific: about 70% of tasks overlapped between two sibling L-1011 models.** Quote: "approximately 70 percent of production tasks overlap between the two models … suggesting that aircraft production experience is very specific." — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: measurement; Applies: transfer (bears on lessons that transfer between targets and stages).*
- **Experience-curve effects of 10–25% across industries (BCG, 1960s–70s).** Quote: "Research by BCG in the 1960s and 70s observed experience curve effects for various industries that ranged from 10% to 25%." The same page lists NASA progress ratios: aerospace 85%, shipbuilding 80–85%, complex machine tools for new models 75–85%, repetitive electronics 90–95%, raw materials 93–96%, purchased parts 85–88%. — [Wikipedia, "Experience curve effect"](https://en.wikipedia.org/wiki/Experience_curve_effect), citing Hax & Majluf (1982) and NASA's cost-estimating site. *Date: page read 2026; the underlying data are older; Read: tertiary page; Type: compiled measurements; Applies: transfer.*
- **A power law (Wright's law) predicted best across 62 technologies.** Quote: "Wright's law performed best" (among six models). — [Wikipedia, "Experience curve effect"](https://en.wikipedia.org/wiki/Experience_curve_effect), citing Nagy et al. (2013, PLOS ONE). *Date: 2013 (older); Read: tertiary; Type: measurement; Applies: transfer (bears on curve_shape).*

**Military cases**
- **US Navy air-combat exchange ratio after the Ault report (early 1968) and TOPGUN (opened 3 March 1969): about 2:1 in 1965–68, a claimed 12:1 by 1973, revised to "nearly 9-1". The Air Force stayed near 2:1.** Quotes: Navy crews were "downing barely two North Vietnamese MiGs for each F-4 Phantom or F-8 Crusader lost"; by 1973 the ratio "had vaulted to a claimed 12-to-1"; with Marine Corps losses counted, "the actual fighter ratio was nearly 9-1"; the Air Force's "overall 2-1" was "little changed since 1968". The Ault report was "released in early 1968" with "nearly 250 recommendations". The air war "resumed in full force" only in 1972, after which TOPGUN graduates "began downing MiGs almost routinely". — [HistoryNet, "Topgun turns 50"](https://www.historynet.com/topgun-turns-50.htm). *Date: 2019, 50th-anniversary article (older; exact day not captured); Read: full article; Type: claimed kill tallies (measurements with known overclaim issues) and the author's narrative; Applies: analogy.* USNI Proceedings' 2019 TOPGUN article refused the request (403). Other search-result sources (not opened) gave conflicting ratios: 2.4–2.5:1 before and about 12.5:1 after; or 3.7:1 for 1965–67 and about 13:1 after 1970.
- **Red Flag (first held November 1975) was built on an Air Force analysis that pilot survival rose sharply after the first 10 combat missions.** Seen only in search-result summaries of Wikipedia mirrors and of an Air Force release quoted by [We Are The Mighty](https://www.wearethemighty.com/intel/red-flag-rescue-exercise) ("pilot survivability increased dramatically after surviving 10 combat missions"). *Date: undated secondary; Read: search snippet only (not opened); Type: secondary report of an Air Force analysis (Project Red Baron); Applies: analogy (individual learning in a task where feedback is clear).*

**Cyber-specific**
- **Tool-building stage: once a vulnerability is found, a working exploit takes a median of 22 days.** Quote: "a median time of 22 days". Sample: "more than 200" vulnerabilities and exploits from one gray-market vendor. — [RAND news release on "Zero Days, Thousands of Nights" (EurekAlert)](https://www.eurekalert.org/news-releases/855015). *Date: 9 March 2017 (older); Read: official news release (RAND's report page refused, 403); Type: measurement; Applies: direct for the tool-building stage's duration; it does not measure a learning rate.*
- I found **no published learning curve (cost, time or error per doubling of experience) for offensive cyber teams, red teams or exercises**. The closest search results were methods for measuring learning at cyber-defence exercises (for example, timestamp analysis at Locked Shields) and a small 2012 student red-versus-blue study with no significant team differences. I did not open them. See Gaps.

### Inferences
**What the model does per doubling (my computation from the model's own forms).** The model sets weight = r^c/(1+r^c) with r = lessons/prior_strength and c = curve_shape. Gain = (weight − weight_today)/(1 − weight_today), and cost = base_cost × (1 − cost_learning × gain). At the defaults, lessons today ≈ 0.4 × 235 / 0.3 ≈ 313 assessed outcomes, so r_today ≈ 0.063.
- If lessons double from today's level, gain ≈ 0.056, so cost falls by about **1.7%**. That is an effective progress ratio of about 0.98, against 0.60–0.90 in industry.
- Four doublings (r ≈ 1) give gain ≈ 0.47 and cost about 14% lower. A 20%-per-doubling industrial curve would give 59% lower cost over the same four doublings.
- The largest cost reduction per doubling that the model can give is cost_learning × 0.18 with c = 1 (5.5% at 0.3, 11% at 0.6), and cost_learning × 0.48 with c = 3 (14% at 0.3, 29% at 0.6).
- So industry-like learning rates are possible in the model only with curve_shape near 3 and cost_learning of at least about 0.45, and only near r ≈ 1.

**Mapping to model inputs**
- *cost_learning (0.3; 0–0.6):* Industrial curves suggest larger savings than the default gives: 20–40% per doubling, which compounds past 50% within a few doublings. Two things argue for slower learning in cyber: know-how is specific to the task (70% overlap even between sibling aircraft models), and defenders adapt, so targets change and old lessons lose value. There is no cyber measurement. **Verdict: the range is not contradicted. The default is conservative against industrial analogies, and it remains an unreviewed assumption.**
- *curve_shape (1; 1–3):* Wright's power law fits best across 62 technologies, and manufacturing curves show no threshold or critical mass in the learning function itself. **Verdict: supports 1.** Values above 1 put a critical mass into the curve, which the industrial data do not show. The essay's "flip" can still come from the feedback loop with c = 1.
- *prior_strength (5,000; 300–20,000):* There is no direct evidence. Individual skills improve within about 10 real missions (Red Flag), and a navy changed its air-combat results after one structured review plus a school (TOPGUN), with few combat outcomes in between. This favours lower prior strength for team-level skills. For doctrine at the level of the whole force, the evidence is silent. **Verdict: not narrowed.**
- *A key combination for the rest point (my computation):* At the rest point, r_today = reliability × attacks × independent outcomes / (forget_rate × prior_strength) = 0.4 × 235 × 1 / (0.3 × 5,000) ≈ 0.063. The three instability thresholds in the brief map to almost the same value: prior 3,500 gives r ≈ 0.090, forget_rate 0.2 gives r ≈ 0.094, and reliability 0.58 gives r ≈ 0.091. The match is approximate, because reliability and forgetting also enter the value of lessons. **So the stable verdict needs this one ratio known to within about +40%.** The evidence in these notes spans factors of 2–10 on each part of it, so it cannot settle the verdict.
- *Identification:* Benkard shows that steady output cannot separate learning from forgetting. Two decades of a small, steady effects program therefore cannot calibrate prior_strength and forget_rate separately from history. Only their combination is fixed by today's split.
- *Doctrine analogy:* In the TOPGUN case, better results came after a formal assessment of past engagements and a schoolhouse that gave simulated experience. That is a source of lessons outside real operations, which the model leaves out: it counts only assessed outcomes of real attacks. Exercises, ranges and the surveillance work itself could be extra lesson inflows.

**Kill-chain stages**
- The finding that know-how is specific (70% overlap) supports separate stocks of lessons by stage. Stages tied to a target (target analysis, access) transfer poorly between targets. Generic stages (tool frameworks, infrastructure, tradecraft) should transfer better.
- The tool-building stage is fast once a vulnerability is known (median 22 days). The slow part is finding vulnerabilities, which is not measured here.
- The surveillance chain shares reconnaissance, access and persistence with the effects chain. Espionage, with about 92% of the experts, gives those shared stages far more practice than about 235 attacks a year can. Stages that only the effects chain has (effects design, timing of delivery, battle-damage assessment) learn only from attacks.

### Gaps
- **Dutton & Thomas (1984) spread not verified.** I could not open the 1984 papers, Argote & Epple (Science 247:920–924, 1990) or Argote's book chapter (Springer requires a login), and the search budget ran out. A search snippet I could not trace to a page said that both Dutton & Thomas and McDonald & Schrattenholzer (2001) found "a median learning rate of close to 20%". I recall that the Dutton & Thomas histogram is often reproduced as spanning progress ratios of about 0.55–1.07 with a mode near 0.81–0.82. This is unverified recollection: check it before use.
- No cyber-specific learning curve. I found no study of red-team, exploit-development or exercise performance against cumulative experience. The FDD June 2026 piece on cyber workforce training refused the request (403).
- I did not obtain the Red Baron numbers (missions against survival odds) from a primary source.

## 2. Organizational forgetting and staff turnover: how fast is know-how lost, and from which causes?

### Takeaway
Measured knowledge depreciation in organizations ranges from about zero (Thompson's re-estimate for Liberty ships; professional services) through 0.49 per year (the L-1011) to 1.9–3.5 per year (the early Liberty-ship and franchise estimates). For a cyber force, the causes I could quantify add up to roughly 0.2–0.4 per year. These causes are exploit disclosure (about 0.15–0.19 per year), staff attrition (3–6% per year across the whole NSA, and higher for technical staff) and rotation out of operator roles (about 0.11–0.25 per year). That supports the default of 0.3, but it does not exclude the region below 0.2 where the model becomes unstable.

### Cited Findings
**Organizational depreciation in production and services**
- **Lockheed L-1011: δ = 0.96 per month, so 61% of experience survives a year.** My conversion: a yearly loss rate of 0.49 (39% lost each year). Quote: "The value δ = 0.96 implies that 61 percent (0.96^12) of the firm's stock of experience existing at the beginning of a year survives to the end of the year." Benkard names these causes: turnover and layoffs; "Some tasks performed by workers are repeated only rarely"; and "a high depreciation rate is also justified by the effects of turnover", with union "bumping" rules multiplying company turnover. — [Benkard, NBER WP 7127](https://www.nber.org/papers/w7127.pdf). *Date: 1999/2000 (older); Read: full; Type: measurement; Applies: transfer.*
- **Earlier estimates (Liberty ships, Argote, Beckman & Epple 1990; pizza franchises, Darr, Argote & Epple 1995): monthly parameter 0.75–0.85, so 5–15% kept per year.** My conversion: 0.75^12 = 3.2% and 0.85^12 = 14% kept, a yearly loss rate of 1.9–3.5. Quote: "the depreciation parameter was estimated to be in the range 0.75-0.85, suggesting that only 5-15 percent of experience was retained from year to year." — [Benkard, footnote 39](https://www.nber.org/papers/w7127.pdf). *Date: 1990/1995 estimates (older); Read: secondary report inside a primary paper (the originals were not opened); Type: measurement; Applies: transfer.*
- **Forgetting did not depend on output in the L-1011 data.** Quote: suggestions to make "depreciation to be a function of output or the change in output … was not supported by the data." Benkard also notes that "the rate of experience depreciation is under the firm's control" (for example, by avoiding layoffs). — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: measurement and opinion; Applies: transfer (bears on burn_share).*
- **Forgetting has been found where work is labour-intensive and turnover is high.** Quote: the three industries with documented forgetting share "the products are labor intensive, learning is thought to be important at the individual worker level, and all three experience relatively high turnover." — [Benkard](https://www.nber.org/papers/w7127.pdf). *Date: 2000 (older); Read: full; Type: author's synthesis; Applies: transfer.*
- **Critique: a re-estimate for Liberty ships finds forgetting "much smaller … and may well be zero".** Quote: archive-based estimates "yield rates of forgetting that are much smaller than previously reported, and may well be zero." The paper also controls for product mix and examines "the relationship between organizational forgetting and labor turnover." — [Thompson (2007), Management Science 53(6):908–918, EconPapers abstract](https://econpapers.repec.org/RePEc:inm:ormnsc:v:53:y:2007:i:6:p:908-918). *Date: 2007 (older); Read: abstract only; Type: measurement; Applies: transfer.*
- **Pizza franchises (36 stores, weekly data over about 1.5 years): knowledge "found to depreciate rapidly". It transferred between stores of the same owner, but not between stores of different owners.** — [Darr, Argote & Epple (1995), Management Science 41(11):1750–1762, EconPapers listing](https://econpapers.repec.org/RePEc:inm:ormnsc:v:41:y:1995:i:11:p:1750-1762). *Date: 1995 (older); Read: abstract text seen in search results (page not opened); I did not find the weekly rate; Type: measurement; Applies: transfer (a transfer pattern that matches compartments and secrecy).*
- **Professional services: "virtually no depreciation of knowledge".** — [Management Science 54(7):1231–1236, "Learning and knowledge depreciation in professional services", IDEAS listing](https://ideas.repec.org/a/inm/ormnsc/v54y2008i7p1231-1236.html). *Date: 2008 (older); Read: abstract snippet in search results only; Type: measurement; Applies: transfer (knowledge work is closer to cyber work than assembly is).*

**Individual skill decay without practice**
- **Procedural skills: half of the gains from training are lost after about 6.5 months without use for accuracy, 13 months for speed, and 11 months for mixed measures.** Gains decline by 0.08 SD a month (accuracy) and 0.06 SD a month (speed and mixed). Scope: 1,344 effect sizes from 457 reports. Quote: "half of initial skill acquisition performance gains were lost after approximately 6.5 months for accuracy". My conversion to exponential-equivalent yearly rates: 1.28 (accuracy), 0.64 (speed) and 0.76 (mixed); the paper's model is linear, so these are approximate. — [Tatel & Ackerman (2025), Psychological Bulletin 151(6):696–736, Europe PMC record](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:40455501%20AND%20SRC:MED&resultType=core&format=json). *Date: June 2025; Read: abstract; Type: measurement (meta-analysis); Applies: transfer (individuals, during non-use).*
- **Earlier meta-analysis: decay grows from d = −0.01 just after training to d = −1.4 after more than 365 days without use, and cognitive, accuracy-based tasks decay more.** Scope: 189 data points from 53 articles. Quote: "Physical, natural, and speed-based tasks were less susceptible to skill loss than cognitive, artificial, and accuracy-based tasks." — Arthur, Bennett, Stanush & McNelly (1998), Human Performance 11:57–101; abstract text seen only in search results ([index page](https://data.zhenzhi.com/details/1/913518324) refused, 403). *Date: 1998 (older); Read: abstract snippet only; Type: measurement; Applies: transfer.*

**Staff turnover in cyber and signals-intelligence organizations**
- **NSA attrition was 3.3% in 2015 and "a little less than six percent" by about 2016–17, among about 36,000 employees.** Quotes: "little less than six percent"; "3.3 percent in 2015" (Director Rogers); attrition had "seen a steady rise" since 2009. — [Reuters via Canadian HR Reporter](https://www.hrreporter.com/news/hr-news/us-spy-agency-risks-talent-exodus-amid-morale-slump-trump-fears/286406). *Date: 1 March 2017 (older); Read: full secondary report; Type: agency figures (measurement); Applies: direct (a US SIGINT agency, all staff, not only operators).*
- **"Several hundred" NSA hackers, engineers and data scientists left after 2015.** Quote: "Since 2015, the NSA has lost several hundred hackers, engineers and data scientists." — Washington Post, 2 January 2018, as excerpted on [Slashdot](https://politics.slashdot.org/story/18/01/03/0637257/nsas-top-talent-is-leaving-because-of-low-pay-slumping-morale-and-unpopular-reorganization). [Newsweek](https://www.newsweek.com/nsa-faces-brain-drain-amid-plunging-morale-placing-national-security-risk-768994) adds: "The NSA employs a civilian workforce of around 21,000" and blames "A controversial reorganization initiative, poor leadership and a climate of suspicion". *Date: January 2018 (older); Read: secondary reports; Type: anonymous officials' estimate; Applies: direct.* Conflict: Reuters gives about 36,000 employees and Newsweek about 21,000 civilians, so the bases differ.
- **Technical staff leave early in their careers, often for pay.** Quotes: "We lose more technical people at much higher rates to resignations early on in their careers" (NSA official); "I'm leaving to double my salary" (exit interview); "25 percent of our millennials are turning over" (an official of the Under Secretary of Defense for Intelligence; the period and base are unclear). — [Defense One](https://www.defenseone.com/business/2015/04/nsas-fight-keep-its-best-hackers/110401/). *Date: 16 April 2015 (older); Read: full; Type: officials' statements; Applies: direct.*
- **Military advanced cyber (ION) training "may take a year or more and costs DOD hundreds of thousands of dollars". Service obligations after it are short or missing:** Navy and Air Force 3 years; Army officers "about 1.88 years"; Marine Corps none. Trained people "may not remain in the military for a significant time after training". — [GAO-23-105423](https://www.gao.gov/products/gao-23-105423). *Date: 21 December 2022; Read: GAO product page and highlights (not the full report); Type: audit measurement; Applies: direct.* A search snippet of [Nextgov's coverage](https://nextgov.com/cybersecurity/2022/12/military-branches-losing-expensive-cyber-talent-private-sector-watchdog-says/381261) adds that the services "spent at least $160 million on cyber retention bonuses annually in fiscal years 2017 through 2021" (not opened).
- **Cyber Mission Force: full proficiency takes "about 10 years", but service career rules move operators out of tactical missions after 6–9 years and analysts within 4–6 years.** Quotes: "This high turnover creates a cycle of perpetual amateurism in the Cyber Mission Force"; "U.S. military cyber forces have never met the department's readiness standards"; "The primary drivers of low retention have been poor talent management and poor leadership". As an analogy, a typical team has 1 elite member, 4 fully trained, 6 qualified only where there is no threat, and 8 still in initial training. The detailed readiness data are classified. — [Cobb, War on the Rocks](https://warontherocks.com/2025/05/an-insiders-guide-to-cyber-readiness/). *Date: 1 May 2025; Read: full; Type: insider's estimate and opinion; Applies: direct.*
- **UK: GCHQ headcount fell to 7,082 full-time equivalents (year to March 2022) from 7,181. More than 200 roles were unfilled, against more than 460 the year before.** Quote: the "first time that the agency's total headcount has gone down in the five years"; causes include "the distance between public and private sector salaries for cyber specialists" and "The lengthy hiring process". The article gives no turnover rate. — [The Record](https://therecord.media/gchq-workforce-shrinks-isc-report). *Date: 6 December 2023; Read: full; Type: measurement (Intelligence and Security Committee data); Applies: direct (UK SIGINT).*

**Tools lost to patches and disclosure ("burned" tools)**
- **Zero-day vulnerabilities live 6.9 years on average from private discovery to public disclosure. 25% die within 1.5 years and 25% live more than 9.5 years. The collision rate is about 5.7% per year.** Quotes: "the time between initial private discovery and public disclosure"; "25 percent of vulnerabilities do not survive to 1.5 years"; "only 25 percent live more than 9.5 years"; "approximately 5.7 percent per year". My conversion: average hazard 0.19 per year over the first 1.5 years, and 0.15 per year to the 75th percentile. — [RAND release (EurekAlert)](https://www.eurekalert.org/news-releases/855015). *Date: 9 March 2017 (older, before AI-assisted discovery); Read: official news release; Type: measurement (more than 200 exploits from one vendor); Applies: direct (one vendor's stockpile, not a state's).*

**Secrecy and fragmentation**
- **Ukrainian MP Oleksandr Fediienko says state bodies "compete" with one another in cyberspace "instead of working against the enemy", and cyber units "still lack a formal legal status".** — [Militarnyi](https://militarnyi.com/en/news/ukraine-access-to-eu-cybersecurity-reserve/). *Date: 23 June 2026; Read: full; Type: opinion; Applies: direct (Ukraine).*

### Inferences
**Converted yearly loss rates (my conversions)**

| Source | Share kept after 1 year | Yearly loss rate |
|---|---|---|
| Liberty ships and franchises, early estimates | 3–14% | 1.9–3.5 |
| L-1011 (Benkard) | 61% | 0.49 |
| Liberty ships, re-estimate (Thompson) | ≈100% | ≈0 |
| Professional services | ≈100% | ≈0 |
| Individual skills, no practice (half-life 6.5–13 months) | 28–53% of the gain | 0.64–1.28 |
| NSA attrition (all staff) | 94–97% stay | 0.03–0.06 |
| CMF rotation out of role (operators 6–9 years, analysts 4–6 years in role) | — | 0.11–0.17 (operators), 0.17–0.25 (analysts) |
| Zero-day disclosure hazard | 81–86% survive | 0.15–0.19 |

**forget_rate (0.3 per year; 0.1–0.7).**
- Patches and disclosure contribute about 0.15–0.19 per year for tools.
- Staff attrition and rotation contribute 0.03–0.25 per year of people. Only part of what a leaver knows is lost, because tools, documents and procedures stay. So the staff part of the loss of lessons is perhaps 0.01–0.15. That share is an unreviewed assumption.
- Lessons also go stale as defenders change their networks, but I found no figure for this.
- Sum: roughly 0.2–0.4 per year. **Verdict: supports the default.** The range 0.1–0.7 covers these components. The literature's full spread (0 to 3.5) is wider than the range.
- The instability threshold (below about 0.2) sits at the low edge of this band. Thompson's re-estimate and the professional-services result both show that very low forgetting is possible, so **the evidence does not exclude the unstable region.**
- Lessons are not tools. A burned exploit loses the tool, but not what the force learned about how targets and effects behave. So the hazard of tools being burned is an upper bound for the part of lost lessons that comes from patches.

**burn_share (0; 0–0.8).**
- RAND's disclosure hazard is for stockpiled vulnerabilities, whether or not they were used. At today's low volume of attacks, loss without use probably dominates.
- Benkard found that depreciation did not depend on output, but that was in production, where use does not expose the tool.
- **Verdict: 0 is defensible as today's working value, but it is an assumption.** No measurement of burn driven by use was found. The mechanism is plausible, because exposed attacks reveal tools in a way that production does not.

**Kill-chain stages.**
- *Access and tools* (shared with surveillance) are lost to patches and detection at about 0.15–0.19 per year, whether or not they are used.
- *Effects-specific skills* (effects design, delivery, battle-damage assessment) get little practice, so the decay of individual skills without use applies: a half-life of 6.5–13 months, or 0.6–1.3 per year, for unpractised parts. Benkard's remark that tasks "repeated only rarely" depreciate faster points the same way.
- *Target analysis* is a cognitive, accuracy-based task. That type decays fastest without use, but surveillance uses it every day, so it stays fresh for the shared chain.
- *Turnover* hits every stage. It hits analysts hardest (4–6 years in role), then operators (6–9 years).
- *Secrecy:* Darr et al. found that knowledge moved only between stores with the same owner. Each compartment (NSA, Cyber Command, the services) may act like a separate franchisee. If so, lessons are effectively kept only within each compartment, which acts like lower reliability or faster forgetting.

### Gaps
- I did not open the primary Liberty-ship paper (Argote, Beckman & Epple 1990, Management Science 36(2):140–154); the PDF host returned an empty page. I also did not obtain the primary weekly rate for the franchises or Thompson's numerical estimate.
- An NSA attrition rate for hackers and watch centres of 8–9% (and 5.6% for STEM staff) appeared only in a search-engine summary of the 2018 Washington Post report, and I could not confirm it on any page I opened. Treat it as unverified.
- I found no published attrition rate for the Cyber Mission Force, the UK National Cyber Force or GCHQ. A search snippet said that the ISC's 2023–2025 annual report records GCHQ recruiting 774 staff against a target of 1,131; I did not open it.
- There is no measurement of tools burned through use (exposure per attack).
- The search budget ran out before I could gather Mandiant figures on time-to-exploit or dwell time.
- Possible leads, not read: "Learning and Forgetting in the Jet Fighter Aircraft Industry" (2017 working paper, [IDEAS](https://ideas.repec.org/p/mal/wpaper/2017-2.html)); "On the Determinants of Organizational Forgetting" ([MPRA 21464](https://ideas.repec.org/p/pra/mprapa/21464.html)).

## 3. Damage-assessment reliability: how often do assessments of effects err, and in which direction?

### Takeaway
In the best-documented campaigns, effects assessments erred mostly toward overstatement:
- by factors of about 1.3–1.6 for bomb hit rates and about 4 for bombs per aimpoint (Desert Storm);
- by 4 to 22 for vehicle kills (Kosovo);
- with no confirmed kills against claimed Scud-hunting success.

The errors were shared across whole campaigns, and the first claims were the most inflated. Cyber-specific evidence shows contested or undetectable effects. In contrast, a well-run strategic intelligence unit was well calibrated and slightly underconfident. The model's assessment error has a zero median and averages over outcomes, giving only about 0.14 log units a year today. That is much smaller, and less biased, than these historical errors.

### Cited Findings
**Desert Storm air campaign (GAO, 1997)**
- **F-117 accuracy was claimed at 80%; GAO estimated a 41–60% chance of hitting a target in a planned F-117 strike.** Quotes: "80 percent of the bombs dropped by F-117s hit their target" (DOD title V report); about one-third of reported F-117 hits "either lacked corroborating support or were in conflict with other available data"; "BDA on 11 of the F-117 strategic air defense targets confirmed only 2 complete kills." On the first night, Lockheed claimed 37 targets struck; GAO found 21 of the 37 tasked targets reported hit.
- **Laser-guided bombs:** the claim of "one target, one bomb" "could not be validated"; "no single aimpoint was struck by only 1 LGB" (an average of 4, at most 10).
- **Scuds:** the campaign against mobile launchers "did not achieve any confirmed kills".
- **Republican Guard:** CIA analysis showed "more than 70 percent of the tanks in three Republican Guard divisions" intact when the ground war began.
- **Coverage and timeliness:** "DIA conducted BDA on only 357 of the 862 strategic targets" (41%). "The BDA was neither as timely nor as complete as planners had apparently assumed it would be." The main database "in most cases did not benefit from ground verifications or damage updates after the war".
- **Success by target set:** targets with objectives met ranged from 76% (known nuclear, biological and chemical targets) to 25% (fixed Scud-related targets). "Less than 15 percent of the nuclear-related facilities were identified before the end of the air campaign."
- — [GAO/NSIAD-97-134, Operation Desert Storm: Evaluation of the Air Campaign](https://www.govinfo.gov/content/pkg/GAOREPORTS-NSIAD-97-134/html/GAOREPORTS-NSIAD-97-134.htm). *Date: June 1997 (older); Read: first 100,000 characters of the full report (the rest unread); Type: audit measurement; Applies: transfer (kinetic battle-damage assessment).*

**Kosovo 1999**
- **Claimed against confirmed, for tanks / armoured personnel carriers / artillery:** Pentagon's tentative estimate, June 1999: 120 / 220 / 450. NATO's assessment of successful strikes, September 1999: 93 / 153 / 389. Newsweek, May 2000, from a draft of the ground survey: 14 / 18 / 20. Serb claims: 13 / 6 / 27. The ground survey found 14 tanks plus 12 self-propelled guns that look like tanks.
- **Why the counts differ:** the survey began in July 1999, and some sites were first visited three months after the strikes: "the Serbs had plenty of time to remove and repair any equipment sustaining less drastic damage". The survey's own task was limited: "Our job was to investigate what equipment was remaining from those strikes." NATO required each strike to be confirmed by at least one other source, a rule the survey team judged "conservative". The team said about 60 more tanks were probably hit but could not be confirmed.
- — [Air & Space Forces Magazine, "Newsweek and the 14 Tanks"](https://www.airandspaceforces.com/article/0700newsweek/). *Date: July 2000 (older); Read: full; Type: official claims (estimates) against ground-survey counts (measurement). The source is an Air Force-aligned magazine that argues the survey undercounts; Applies: analogy.*

**Cyber campaign against ISIS, 2016 (Operation GLOWING SYMPHONY, Joint Task Force ARES)**
- **The defense secretary judged it a failure while Cyber Command judged it a success.** Ash Carter, then Secretary of Defense, wrote that he was "largely disappointed": "It never really produced any effective cyber weapons or techniques." Cyber Command's intelligence director, Brig. Gen. Timothy Haugh, replied: "When you look back now over the last year, we've really made some enormous strides." The article names no metrics. — [Defense News](https://www.defensenews.com/smr/cybercon/2017/11/28/how-cybercoms-efforts-against-isis-have-changed/). *Date: 28 November 2017; Carter's blog post October 2017 (older); Read: full; Type: opinion (the principal against the operator); Applies: direct.*
- **Cyber Command's own assessments of up to 120 days judged the operation a success, but the redacted reports "do not reveal whether the operation achieved its wider intended effect".** The reports say it "imposed time and resource costs" on ISIS. The decline in ISIS's English-language online activity happened at the same time as more Coalition airstrikes and battlefield gains. — [The Defense Post](https://thedefensepost.com/2020/01/21/us-cybercom-glowing-symphony-isis/amp/). *Date: 21 January 2020; Read: full; Type: secondary report of declassified self-assessments; Applies: direct.*
- **Outsiders have "very little data publicly available by which to judge"; "Public understanding of the effectiveness of US cyber operations is hindered by secrecy".** Public research found "a sizable downtick in ISIL's use of social media that tracks with the timing of GLOWING SYMPHONY's launch". The activity "dropped markedly and did not cycle back up". The concept of operations listed measures of performance and of effectiveness, but they are redacted. — [National Security Archive](https://nsarchive.gwu.edu/briefing-book/cyber-vault/2018-08-13/joint-task-force-ares-operation-glowing-symphony-cyber-commands-internet-war-against-isil). *Date: 13 August 2018 (older); Read: full; Type: analyst's assessment; Applies: direct.*

**Wartime cyber effects in event data**
- **Cyber attacks in Ukraine and Syria showed no discernible effect on fighting.** Quotes: "cyber activities failed to compel discernible changes in battlefield behavior"; Ukraine, "little or no impact on fighting"; Syria, "the timing of cyber actions is independent of fighting on the ground"; "cyber attacks are not (yet) effective as tools of coercion in war". Data, from search snippets only: 1,841 cyber attacks and 26,289 kinetic operations (Ukraine, 2014–16); 682 cyber attacks and 9,282 acts of violence (Syria, 2011–16). — [Kostyuk & Zhukov, Journal of Conflict Resolution 63(2):317–347, IDEAS abstract](https://ideas.repec.org/a/sae/jocore/v63y2019i2p317-347.html). *Date: 2019 (older); Read: abstract; Type: measurement; Applies: direct for low-end, mostly non-state cyber activity; weaker for a capable state's operations.*

**Calibration of intelligence judgments**
- **Canada's Intelligence Assessment Secretariat (1,514 forecasts by 15 analysts, March 2005 to December 2011) was well calibrated and slightly underconfident.**
  - Discrimination: area under the ROC curve 0.940; about 94% of forecasts correctly classified.
  - Accuracy and calibration: mean Brier score 0.074; calibration index 0.016.
  - Direction: underconfident, with a signed confidence index of −0.076. Underconfidence was larger for harder forecasts (−0.106 against −0.044) and for more important ones (−0.071 against −0.044).
  - Recalibration cut the mean absolute deviation from perfect calibration from 12.7% to 4.2%.
  - About 20% of numeric forecasts had outcomes too ambiguous to score, and two coders agreed 90% of the time.
  - The full text describes the discrimination as "very good". I did not capture its exact sentences, so the numbers above are as reported.
  - — [Mandel & Barnes, PNAS 111(30):10984–10989, PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/4121776/). *Date: 2014 (older); Read: full text; Type: measurement; Applies: transfer (strategic forecasts whose outcomes can be seen, not effects assessment).*
- **Critique:** Tetlock & Mellers ([PNAS commentary, PMC](https://pmc.ncbi.nlm.nih.gov/articles/4136586/)) say the "hard" and "easy" labels are not standardized, and that the study does not show analysts are typically well calibrated. *Date: 2014 (older); Read: search snippet only; Type: opinion.*

### Inferences
**Direction and size of errors (log ratio of claimed to confirmed; my conversions)**

| Case | Log ratio |
|---|---|
| F-117 hit rate (0.80 against 0.41–0.60) | 0.29–0.67 |
| Bombs per aimpoint (1 against an average of 4) | 1.39 |
| Kosovo first claims against ground-found tanks, APCs, artillery | 2.15, 2.50, 3.11 |
| NATO's own revised count against physical evidence (93 against 26) | 1.27 |
| First claim against NATO's revision | 0.15–0.36 |
| Scuds (claimed kills against zero confirmed) | without limit |

Operators' and services' own assessments overstate. Strategic forecasters in a unit with no stake in the outcome understated their confidence. **So the direction depends on who assesses and on their incentives.** In the ISIS case, the operator and the principal disagreed completely, from "enormous strides" to "never really produced any effective cyber weapons".

**What the model assumes (my reading of the model file).**
- The yearly assessment draws a log error with median 0 ("In the central run its draw is the median, 0").
- Its spread is sqrt((1 − success)/success × spread/(yearly targets + 1) + assessment_noise²/(learn rate + 1)), so the per-outcome noise averages out as volume grows.
- At today's defaults this gives about **0.14 log units a year** (my computation: sqrt(4/236 + 0.25/95)).

The evidence contradicts this in three ways:
1. *Bias:* the median error of the operator's assessment is positive, not zero.
2. *Common error:* the same claims came from DOD, the Air Force and the contractor alike, and Kosovo inflated all three vehicle types by similar factors. Such errors do not average out with volume.
3. *Size:* single-campaign errors of 0.3–3 log units are 2–20 times larger than 0.14.

A non-averaging, campaign-level error term (perhaps 0.3–1.0 log units) and an optional bias term (perhaps +0.25 to +1.3 log units) would follow these cases. Both would be unreviewed assumptions anchored on these cases.

**assessment_reliability (0.4; 0.1–0.9).**
- Desert Storm: assessment covered 41% of strategic targets, and about two-thirds of the F-117 hits that were reported were corroborated. Together that keeps about 0.27 of outcomes (my inference).
- Kosovo: 26 of 93 claimed strikes on tanks and self-propelled guns were physically confirmed (0.28).
- ISIS: contested.
- Intelligence forecasts with outcomes that can be seen: about 0.8 could be scored, which is an upper bound for a well-instrumented setting.
- **Verdict: supports the default and narrows the plausible range for effects to about 0.2–0.5.** The instability threshold (above about 0.58) lies above every battle-damage analogue. Today's evidence therefore favours the stable regime, unless assessment improves a lot. That AI could make that happen is speculation and is not shown here.

**assessment_noise (0.5; 0.1–1.5).**
- Per-outcome errors in these cases run from 0.3 to 1.4 log units, and first claims reach 2–3.
- **Verdict: the default is at the low end, and the range covers most cases.** The bigger issue is structural: the averaging and the zero median, as described above.

**Timing.** Claims are revised over months: Kosovo went from June 1999 to September 1999 to May 2000, ISIS was assessed at 120 days, and GAO reported six years after the war. A yearly assessment that reads first claims uses the most inflated number.

**Kill-chain stages.** Assessment is a stage of its own with its own reliability. Desert Storm also shows a failure at target identification ("Less than 15 percent of the nuclear-related facilities were identified"), so the target-analysis stage limits success independently of weapon accuracy. Espionage outcomes (data in hand) can be seen directly, and the Mandel & Barnes unit shows that intelligence judgments can be checked. **So the surveillance return is probably assessed more reliably than the attack return.** The model compares both returns, so this asymmetry matters.

**Success per target.** In Desert Storm, the share of targets whose objectives were met ran from 25% to 76% by target set. This is close to the model's range for success per target, from 20% to 70% (an analogy only).

### Gaps
- I did not gather the cyber battle-damage-assessment literature (joint doctrine on assessing cyber effects, Air Force Institute of Technology theses), because the search budget ran out.
- The figures in Cyber Command's 120-day assessment remain redacted.
- I could not open the NPR 2019 story on the ISIS operation (HTTP 503), which has the operators' own success quotes.
- There is no direct measurement of error rates in assessing cyber effects for a capable state.
- The Kosovo source is partisan, and the true number of vehicles destroyed is unknown. The ground survey undercounts and the first claims overcount.

## 4. Do budgets follow assessed results, and with what delay and strength?

### Takeaway
Budgets follow assessed performance weakly and slowly:
- In the best US study, 10 points on OMB's 100-point PART scale moved the President's proposed budgets by 4–5%, and the "results" part of the score counted least.
- The PPBE process starts more than two years before the money is spent.
- US military cyber budgets kept rising (+4.1% in the FY2026 request) even though readiness standards were never met and a defense secretary was publicly disappointed.
- Ukraine's plan to pay cyber units bonuses graded by results had not passed by June 2026.

This evidence points to steepness below the default, and to adjust_time at 2 years or more.

### Cited Findings
- **Performance scores moved proposed budgets modestly: +10 PART points (on 0–100) gave +4–5% in the President's FY2005 budget.** Scope: 176 newly assessed programs plus 234 assessed for FY2004. Quotes: "an increase in PART score by 10 points will lead to a budget increase of 4–5 percent"; "the ''results'' component of PART scores has a smaller impact on budget decisions than the ''program purpose'' component"; "In the FY 2004 budget, ''results not demonstrated'' was the most common management grade, accounting for 51 percent of the 234 programs evaluated" (41% of the 176 new programs in FY2005); "performance and results do not play as prominent a role as might be expected"; "it appears likely that results influence budget allocations more for programs with good measures"; and "it is still unclear how performance information is being used in appropriations". — [Gilmour & Lewis, JPART 16(2):169–186 (author-hosted PDF)](https://cdn.vanderbilt.edu/t2-my/my-prd/wp-content/uploads/sites/411/2018/07/gilmourlewis2006.pdf). *Date: 2006 (older); Read: full text; Type: measurement (regression); Applies: transfer (US federal programs, proposals rather than appropriations).*
- **The PPBE timing: "typically begins more than two years before the expected year of budget execution"; each POM is "a funding plan for each component covering a five-year period" (the Future Years Defense Program).** — [CRS In Focus IF10429, Defense Primer: PPBE](https://www.everycrsreport.com/reports/IF10429.html). *Date: updated 6 December 2024; Read: first 100,000 characters; Type: official description; Applies: direct (US DoD).*
- **US cyber budgets rise steadily and are not tied to results.** The FY2026 cyberspace-activities request is "approximately $15.1 billion", "4.1% more than the previous year's request" (FY2025 about $14.5 billion). "Approximately $2.6 billion of the cyberspace operations budget is designated for CYBERCOM resources", including about $1.3 billion for the Cyber Mission Force and $314 million for the headquarters. The report links no funding to readiness or operational results. — [CRS Insight IN12616](https://www.everycrsreport.com/reports/IN12616.html). *Date: 24 November 2025; Read: full; Type: official budget data; Applies: direct.*
- **The money flows despite failing readiness.** The DoD spends "$14 billion a year on cyber forces and technology", yet "U.S. military cyber forces have never met the department's readiness standards" and "Training has continuously been at failing levels since Cyber Command first established training standards." — [Cobb, War on the Rocks](https://warontherocks.com/2025/05/an-insiders-guide-to-cyber-readiness/). *Date: 1 May 2025; Read: full; Type: insider's opinion and estimate; Applies: direct.*
- **The split between intelligence and attack is negotiated case by case.** Quote: the "intel gain-loss discussion has always been there" (Col. Todd Stratton). Carter also blamed the intelligence community for delaying or preventing the use of cyber tools to protect collection; that point comes from the search summary of the same article. — [Defense News](https://www.defensenews.com/smr/cybercon/2017/11/28/how-cybercoms-efforts-against-isis-have-changed/). *Date: 28 November 2017 (older); Read: full; Type: official's statement; Applies: direct.*
- **Ukraine's bill on Cyber Forces (draft law No. 12349) passed first reading on 9 October 2025 with 255 votes, but had not passed second reading by 23 June 2026.** Quote: "The legislation must pass a second reading and be signed by the president before becoming law." — [Kyiv Independent](https://kyivindependent.com/ukraines-parliament-backs-creation-of-cyber-forces-in-first-reading/) (9 October 2025; read in full). The bill was revised in March 2026 to add incentives for successful operations, and the units "still lack a formal legal status". — [Militarnyi](https://militarnyi.com/en/news/ukraine-access-to-eu-cybersecurity-reserve/) (23 June 2026; read in full). *Type: news reports of legislative status; Applies: direct (Ukraine).*
- **Reported bonus design (unverified): one-time payments graded by the level of the operation.** Search summaries of Ukrainian legal-news pages said the Commander-in-Chief may award 100 subsistence minimums (332,800 hryvnias in 2026) for strategic and operational operations, and up to 400 for a strategic operation by decision of the President. One headline reads "Successful Operations Can Earn Over 1 Million Hryvnias". Another report says base pay would be 1.8 times that of other Armed Forces members. — [sud.ua](https://sud.ua/en/news/laws/363897-v-vsu-gotovyatsya-sozdat-kibersily-za-uspeshnuyu-operatsiyu-mozhno-budet-poluchit-bolee-1-milliona-griven) (refused, 403); [Scroll](https://scroll.media/en/?p=27714) (not opened). *Read: search snippets only; the figures conflict; Type: reported bill provisions.*

### Inferences
**steepness (8; 2–20). Mapping to the model's form (my computation).**
- The model sets target share = floor + (ceiling − floor)/(1 + e^(−steepness × gap)), with floor 0.03, ceiling 0.5 and today's share 0.083.
- So the relative response of the target share to the return gap at today's rest point is 0.567 × steepness. That is 4.5 at the default: a gap of +0.1 (10% of today's surveillance return per expert) raises the target share by about 45%.
- The PART result is a semi-elasticity of about 0.4–0.5. If 10 PART points are taken as equal to a return gap of 0.1, steepness ≈ 0.7–0.9, which is below the range.
- The mapping is uncertain. A 10-point PART difference is a large rating gap, so it probably stands for a large return difference, which would push the equivalent steepness still lower. Reallocations inside one agency might respond more strongly than OMB program budgets, but I found no measurement of that.
- **Verdict: the evidence contradicts the default if the mapping holds, and favours the low end (2) or below. The instability threshold (above about 13.5) is far outside every analogue.**
- **Budgets respond less when measures are poor.** Results counted less where 40–51% of programs lacked adequate measures. This suggests that steepness should fall when assessment reliability is low. That would be an interaction of steepness with the model's assessment signal, which the model does not have today (an unreviewed proposal).

**adjust_time (2 years; 1–5).**
- Money cannot follow a result in less than about two years without reprogramming or a supplemental. No data on how fast those work were found.
- Trained capability follows more slowly still: a year or more of advanced training, and about 10 years to full proficiency.
- **Verdict: supports the range. The default is at the fast end, and a central value near 3 years fits better.**
- The model uses a first-order lag. The PPBE gap is closer to a fixed delay, so a structure with a delay plus smoothing (for example, a 2-year pipeline and then a 2-year adjustment) would be more faithful.

**The pattern from 2016 to 2026.** Cyber budgets rose steadily even though results were contested (ISIS) and readiness standards were never met. So budgets followed threat, strategy and organizational momentum rather than assessed results. That fits the "stable marginal program" reading at today's split.

**Ukraine.** Bonuses graded by results reward claimed successes at the level of people, not budgets. If they are adopted, they would add an incentive to overclaim, which links to the upward bias in Section 3. There is no evidence yet on what they would do.

**Consolidated mapping of the nine inputs**

| Input (default; range) | Main evidence | Verdict |
|---|---|---|
| forget_rate (0.3; 0.1–0.7) | Sum of components ≈0.2–0.4; L-1011 0.49; Thompson ≈0; early estimates 1.9–3.5 | Supports default; the region below 0.2 cannot be excluded |
| burn_share (0; 0–0.8) | Disclosure of stockpiled tools without use (RAND); production depreciation not tied to output (Benkard) | Default defensible today; no measurement (assumption) |
| cost_learning (0.3; 0–0.6) | Industry: 20–40% per doubling; the model at default ≤5.5% per doubling | Conservative against analogies; not narrowed for cyber |
| prior_strength (5,000; 300–20,000) | No direct evidence; team-level gains within about 10 missions, or one review (TOPGUN) | Not narrowed; leans lower for team skills |
| curve_shape (1; 1–3) | Wright's power law fits best; no industrial threshold | Supports 1 |
| assessment_reliability (0.4; 0.1–0.9) | Desert Storm ≈0.27, Kosovo 0.28; intelligence forecasts ≈0.8 at best | Supports default; narrows to about 0.2–0.5 for effects |
| assessment_noise (0.5; 0.1–1.5) | Per-outcome errors 0.3–1.4, first claims 2–3; biased and shared across a campaign | Default low; the zero-median, averaging structure is contradicted |
| adjust_time (2; 1–5) | PPBE lead time over 2 years; training a year or more; 10 years to full proficiency | Range supported; central value nearer 3 |
| steepness (8; 2–20) | PART equivalent ≈0.7–0.9 (if the mapping holds); cyber budgets rise whatever the results | Contradicts default; favours 2 or below |

Overall:
- The evidence favours the model's stable regime on steepness and reliability. It is ambiguous on forget_rate and says nothing on prior_strength.
- Three of the four instability thresholds act through one ratio (lessons today over prior strength, ≈0.063 against a critical ≈0.09), which no evidence pins down within ±40%.
- Most of the quantitative evidence is older (before 2020) and comes from manufacturing or kinetic analogues. Direct cyber measurements are few.

### Gaps
- I found no study of how Cyber Command's or the NSA's budgets changed after specific campaigns (for example, after the 2016 ISIS campaign or the 2018 election-security operations), and no data on how fast reprogramming works.
- I did not open the companion study (Gilmour & Lewis, Public Administration Review 66(5), 2006, on FY2004). A search snippet says the effect of management scores "diminished as the political component was taken into account".
- There is no appropriations-level evidence on whether Congress follows PART-like scores.
- I did not read the text of Ukraine's bill or its final bonus provisions (sud.ua refused, 403). The amounts reported in different places conflict.
- I did not open the final report of the Commission on PPBE Reform (March 2024). A search snippet says it found that the process "lacks agility" and recommended replacing it.
