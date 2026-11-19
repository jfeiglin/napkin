# Asheville, North Carolina: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:asheville, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Asheville's water system and where each one comes from.

Asheville is in the family because of its hospital water and the end of its boil-water notice after Hurricane
Helene in 2024. The city lifted the notice on 18 November 2024, on samples of 16 and 17 November (claim
`E-SC43-CLEARANCE-INTERVAL`). Mission Hospital was without city water for 54 days and trucked in 300,000 gallons
a day (claim `E-SC43-TRUCKED-SUPPLY`), and one hospital company lists 28 tankers of 6,000 gallons for its North
Carolina hospitals (claim `E-SC43-HCA-FLEET`). The place has one system, the City of Asheville water system
(`asheville`, NC0111010). It sells water to three systems outside the place and buys none.

## The sources

The values come from the system's Local Water Supply Plans for 2025 and 2022, on the site of the NC DEQ Division
of Water Resources (sources `asheville_ncdeq2025_lwsp` and `asheville_ncdeq2022_lwsp`). Both pages were
retrieved on 25 October 2026 and read in the retrieved text. The plans are the system's own report, and the
pages say that the Division's staff does not field verify the data. All five claims are verified.

- **Use** (`E-SC43-ASHEVILLE-CITY-USE`, 2025 plan). The plan gives the average day and the highest day of each
  month. The highest day of 2025 is 26.48 Mgal, in January, when the average day was 24.05 Mgal. The total demand
  of 2025 is 22.6544 Mgal a day: 21.4912 Mgal a day in the service area and 1.1632 Mgal a day of sales. The
  monthly figures are withdrawals, so they include the sales, the process water and the losses.
- **Sales and purchases** (`E-SC43-ASHEVILLE-CITY-SALES`, 2025 plan). Asheville sold 0.7057 Mgal a day to Black
  Mountain, 0.3136 to Woodfin and 0.1439 to Biltmore Forest, 1.1632 Mgal a day in all. The contracts total
  2.15 Mgal a day. The connections with Hendersonville and Weaverville are for emergencies only. Asheville bought
  no water: its four purchase connections, with Hendersonville, Black Mountain, Weaverville and Woodfin, are for
  emergencies and carried no water in 2025.
- **Plants** (`E-SC43-ASHEVILLE-CITY-CAPACITY`, 2025 plan). The permitted capacities are 31.5 Mgal a day at North
  Fork, 7.5 at Mills River and 5.0 at William DeBruhl. The system expects peak day demand to exceed the plant
  capacity within 10 years. Phase 2 of the Mills River expansion is due by the end of 2027.
- **Storage** (`E-SC43-ASHEVILLE-CITY-STORAGE`, 2025 plan). The finished water storage is 27.3560 Mgal, in a
  system of 55 pressure zones. The 15 Mgal of off-stream raw water storage is separate. The figure does not
  include the 1 Mgal clearwell of the Mills River expansion.
- **The freeze of 2022** (`E-SC43-ASHEVILLE-CITY-FREEZE-2022`, 2022 plan). From 22 to 27 December 2022, frozen
  coagulant lines took the Mills River plant offline for 3 days. In that time 27 main breaks and many private
  line breaks drained the storage tanks. The southern district and parts of the western district had no water
  for 5 to 8 days. The highest day of December was 29.01 Mgal.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report
  (`A-SC43-PEAK-DAY`). It leaves out a day that the source attributes to main breaks. Asheville reports one year
  at a time, so the record is the 2025 plan: 26.48 Mgal in January. The ratio to the 2025 total demand is
  26.48 / 22.6544 = 1.1689. The 29.01 Mgal of December 2022 is not a day of use: the 2022 plan attributes it to
  the main breaks of the freeze. Older plans show higher days, so the peak here can be low.
- **Sales.** 1.1632 × 1.1689 = 1.3596 Mgal a day (`sold`). None of the buyers is in the place.
- **Daily use.** (26.48 − 1.3596) / 1.05 = 23.9242 Mgal a day (`demand`); the model adds the pipe losses of 5% on
  top.
- **Plant capacity.** 31.5 + 7.5 + 5.0 = 44 Mgal a day (`nameplate`), the permitted capacities.
- **Storage.** 27.356 Mgal (`storage`), the finished water storage. The model keeps the family's usable share of
  0.8878 (claim `E-SC43-USABLE-STORAGE`).
- **Purchases.** None (`bought` = 0).

From the family's evidence: SDWIS lists 157,431 people served through 61,981 service connections (claim
`E-SC43-SDWIS-NC0111010`). The value added comes from Buncombe County, North Carolina. Two hospitals lie in the
system's service area (claim `E-SC43-HOSPITALS-ASHEVILLE`): the Asheville-Oteen VA Medical Center and Memorial
Mission Hospital.

## What the model does not show

Asheville has four emergency connections through which it can buy water, among them a 24-inch connection with
Hendersonville. The model gives the system no water from outside the place during the event, so its interruption
can be longer here than in fact. The peak comes from one year's plan, and older plans show higher days. So the
stored water can last longer here than on a higher peak day.
