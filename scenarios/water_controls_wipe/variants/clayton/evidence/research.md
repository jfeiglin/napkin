# Clayton County, Georgia: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:clayton, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Clayton County's water system and where each one comes from.

Clayton County is in the family because a disruption of part of its operational systems on 27 July 2026 led to a
boil-water advisory (claim `E-SC43-CLAYTON-2026`). The pressure fell in parts of north Clayton County, and the
Authority issued the advisory as a precaution. Service came back within hours. The place has one system, the
Clayton County Water Authority (CCWA) (`clayton_county`, GA0630000), with three surface water plants. It sells
water to College Park, a system outside the place, and buys none on a normal day.

## The sources

Four documents give the values. All were retrieved on 25 October 2026.

- The Authority's Annual Comprehensive Financial Report for the fiscal year that ended on 30 April 2025 (source
  `clayton_ccwa2025_acfr`).
- Its adopted budget for 2026 to 2027 (source `clayton_ccwa2026_budget_fy2027`).
- An SDWIS query of the systems that buy from it (source `clayton_epa2026_sdwis_ccwa_buyers`).
- A College Park council document of 6 November 2023 (source `clayton_collegepark2023_council_agenda`).

The first three opened directly and were read in full; their four claims are verified. The College Park site
refused the retrieval (HTTP 403), a third-party retrieval could not reach it and the Internet Archive was not
reachable. So its claim, `E-SC43-CLAYTON-CLAYTON-COUNTY-COLLEGE-PARK`, is unverified: its figure comes from a
search engine summary of the document.

- **Plants and production** (`E-SC43-CLAYTON-CLAYTON-COUNTY-PLANTS`, budget). The W.J. Hooper plant can give up
  to 20 Mgal a day, J.W. Smith up to 12 and Terry R. Hicks 10, 42 Mgal a day in all. The water comes from the
  Authority's reservoirs, with raw water from the Flint River. The average production is 28.15 Mgal a day, and
  it includes the water sold to College Park.
- **System** (`E-SC43-CLAYTON-CLAYTON-COUNTY-SYSTEM`, 2025 report). The report gives 42 Mgal a day of capacity
  and 28 Mgal a day produced. Three clear wells hold 6.7 Mgal, seven ground tanks 23 Mgal and four elevated tanks
  2.5 Mgal. Six connections with Atlanta can open on demand, with about 5 Mgal a day of supply.
- **Connections** (`E-SC43-CLAYTON-CLAYTON-COUNTY-INTERCONNECTIONS`, budget). The six connections with Atlanta
  open on demand under a contract and can bring about 8 Mgal a day. The connections with the DeKalb and Fayette
  systems can give up to 2 Mgal a day. The budget reports no water bought in normal operation.
- **Buyers** (`E-SC43-CLAYTON-CLAYTON-COUNTY-BUYERS`, SDWIS). SDWIS lists a permanent connection to College Park
  and emergency connections to Fayette County, the Henry County Water Authority, Griffin and Spalding County.
- **College Park** (`E-SC43-CLAYTON-CLAYTON-COUNTY-COLLEGE-PARK`, unverified). The search summary says that the
  Authority supplies College Park with 0.7 Mgal a day, and East Point with 2.8. It is not clear whether the
  0.7 Mgal a day is a capacity, a contract amount or a normal flow.

Schedule 9 of the 2025 report is an image without a text layer, so no claim quotes it. Read from the page, it
gives 10,029 Mgal produced in fiscal 2025, no water imported through the connections in that year and a daily
capacity of 15 Mgal for the connections. No value uses these figures.

## The values

- **Peak use.** No source reports a highest day, so the family median ratio applies (`A-SC43-PEAK-DAY`):
  1.54385, the median of the 19 systems that report both a highest and an average day. 28.15 × 1.54385 =
  43.4593 Mgal a day. This is more than the 42 Mgal a day that the plants can produce, and the Authority buys no
  water on a normal day. Under the rule, an estimated peak is at most what the system can produce and buy on that
  day. So the peak is 42 Mgal a day.
- **Sales.** College Park, 0.7 Mgal a day (`sold`). The scenario takes the figure as the peak-day sale, without
  the peak ratio, because it may be a capacity. Its claim is unverified.
- **Daily use.** (42 − 0.7) / 1.05 = 39.3333 Mgal a day (`demand`); the model adds the pipe losses of 5% on top.
- **Plant capacity.** 20 + 12 + 10 = 42 Mgal a day (`nameplate`).
- **Storage.** 6.7 + 23 + 2.5 = 32.2 Mgal (`storage`). The model keeps the family's usable share of 0.8878
  (claim `E-SC43-USABLE-STORAGE`).
- **Purchases.** None (`bought` = 0): the connections with Atlanta, DeKalb and Fayette are for supply on demand.

From the family's evidence: SDWIS lists 298,374 people served through 87,365 service connections (claim
`E-SC43-SDWIS-GA0630000`). The value added comes from Clayton County, Georgia. One hospital lies in the system's
service area: Southern Regional Medical Center (claim `E-SC43-HOSPITALS-CLAYTON-COUNTY`).

## What the model does not show

The Authority can open its connections with Atlanta, DeKalb and Fayette on demand, for about 8 and 2 Mgal a day.
The model's purchases are the same at every hour, so it cannot open them when the Authority needs water. So the
interruption can be longer here than in fact.

The peak of 42 Mgal a day is the plants' capacity, because the median estimate is above it. Water systems are
sized for their highest day, so the true peak is probably lower. Then the stored water can run out sooner here
than in fact.
