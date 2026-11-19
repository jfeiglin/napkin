# Water-service disruption calculations: the SC43 family

Research date: 25 October 2026. Package: SC43, with one variant for each of sixteen places.

SC43 follows one operation against the controls of the water systems of one real place, from the first move
to the water that reaches people's taps, the work that puts the controls back and the value added that the
place loses. The module `water.scn` holds the mechanism. Each place's variant holds its own systems, the
sales between them, their people and their hospitals, and each place's research note gives the sources of
its values. This note gives the evidence that every place shares.

## What the model does not hold

The model holds no hydraulics. A system delivers its customers' normal use in full while its usable stored
water lasts, and passes on what it produces or receives once the store is empty. A real system loses pressure
zone by zone, and a utility may cut service early to protect a reserve, so an interruption can start earlier
than this model says. The pressure-demand relationship that hydraulic models use (claim `E-SC43-PDD-FORM`) and
the restoration simulators built on it (claim `E-SC43-REWET-PRECEDENT`) show what a finer model would need: a
network, its pumps and a hydraulic solver, which no catalogue scenario holds.

The model converts no loss of water service into deaths or serious harm. The reviewed evidence gives the
effects of an outage on a hospital's functions: one hospital postponed surgeries within an hour of a pressure
drop and resumed normal operations an hour and a half later (claim `E-SC43-MEDSTAR-90MIN`); another trucked in
300,000 gallons a day for 54 days (claim `E-SC43-TRUCKED-SUPPLY`); a federal analysis found services degraded by
half or more within eight hours at facilities that depend on water (claim `E-SC43-NIAC-DEGRADATION`). None of
these gives a rate of death or serious harm for a population without water, so deaths and serious casualties
are reported as not estimated, with the hospitals' hours short of water as the measure that the evidence
supports. The outputs are not zero.

The model holds no trade between areas. The value-added loss is the direct loss of the areas that the systems
serve, and the loss in other areas is reported as not estimated.

## The places

The family has one scenario for each place where a part of its evidence comes from (`A-SC43-PLACES`): a 2026
incident (Cape May County, Clayton County, Minot), a recovery (Asheville, Richmond, Jackson, El Dorado County),
a measurement of stored water (Auburn, Austin, Jamestown), the cost of a regional outage (Washington, DC), the
help between utilities (Lehigh County and Erie), the duration of business closures (Lumberton) and the context
of the premise (Juneau, Camden, Los Angeles). Each scenario follows the community water systems that the
evidence names and the systems inside the place that sell water to them (`A-SC43-REACH`). The places are not a
sample of the country. The national inventory counts 49,193 community water systems serving 315.7 million
people; 91% of the systems serve 10,000 people or fewer and together serve 16.8% of the people, while 2% serve
more than 50,000 people and together serve 59% (claim `E-SC43-CWS-INVENTORY`).

The people the study follows are the people that the systems of the place serve, each counted once under the
system that delivers their water. Each system's people served is the count that it reports to the federal
inventory through its state (claims `E-SC43-SDWIS-<PWSID>`). A wholesale system that serves no retail customer
has no homes in the model.

## Each system's values

Each system has its own daily use, plant capacity, stored water, purchases and sales, from its own reports.
The reports differ in year, in what they cover and in how they count; each place's research note says which
figure each value takes and why.

- **The peak day.** The attack comes on each system's peak day of use (`A-SC43-PEAK-DAY`): the highest day of
  production, deliveries or use in the record that the system's latest report gives, a table of several years
  where the report has one and the report's own year where the system reports one year at a time. A day that
  the source attributes to main breaks or to a counting error, or that included sales that have since ended, is
  not a day of use and is left out. The peak ratio is that day over the average day of the same year where a
  source gives it, and over the latest average day otherwise. Water use varies through the year (claim
  `E-SC43-WITHDRAWALS`), and stored water lasts least on the peak day.
- **The median ratio.** Where no source reports a highest day, the peak is the average day times the median peak
  ratio of the family's systems that report both: 1.54385, the median of 19 ratios from 1.17 (Asheville) to 2.95
  (Cape May). A month's mean is not a highest day, so a system that reports only its highest month is not in the
  set; its month's mean is a floor for its estimate. An estimated peak is at most what the system can produce
  and buy on that day: Clayton County's estimate passes its plants' capacity, so its peak is that capacity.
  Six systems use the median: Woodbine, Clayton County, Jamestown, JXN Water, LADWP and the sales of NAWS.
- **Daily use.** The water that the system's own retail customers use on the peak day: the peak use, less the
  system's sales at the same ratio when the peak figure includes them, divided by 1.05, because the model adds
  pipe losses of 5% of use on top.
- **Plant capacity.** The rated capacity of the system's own plants, wells and springs. A system that buys all
  its water has none.
- **Stored water.** The finished-water storage that the system reports. The model applies a usable share of
  0.8878: a city water plan deducts dead storage and a wholesale customer's reserve from its 15.86 million
  gallons and keeps 14.08 million as usable (claim `E-SC43-USABLE-STORAGE`). The 2006 national survey gives,
  for systems serving more than 100,000 people, a mean finished storage of about 17 hours of mean daily
  production where they draw on groundwater and about 18 hours where they draw on surface water (claim
  `E-SC43-STORAGE-HOURS`).
- **Purchases and sales outside the place.** Water bought from and sold to systems that are not in the place's
  scenario, at the system's peak ratio. The scenario does not follow those other systems.

## Sales between the systems of a place

A system of the place that sells water to another system of the place is linked to it by a connection with a
capacity (`A-SC43-TIES`). The national inventory links each buyer to the system that sells to it (claim
`E-SC43-BULK-LINKING`); the capacity of each connection comes from the contract or the connection that a place's
source reports, or, where none is reported, from the highest flow on record, which is a floor.

The seller serves its own customers first and shares what is left among its buyers in proportion to what each
asks. A buyer asks for what its customers, its losses and its own sales need beyond what it produces and buys
from outside, plus the water that refills its storage over a stated time, up to the connection's capacity. A
buyer with two sellers asks each in proportion to the capacity of its connection, and asks the other for the
part that a short seller cannot fill. After the February 2021 freeze, Austin's storage climbed from 32 to 118
million gallons over about 72 hours against a stated healthy minimum of 100 million (claim `E-SC43-REFILL`): a
refill takes time, which is why the scenario refills over a stated time and not at once.

The balance of each system is

```
d(stored)/dt = production + purchases from outside + water from sellers
               - delivery - water to buyers - sales outside - losses
delivery     = normal use while stored > 0, else min(normal use, what is produced and received)
service      = delivery / normal use
```

Every gallon is produced, bought, stored, delivered, lost or sent on, and the model counts each once: water
that leaves the store makes room for water that refills it.

## Manual operation

Operators can run a plant by hand at a share of normal production, after a delay. The two New Jersey systems of
Cape May County switched to manual controls one hour and 45 minutes after their alarms (claims
`E-SC43-CAPEMAY-MANUAL`, `E-SC43-WOODBINE-MANUAL`), and a Utah system ran by hand for about three weeks (claim
`E-SC43-UTAH-RECOVERY`). The share of production that operators can hold is an assumption (`A-SC43-MANUAL`) by
the kind of system: the root cause analysis of the Richmond failure found a plant that operates mostly by hand,
staffed near the minimum, with manual tasks left unfinished (claim `E-SC43-MANUAL-TASKS-UNFINISHED`), and the
plant's organization chart lists 15 plant operator positions with two of the operations positions vacant
(claim `E-SC43-OPERATOR-COVERAGE`). Running by hand takes qualified hours from the recovery, so each system's
operator duty comes off the controls crews' pace while the system is on manual controls.

## The first move and its reach

The premise transfers the reach of reported incidents. In July 2026 Minnesota reported malicious cyber activity
against the technology used to monitor and control equipment remotely at more than thirty community water
systems (claim `E-SC43-MN-2026`), and the same week two New Jersey systems lost communications with their remote
monitoring (claims `E-SC43-CAPEMAY-MANUAL`, `E-SC43-WOODBINE-MANUAL`). An earlier campaign reached at least 34
US water-sector controllers through internet-connected devices with default passwords (claim
`E-PLC-INTERNET-REACH`), and a national alert describes trusted third-party suppliers used as pivot points into
the intended targets (claim `E-TA18-ACCESS`). The shared remote-support platform, the wipe of the controls and
the credential that the first cleanup misses are what this scenario assumes (`A-SC43-OPERATION`); the
catalogued behaviour behind them is the abuse of valid accounts and remote services (claims `ATTACK-T1078`,
`ATTACK-T1133`, `ATTACK-T0886`, `ATTACK-T0859`). The scenario also gives a run where the first move reaches
fewer systems, for example the Washington Aqueduct only, whose buyers then lose their water through their
connections.

The depth of the first move is two shares: the share of production that the wiped controls stop and the share
of delivery that stops before anyone runs the pumps by hand (`A-SC43-DEPTH`). The Clayton County incident shows
the shape: a disruption of part of the operational systems, reduced pressure in some areas, a precautionary
boil-water advisory, and service restored within the day (claim `E-SC43-CLAYTON-2026`). The American Water
incident shows the other case, an IT incident with no effect on water service (claim `E-SC43-AMWATER-2024`),
which this scenario does not model.

## Work, crews and parts

Each system's recovery is three loads of work: the controls work that rebuilds and verifies the controllers,
the field work that reconfigures equipment, and the replacement work that installs new controllers and needs
parts. The loads are assumptions by the kind of system (`A-SC43-WORK`): a district's monthly field report gives
99 labour hours for four main and lateral repairs (claim `E-SC43-FIELD-HOURS`), which sets the scale of a field
task and nothing about controls. A controls crew pool and a field crew pool serve the systems of the place;
each pool shares its hours equally among the systems with work waiting, so a system with a small load finishes
first (`A-SC43-CREW-CAPACITY`).

The pools arrive in stages: recognition, request, release, travel and orientation. One generator was offered
within 13 minutes of a request and ran on site within a day (claim `E-SC43-OFFER-TIME`), but after Hurricane
Hermine it took two days before visiting crews knew a system well enough to operate it on their own (claim
`E-SC43-MUTUAL-AID-SCALE`), mutual aid runs through state networks with a common agreement (claim
`E-SC43-WARN-MECHANISM`), and a state's volunteer cyber response team of about 140 call-out members sends one or
two people to a small incident and up to a dozen to a large one (claim `E-SC43-CRT-ROSTER`). Most utilities
have two or fewer full-time staff for operational-technology security (claim `E-SC43-WSCC-STAFFING`). The
capacities of the pools and their stage times are assumptions by response tier (`A-SC43-RESPONSE`).

Replacement controllers come from the spares in stock and then from a batch after a lead time
(`A-SC43-PARTS`). A district reported a lead time of about 32 weeks for replacement pumps (claim
`E-SC43-PUMP-LEAD-TIME`), large utilities report lead times from weeks to years for electrical parts (claim
`E-SC43-COMPONENT-LEAD-TIMES`), and a federal intervention cut a year's wait for a pump controller (claim
`E-SC43-EXPEDITED-DELIVERY`). After a ransomware breach of a city network, a regional project's SCADA was back
in three days while the shared connection stayed cut for more than two months (claim `E-SC43-NAWS-SCADA`):
restoring controls and trusting a shared channel again are different clocks, which is why the removal of the
credential has its own time.

## Clearance and the advisory

A system issues a boil-water advisory when its stored water runs out and the pressure falls, and lifts it after
sampling once its controls and its sellers' controls are back. Asheville's notice was lifted on 18 November 2024
on samples taken on 16 and 17 November (claim `E-SC43-CLEARANCE-INTERVAL`); Calgary took three days to fill a
repaired feeder main and five days from the start of filling to the end of restrictions (claims
`E-SC43-CALGARY-STAGES`, `E-SC43-CALGARY-RELEASE`). Richmond's staff believed early on 6 January 2025 that their
reserve would last until about the early afternoon, and the city lost pressure before that (claim
`E-SC43-RESERVOIR-BOUND`): a reserve is a bound on the time a system has, not a promise. The clearance time by
response tier is an assumption (`A-SC43-CLEARANCE`). An advisory is permitted use, not delivery: people under an
advisory may still have water at the tap, and the model reports them separately. For a hospital the end of the
advisory starts its own recommissioning (claim `E-SC43-RECOMMISSIONING`), which the model does not follow.

## Emergency water and hospitals

Emergency drinking water moves at the smallest of the approved supply, the tankers, the receiving points and the
staff who hand it out (`A-SC43-RELIEF`), at the planning minimum of one gallon a person a day (claim
`E-SC43-RELIEF-MINIMUM`). Hospitals get it first. The hospitals' critical need and reserves rest on an audited
medical complex that kept 1.68 million gallons in reserve against a summer use of 0.433 million gallons a day
(claim `E-SC43-HOSPITAL-RESERVE`), on the 28 tankers of 6,000 gallons that one hospital system lists for its
hospitals (claim `E-SC43-HCA-FLEET`), and on the state template that asks hospitals to plan their water over
successive periods (claim `E-SC43-HCAI-FIELDS`); the ordinary water use of hospitals is about 107,000 gallons a
bed a year (claim `E-SC43-HOSPITAL-USE`). The model reports facility-hours with critical care short of water and
puts no clinical harm on them (`A-SC43-HOSPITAL`).

The hospitals of each system come from the CMS Hospital General Information list (claims `E-SC43-CMS-<SYSTEM>`):
the acute care hospitals, with those of Veterans Affairs and Defense, the critical access hospitals and the
children's hospitals of the place (`A-SC43-HOSPITAL-JOIN`). The Census geocoder places each hospital's CMS
address (claims `E-SC43-GEOCODE-<CCN>`), and a point query of the EPA service areas gives the system whose area
contains it (claims `E-SC43-JOIN-<CCN>`, counted by system in claims `E-SC43-HOSPITALS-<SYSTEM>`). The EPA
boundaries are modelled for many systems and can be wrong at their edges (claim `E-SC43-SERVICE-AREAS`). The
geocoder does not match the CMS address of six hospitals, which are not counted: Inova Mount Vernon (Fairfax
Water), Walter Reed (WSSC Water), the Richmond and the Jackson Veterans Affairs medical centers, St. Dominic in
Jackson and the VA Greater Los Angeles. The counts of those systems are floors. Three addresses lie in two
service areas; each hospital goes to the system of the place, or to the smaller area when both systems are in
the place (United Medical Center to DC Water).

## Costs

The value added that an area's businesses lose follows the survey of Swedish companies' own estimates: for each
sector a share `r` of value added maintained over the outage and its recovery, and a ratio `tau` of the
interruption plus recovery to the interruption (claim `E-SC43-VA-R-TAU`). The loss rate is

```
loss rate = value added an hour * share that needs public water * (1 - r) * tau * (1 - service)
```

Part of the loss is made up later. The value added an hour of the area that a system serves is its people served
times the value added for each resident of the counties it serves (`A-SC43-ECONOMY`): the 2024 GDP of those
counties in current dollars (claims `E-SC43-BEA-GDP-<FIPS>`, `E-SC43-BEA-GDP-BASIS`) over their 2024 midyear
population (claims `E-SC43-BEA-POP-<FIPS>`, `E-SC43-BEA-POP-BASIS`), taken to 2025 prices by the GDP price index
(125.587 in 2024 and 128.893 in 2025, claims `E-SC43-GDP-DEFLATOR`, `E-SC43-GDP-DEFLATOR-SERIES`), over 8,760
hours. The counties of each system are those that the federal inventory lists (claim `E-SC43-SDWIS-COUNTIES`).
A system's customers then produce the average value added of its counties; where a system serves parts of
counties that the inventory does not list, the value added uses only the listed ones. The share that needs
public water and the share made up are assumptions; `r` and `tau` are stated estimates for Swedish sectors over
hypothetical outages, transferred to US areas.

Two benchmarks bound the account. A study of the National Capital Region puts the loss of gross regional product
from losing the Potomac supply at about $14.9 billion in the first month (claim `E-SC43-NCR-BENCHMARK`). FEMA's
standard value for a loss of potable water service is $150 a person a day (claims `E-SC43-FEMA-150`,
`E-SC43-FEMA-150-NY`); it is a planning value for benefit-cost analysis and not a measured loss, and the
scenario does not use it as an input. A flood study found that the days of each utility outage enter
business-interruption models with their duration (claim `E-SC43-LUMBERTON`), which is why the loss here is
integrated over time rather than counted per event.

## The attacker's loop

With a hidden credential, the attacker sees each system's controls come back and wipes them again after its
reaction time, which adds the share of the controls work it is prepared for. The AI acts within a quarter of an
hour and reaches every make; the human team acts after about two days and reaches one fifth of the work
(`A-SC43-PREPARED-MAKES`, `A-AI-TEMPO`). The two-day pace is the calendar interval between two disruptive events
of one reported intrusion (claim `E-MANDIANT22`), and the AI's pace rests on reports of agents that rebuild
their tooling on detection (claims `AI-ORCHESTRATION-2026`, `AI-AGENT-TRUST-2026`). In the 2015 Ukraine case
operators disabled an attacker's account about 40 minutes after the first breaker openings (claim
`E-CYOTE15-TIMING`), which is the lower end of the time to remove access; the removal time by response tier is
an assumption (`A-SC43-RESPONSE`). Ties go to the defenders: a credential removed as a strike comes due stops
the strike.

## Source benchmark

The two New Jersey incidents and the Clayton County disruption of July 2026 are the closest observed events: a
loss of remote monitoring or control, manual operation within the hour, and normal operation within one to three
days. This scenario's delayed response is slower than all of them on every clock, by construction: it asks what
happens when the switch to manual operation holds less than normal production, when the crews are shared by the
systems of a place, and when the attacker comes back. The Richmond failure of January 2025, a plant failure
rather than an attack, shows a metropolitan system that lost pressure within a day and took days to clear its
advisory. The Washington Aqueduct's place shows a seller whose loss reaches three buyers at once.

## Verification status

The family folder holds 347 claims. 321 are verified against cached copies of their documents. 26 are partial.
Seven of them because the publisher's server refused the repository's fetch and the document was retrieved
through a third-party fetch service, whose copy the rules never mark verified (`E-SC43-AMWATER-2024`,
`E-SC43-HOSPITAL-RESERVE`, `E-SC43-JUNEAU-POP`, `E-SC43-FEMA-150`, `E-SC43-GAO-2026`, `E-SC43-FEMA-150-NY`,
`E-SC43-RECOMMISSIONING`). Nineteen are the CMS hospital lists of the systems (`E-SC43-CMS-<SYSTEM>`): the CMS
data site refused the fetch, and the rows came through the same service. Their quotes match the retrieved text.
The Richmond engineering report's text layer holds its appendices and not its body, so its two claims record
what the appendices say. Each place's research note gives the status of its own claims.

## Not estimated

Deaths and serious casualties are not estimated, for the reason given above. The loss in other areas is not
estimated. The people without service for more than a week without a break are not estimated: the model
follows the water each system delivers, not each person's own days without it. Each output reports its reason
and is not zero.
