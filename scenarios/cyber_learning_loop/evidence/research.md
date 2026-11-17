# Consequence research

Research date: 2026-11-07. Executable definitions: SC45. Currency: USD2025 for money that the model
spends; source figures keep their own price year. Value: SEV, the yearly value of one expert on
surveillance in 2026.

## SC45: A country's cyber attacks and the learning loop

SC45 does not follow the harm of an attack. It follows one capable country's split of its cyber
experts between surveillance and attacks, the lessons that its attacks teach, the attention and the
fixes of the defenders, and whether campaigns become reliable enough for military plans. Deaths, serious
casualties and economic loss are declared not estimated.

The research that this version of the model follows is in [research/](research/): the report
([research/report.md](research/report.md)) and the notes of its eight threads. Its quotes and numbers
are not records until integration verifies them.

### How the model uses its evidence

- **Today's split.** The pool of experts is the NSA workforce, about 39,000 in 2024 less about 2,000
  that it shed in 2025 (E-SC45-NSA-WORKFORCE), and the 3,535 attack-oriented posts of the Cyber Mission
  Force, which has 133 teams and roughly 6,200 people (E-SC45-CMF-SIZE): 40,535 people.
  - The share on attacks, 3,535 / 40,535 = 0.087, is a staff ratio of about 10.5:1. Its range covers the staff ratios
    6.3:1 to 12.7:1 and the money ratios 5.4:1 to 8.9:1 that the essay's workbook gives. Cyber
    Command's $191 million in fiscal 2013 sets the money side (E-SC45-CYBERCOM-BUDGET).
  - The workbook is a spreadsheet, so the model reads none of it: these sources are its primary
    sources.
- **Revealed preference.** Today's split is a rest point of the funding rule, and the value of one
  intended effect follows from it in closed form. The rule is centered on today's split, so an expert
  on attacks and an expert on surveillance return the same today. So the model calibrates value by the
  country's revealed choice, not by the essay's claim that attacks do not pay.
  - Budgets follow results slowly and weakly. The defense budget process starts more than two years
    before the money is spent (E-SC45-PPBE), so the split takes three years to move about two thirds
    of the way to its target. In one study of US programs, 10 points on a 100-point performance score
    moved proposed budgets by 4 to 5% (E-SC45-PART-BUDGET, partial: the PDF could not be extracted by
    the recorded extractor). If those 10 points stand for a difference in returns of 0.02 to 0.1, the
    steepness of the funding response is about 0.8 to 4, so the default is 2.
  - At the default values, today's split is also stable (leading eigenvalue about −0.07 a year; the
    stocks of attacks on their way slow its return from about −0.13). Two decades of a marginal
    effects program suggest this. With the other defaults, it needs a prior strength above about 1,650
    assessed outcomes, a steepness below about 8.9 and the logistic funding rule; under the
    proportional rule it is a saddle, and at the slowest loss of lessons, 0.1 a year, it is only just
    stable. The reliability of assessment and the time to adjust keep it
    stable over their whole ranges. Where today's split is
    not stable, the model contradicts the history that it starts from, and the analysis must report
    that region.
- **Costs, from the stages.** An attack's work is the sum of five kinds of work: target analysis and
  approval, access, building and testing the effect, running the attack and damage assessment. Each
  has work by hand for the attack and for each target, AI's share now and at the end, and a time. A
  unit of AI work costs an expert's supervision, shared by the attacks that one expert runs at once,
  and compute. The stage values are this scenario's estimates from public anchors; the totals that
  they give are checks, not targets.
  - Anchors: a top-level approval process for one operation (E-SC45-GLOWING-SYMPHONY); an AI model
    that took over a 32-step range of about 20 expert-hours in 3 of 10 tries (E-SC45-AISI-RANGE);
    exploits for known flaws at about $3 each (E-SC45-CVE-GENIE); a core team of five to ten people
    for six months on one payload (E-SC45-STUXNET-TEAM), and another built in as little as two months
    (E-SC45-SANDWORM-2022); a 120-day assessment (E-SC45-GLOWING-SYMPHONY); AI doing 80–90% of an
    espionage campaign's tactical work on about 30 targets (E-SC45-AI-CAMPAIGN).
  - The checks hold today: 10.8 expert-years an attack (the evidence gives 8.1–15.3: the access
    program's staff and the attack posts over about 231 operations of 2011, E-SC45-OPS-2011), 326
    attacks a year (231–437) and 9 months to build an attack (2–11 months). The AI share of access
    and the running of attacks at the end, 0.87, is inside the 0.8–0.9 of the campaign.
  - AI is two paths. Access and the running of attacks follow AI progress fast; payloads, target
    analysis and damage assessment follow it more slowly, because the most complex intrusions and
    attacks on industrial systems stay mostly manual.
  - Compute at frontier prices costs about as much as the work that it replaces (a range of about 20
    expert-hours ran on a budget of 100 million tokens), so AI work is not cheaper than an expert
    today and becomes ten times cheaper at the end by default.
  - **A finding.** Built from its stages, AI cuts the work of each target by about 6 times on the fast
    path, from 10.8 to 1.7 expert-years, but each attack then takes 30 targets, so the work of an
    attack rises to about 50 expert-years. Attacks in a year grow only from 326 to about 390, while
    the targets hit in a year grow about 47 times. Analysis, approval and assessment of each target
    stay mostly human, and they now carry most of the cost. The aggregate model of the first version
    cut the work of an attack to about 6 expert-years whatever its targets.
  - Volt Typhoon held footholds for at least five years (E-VOLT-PREPOSITION), which shows the cost of
    waiting.
- **The delays of an attack.** The force pays for an attack when it starts it, makes it when it is
  ready and its moment comes, and learns from it when its assessment ends. Four stocks hold the attacks
  on their way: access being built, the effect being built and tested, attacks held ready, and attacks
  under assessment.
  - The evidence of the times: first known access came 2 to 11 months before the effect in documented
    operations (research notes, effects chain); footholds were held for at least five years
    (E-VOLT-PREPOSITION); one operation had a first assessment after 30 days, which could not yet
    assess its overall effect, and a second after 120 days (E-SC45-GLOWING-SYMPHONY). The time of
    assessment at the end of AI progress, half of today's, is an assumption.
  - **A finding: a surge costs before it pays.** In the first year of the 2025 surge the force starts
    17% more attacks but makes at most 3% more, so the assessed return of an expert on attacks falls to
    0.86 of the return of surveillance, and the leaders cut the split from 0.087 to 0.083. When the
    surge ends, the stocks still deliver its attacks, and the split rises to 0.090 by 2034.
  - **A finding: AI shrinks the stock held ready.** With access built in days, fewer attacks need to
    be built in advance, so the stock held ready falls from about 760 attacks in 2030 to about 400 in
    2051, under one year of attacks. The one-day plan, which draws on that stock, still passes from 2032.
  - **A finding: a reversal costs more.** When the costs of attacks rise again from 2038, the force
    must fill its stocks again before it gets attacks back: it makes up to 36% fewer attacks than it
    starts, and the split falls to 0.35 by 2051, against 0.38 without the stocks.
- **Surveillance's accesses.** Surveillance builds accesses, its operators use those that they can
  reach, and it loses accesses to the defenders and to exposed attacks on shared access. Its value comes
  from the accesses used, so its gain from AI is a result, not an input.
  - The NSA managed 100 to 150 implants in 2004, tens of thousands six to eight years later, and between
    85,000 and 100,000 by 2014 (E-SC45-IMPLANT-COUNT): the model takes 85,000 accesses today.
  - Human operators limited exploitation at a large scale, and an automated system has controlled
    implants in groups since at least 2010 (E-SC45-TURBINE). In 2011 the implant program made full use
    of only 8,448 of its 68,975 machines, with 1,870 staff (E-SC45-GENIE-2011, unverified: only copies of
    the paywalled article carry these figures, and the model uses them as the research notes quote
    them). So the operators use 12% of the accesses today, a twentieth of the surveillance experts build
    and keep them, and automation does 30% of the work of running them. AI did 80–90% of one espionage campaign
    (E-SC45-AI-CAMPAIGN): 90% at the end of AI progress.
  - Espionage hides long: a median of 122 days among the intrusions that one firm found in 2025, and
    nearly 400 days for one backdoor (E-SC45-ESPIONAGE-DWELL). Accesses that no one finds last longer,
    so the model loses accesses at 50% a year, an assumption.
  - **A finding: AI raises surveillance more than the first version assumed.** At today's split and the
    end of AI progress an expert on surveillance returns about 3.7 times today's, against a doubling.
    AI cheapens the building of accesses about 4.5 times and widens the reach of the operators about
    5 times. On the fast path the split still rises to 0.47 by 2051 (0.50 before), because the funding
    response is near its ceiling, and doctrine still forms in 2034.
  - **A finding: attacks gain shared access as surveillance grows.** The accesses held reach about
    207,000 by 2051, so surveillance covers 98% of the targets of attacks, and 61% of attacks run on its
    access. They burn about 6,600 accesses a year, 3% of those held. When the costs of attacks rise
    again, surveillance shrinks below today's accesses and covers 73% of the targets.
- **Ways to get access.** An attack gets access by an unknown flaw, a known flaw on a target that has
  not fixed it, or access that surveillance holds. The shares follow the ways' costs from today's
  observed shares, so no preference is tuned. A known flaw works only where the target has not fixed it
  when access is built: half of the known-exploited flaws in large outside scans were fixed in just
  under six months (E-SC45-KEV-FIX, partial: a PDF), and one famous flaw was 92% fixed in three weeks
  (E-SC45-PROXYLOGON-FIX). AI builds access in days, so more targets are still open. AI also finds
  unknown flaws: one model found thousands of serious ones (E-SC45-MYTHOS-FLAWS). On the fast path the
  share of attacks on shared access falls from 0.70 to about 0.56, a result where the first version
  assumed 0.2.
- **The defenders adapt in three parts.** No study measures how much one exposed state attack lowers
  the success of later attacks on other targets, so the model splits the brake by what the evidence
  shows.
  - Attention answers the whole threat flow: 884 flaws were first seen exploited in 2025
    (E-SC45-KEV-2025) and 90 zero-days were exploited in the wild (E-SC45-ZERODAY-2025), from many
    actors. The force's attacks are 5% of the threat that the defenders answer, an assumption.
  - Attention saturates: as the flaws to fix in one dataset grew from 69 million to 527 million, the
    share of exploited flaws fully fixed fell from 38% to 26%, and 60–70% stayed open after a week
    whatever the maturity of the organization (E-SC45-DBIR-SATURATION). The model caps attention at
    six times today's, 0.3 log-odds, an assumption.
  - Attention fades within months: two exposed actors returned to their earlier activity about five
    months after their exposure (E-SC45-APT1-RETURN), so it fades at 2 a year.
  - Fixes stop attacks that reuse what was exposed: one actor rebuilt its 2016 tool from the same source
    code (E-SC45-INDUSTROYER2), and at least nine of 18 zero-days of early 2022 were variants of patched
    flaws, one back within 12 months (E-SC45-ZERODAY-VARIANTS). Half of today's attacks reuse something,
    a tenth at the end of AI progress; both shares are assumptions.
  - Lasting gains are options. Organizations found 52% of intrusions themselves in 2025, up from 43%
    (E-SC45-INTERNAL-DETECTION), while dwell rose; AI systems found 86% and patched 68% of the synthetic
    flaws of one competition (E-SC45-AIXCC).
  - **A finding: the defenders' brake on volume is small.** At 1.4 times today's attacks (the end of
    the fast path) attention rises from 0.05 to about 0.051 log-odds, and at 3.4 times (the reversal)
    to about 0.055, where a rule linear in the force's attacks gave 0.07 and 0.17. Doctrine forms a
    year earlier than with the linear rule, and today's split becomes less robust: it is unstable for a
    steepness of the funding response above about 6.9, against 8.9 before.
  - **A finding: the defenders' AI matters more than their attention.** Taking 0.5 log-odds at the end
    of AI progress, it holds success per target to 0.32, against 0.43, and delays doctrine by two
    years, to 2033.
- **The steps that a plan's attacks share.** The plan test first made every attack of a plan depend on
  one shared step, so a failure took a fixed half of the plan whatever AI did. AI made the targets
  inside one attack independent but never the attacks of a plan, which built in the opposite of the
  essay's claim.
  - A failure now takes the attacks that depend on the step. Those are the attacks that reuse an
    exposed flaw, tool or infrastructure: half today and a tenth at the end of AI progress, as AI
    writes new code for each attack (E-SC45-INDUSTROYER2, E-SC45-ZERODAY-VARIANTS; both shares are
    assumptions). Today this gives the same half as before.
  - The factor of the one defender stays shared. Its value, 0.3 log-odds, comes from a drone campaign
    whose drones were one type of weapon (E-SC45-SHAHED-2026, partial), so it may hold a part from the
    attacker's side that AI could also split. No source separates the two parts.
  - **A finding: AI matters more once it splits the shared step.** On the fast path a failure takes
    0.25 of a plan by 2030 and 0.10 by 2045. The plan's chance reaches 0.90 by 2051, against 0.86, and
    doctrine forms in 2031, two years earlier; without AI nothing changes.
  - **A finding: dispersed targets clear the bar without AI.** With unconnected targets the plan's
    chance is 0.905 today, so doctrine forms in 2029 even without AI. Their weaker shared causes alone
    give 0.84; counting every attack toward the plan alone gives 0.78. What the attacks share limits a
    plan more than how many attacks it has.
- **Lessons by stage.** The work of access is the same as surveillance's, so it also learns from
  surveillance's builds. Industry cuts its inputs by about 20% for each doubling of output, and about
  70% of the tasks of two models of one aircraft overlapped (E-SC45-BENKARD-LEARNING, unverified: a PDF
  that this environment cannot extract; the model uses the figures as the research notes quote them).
  The model takes 10% for each doubling of the lessons of access and a 70% overlap. The lessons of access
  fade at 20% a year: a privately held zero-day lived 6.9 years on average before its disclosure, about
  15% a year (E-SC45-ZERODAY-LIFE), and staff leave. The stages that only attacks practice keep the
  faster 30% a year.
  - **A finding: the work of an attack ends up in the stages that only attacks do.** On the fast path
    the lessons of access grow 2.6 times and save about 14% of the work of access, but in 2051 analysis
    and approval (11.5 expert-years) and damage assessment (14.3) are most of the work of an attack
    (43), ahead of access (7.4) and the effect (8.9).
- **The assessment's error is partly common.** In the 1991 air campaign the services and their
  contractors shared one error, 80% claimed against 41–60% audited (E-SC45-DESERT-STORM-BDA), and the
  notes put the reliability of such assessments near 0.3, so the reliability runs from 0.2 to 0.6. One AI
  campaign made up credentials and claimed secret data that was public (E-SC45-AI-CAMPAIGN), so the bias
  can change along the AI path; by default it does not.
  - **A finding: more attacks no longer make assessment precise.** A common error of 0.3 caps the
    signal of a yearly assessment near 3.3: 3.1 today and 3.3 on the fast path, where an error that
    only averaged out gave about 44.
- **War.** In 2022 Russia massed its destructive cyber attacks at the war's outset, hit 22
  organizations in the first week, made about three a week for five weeks and one a week from
  mid-April, spent its first stockpiles, and could sustain the tempo for only weeks
  (E-SC45-WARTIME-TEMPO). The wartime option makes the moment to use an attack held ready come about
  monthly and the planners review every quarter.
  - **A finding: war alone does not make doctrine.** With today's capability, a war from 2026 drains
    the attacks held ready from about 640 to about 125 within months, so the best plan is a month-long
    campaign. The force makes about 1,500 attacks a year by 2051, but the best plan's chance stays near
    0.71 against the 0.8 needed, and every quarterly review misses.
- **Targets that fall together.** In 2015 three utilities that one attack reached lost power together
  (V-C01), so today's correlation of an attack's targets is 0.85. It follows from the share of the
  chance of success that lies in the steps that targets share; AI tailors those steps to each target,
  and the correlation falls to about 0.09 at the end of the fast path.
- **Attribution by channel.** Four kinds of evidence each attribute an attack; it stays unattributed
  only when all miss. Today's chance, 0.73, sits in the 0.6–0.95 of technical attribution. AI removes
  the evidence of the code, as an AI-written wiper in Poland showed, but not of the infrastructure, which
  still matched a known cluster (E-SC45-POLAND-2025): the chance falls to about 0.57, not to the 0.4
  that the first version assumed.
- **A rule for targets per attack is not used.** A rule that chose the targets of an attack as an
  optimum needs a cost of each added target that no source measures. Calibrated to one target per
  attack today, it would hold AI-era attacks near one target, against the evidence of about 30 per AI
  operation (E-SC45-AI-CAMPAIGN, E-SC45-POLAND-2025). So the targets of an attack stay an AI path.
- **Returns.** The essay's precedents show low success against the intended purpose:
  - Ukrainian operators restored power by hand in six hours (V-C01).
  - Iran replaced about 1,000 broken centrifuges and kept enriching (E-SC45-STUXNET).
  - Attacks on more than 30 Polish wind and solar farms did not stop production, and the attack on a
    heat plant missed its intended effect (E-SC45-POLAND-2025).
  - NotPetya did more than $10 billion of damage, most of it collateral (E-SC45-NOTPETYA-DAMAGE).
  - The model's chance of success today, one in five per target, is an assumption that these cases
    inform; no source counts it.
- **Assessment.** The defense secretary who ordered the campaign against ISIS was largely
  disappointed in Cyber Command's effectiveness, and the intelligence community delayed attacks that
  it claimed would hinder collection (E-SC45-CARTER-ISIS). The source supports two parts: noisy
  assessment, and the competition of the two missions.
- **Politics.**
  - NotPetya was attributed to the Russian military (E-SC45-NOTPETYA-ATTRIBUTION) and drew sanctions
    (E-SC45-NOTPETYA-SANCTIONS).
  - The essay cites a wiper that AI may have written in the Polish attacks of 2025. CERT Polska's
    summary still finds a high degree of overlap between the attack's infrastructure and a known
    cluster. That limits the assumption that AI lowers the chance of attribution.
- **The 2025 surge.** The surge is $1 billion over four years for offensive cyber operations
  (E-SC45-SURGE-2025). The source is a news report of the law; the statute text was not checked.
- **The doctrine test.** The planners test plans of one day to one quarter by one rule, so the model
  does not choose what doctrine becomes. A plan fails when it falls short of the planned share of
  targets hit by more than the tolerance; an effect above the plan does not break it.
  - The common factor of a plan's attacks is 0.3 in log-odds. Against one air defense, the monthly hit
    share of Russia's drone campaign ran from 2.61% to 18.67% in 2025–2026, and larger raids gave lower
    rates (E-SC45-SHAHED-2026, partial: the PDF could not be extracted by the recorded extractor). The
    research notes convert the monthly spread to 0.27–0.46 in log-odds.
  - Unconnected victims share no defender: the "Dispersed targets" option takes 0.13, the bound that
    the notes find in quarterly ransomware payment rates. Across campaigns, the success of mass
    extortion through one flaw still fell, from close to 25% of the victims of Accellion to about 2.5%
    of MOVEit's and none of Cleo's in Coveware's cases (E-SC45-COVEWARE-CAMPAIGNS).
  - A step that all of a plan's attacks share fails as a whole, so the model counts it as a mixture.
    An exact count of hits shows why: where the mixture gives 0.879 against an exact 0.879, a normal
    formula with the same variance gives 0.60 (tests/test_doctrine.py).
  - The planners' forecast counts the force's assessed outcomes, not the prior, and keeps a floor of
    10%. After the 1991 air campaign, the claimed hit rate of the F-117 was 80% against 41–60% that
    GAO found (E-SC45-DESERT-STORM-BDA).
  - Doctrine lapses after two missed reviews. Excalibur shells fell from more than 50% to under 10%
    hits under jamming within months, and the United States stopped providing them
    (E-SC45-EXCALIBUR).
  - **A gap to report.** At the defaults the best plan today, a one-day salvo, meets its plan with a
    chance of about 0.75, under the 0.8 needed, so the model finds no doctrine in 2026. Statements of
    2026, not verified in this pass, describe cyber effects as "first movers" before strikes on Iran, which suggests that plans
    already count on opening effects. Those statements give no reliability, so the gap stays open: it
    is a finding about the defaults, not a reason to move them.

### Corrections to the brief that the sources show

- CVE-Genie's 18 minutes is an average of successful runs, not a median.
- The 80-90% is a share of one espionage campaign, not of effects operations.
- CERT Polska attributes the Polish attack's infrastructure to a known cluster. The essay's point
  about missing attribution clues may hold for the malware, which is in the report's PDF and was not
  extracted here.
- The attack-oriented posts (3,535) have no clean primary source in this pass. The Cyber Mission Force
  totals roughly 6,200 people in 133 teams, with 68 defensive teams.

### Not verified in this pass

The model's other values are assumptions with ranges. These sources would inform them; they were
paywalled, refused a plain request, or need a PDF extractor that this environment lacked:

- **Detection rates of the ratio of operations.** The CFR Cyber Operations Tracker counts (719
  espionage and 102 effects operations, 2005–2023) and SSSCIP's 2022 counts. They set the essay's
  21:1 ratio, which the model does not read.
- **Forgetting of organizational knowledge.** Argote, Beckman and Epple (1990), for the rate at which
  lessons fade. Benkard (2000) is cited unverified (E-SC45-BENKARD-LEARNING): its PDF could not be
  extracted, and the model uses its figures as the research notes quote them.
- **Learning curves.** Dutton and Thomas (1984), for the share of work that lessons save.
- **Exploit lifetimes.** The RAND study itself (Ablon and Bogart, 2017) and Smeets (2018). A news
  report of RAND's mean life of 6.9 years is verified (E-SC45-ZERODAY-LIFE).
- **The control of effects.** Maschmeyer (2021), for the trade-off between speed, intensity and
  control.
- **Cyber attacks and battlefield events.** Kostyuk and Zhukov (2019).
- **The money and people of the comparison.** OMB Circular A-94, for the discount rate; CRS IN12616,
  for Cyber Command's resources in FY2026; the ISC report on GCHQ staff.
- **The closest work.** Sulmeyer (RAND, 2026), Lohn (CSET), Withers (CNAS) and Huskaj.

### Data still needed

- A count of effects operations with their expert work, costs and assessed results, for more than one
  country.
- Budgets and staff of attack and surveillance units over time, with the assessed results that came
  before each change.
- The rate at which cyber units lose their lessons, and the reliability of their damage assessments.
- How much one exposed attack lowers the success of later attacks on other targets, and how the
  defenders' attention saturates with the threat flow.
- How fast a force at war uses the attacks that it holds ready, and how much of surveillance's
  experience reaches the access work of attacks.
- The time from the use of an attack to the end of its damage assessment, and how many attacks a force
  holds ready and for how long.
- The accesses that a surveillance program holds and uses today, the work to build one, and the rate at
  which it loses them.
- The share of state effects operations that met their intended effect, by class of target.
- The correlation of outcomes across the targets of one attack and across attacks.
- Records of military plans that depend on timed cyber effects, and the confidence that their
  planners required.
