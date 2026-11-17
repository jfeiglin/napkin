# Jamestown, North Carolina: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:jamestown, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

Jamestown is in the family because it is a small town that buys all its water. Its 2024 plan gives its stored
water against its purchases (claim `E-SC43-JAMESTOWN-RATIO`). The place has three systems. The Town of Jamestown
(`jamestown`, NC0241030) has no plant of its own. Two cities sell water to it: Greensboro (`greensboro`,
NC0241010) and High Point (`high_point`, NC0241020).

## The sources

Each system's values come from its 2025 Local Water Supply Plan on the site of the NC DEQ Division of Water
Resources (sources `jamestown_ncdeq2025_jamestown_lwsp`, `jamestown_ncdeq2025_greensboro_lwsp` and
`jamestown_ncdeq2025_highpoint_lwsp`). The three pages were retrieved on 25 October 2026 and read in full. The
plans are the systems' own reports, and the pages say that the Division's staff does not field verify the data.
All 13 claims are verified.

The Town of Jamestown:

- **Use** (`E-SC43-JAMESTOWN-TOWN-USE`). The total demand of 2025 is 0.5313 Mgal a day, with no sales. The
  monthly table gives monthly means only, from 0.4490 Mgal a day in March to 0.6290 Mgal a day in September. Its
  column for the highest day of each month is empty.
- **Storage** (`E-SC43-JAMESTOWN-TOWN-STORAGE`). The finished water storage is 0.4672 Mgal. The 2024 plan, which
  the family claim cites, gave 0.3170 Mgal.
- **Purchases** (`E-SC43-JAMESTOWN-TOWN-PURCHASES`). The town has no source and no treatment plant. It buys from
  High Point (0.4330 Mgal a day, contract 1.5 Mgal a day), Greensboro (0.0983 Mgal a day, contract
  0.125 Mgal a day) and the Piedmont Triad Regional Water Authority (PTRWA; none, contract 0.15 Mgal a day). The
  purchases sum to its total demand. Most of its water is PTRWA water that High Point (0.500 Mgal a day) and
  Greensboro (0.125 Mgal a day) pass through their mains. The PTRWA contract of 0.15 Mgal a day is the rest of
  the town's PTRWA allocation of 0.775 Mgal a day. No water came through it in 2025.

Greensboro:

- **Peak day** (`E-SC43-JAMESTOWN-GREENSBORO-MAXDAY`). The highest day of 2025 is 44.9818 Mgal, in January. The
  total demand is 34.4067 Mgal a day, with 0.1069 Mgal a day of sales. The plan gives no cause for the January
  peak.
- **Plants** (`E-SC43-JAMESTOWN-GREENSBORO-PLANTS`). The Lake Townsend WTP has a permitted capacity of
  30 Mgal a day and the Mitchell Water Treatment Plant 24 Mgal a day.
- **Storage** (`E-SC43-JAMESTOWN-GREENSBORO-STORAGE`). 31.8 Mgal of finished water storage.
- **Purchases** (`E-SC43-JAMESTOWN-GREENSBORO-PURCHASES`). The city buys from PTRWA (6.7714 Mgal a day, contract
  7.955), Burlington (1.9446, contract 5.0) and Reidsville (0.9920, contract 1.0 Mgal a day), 9.708 Mgal a day in
  all. The PTRWA water includes the 0.125 Mgal a day that Greensboro passes to Jamestown.
- **Sales** (`E-SC43-JAMESTOWN-GREENSBORO-SALES`). Jamestown bought 0.1055 Mgal a day under its contract of
  0.125 Mgal a day. Burlington bought 0.0044 Mgal a day on the 119 days that it used the connection, which is
  0.0014 Mgal a day over the year.

High Point:

- **Peak day** (`E-SC43-JAMESTOWN-HIGHPOINT-MAXDAY`). The highest day of 2025 is 17.87 Mgal, in October. The
  total demand is 14.9786 Mgal a day, with 0.365 Mgal a day of sales. The plan says that its process water
  includes water that goes to Jamestown. So some of that water can be in its service area demand as well as in
  its sales.
- **Plant** (`E-SC43-JAMESTOWN-HIGHPOINT-PLANT`). The Frank L. Ward Water Filtration plant, the city's only
  plant, has a permitted capacity of 24 Mgal a day.
- **Storage** (`E-SC43-JAMESTOWN-HIGHPOINT-STORAGE`). 19.0 Mgal of finished water storage.
- **Purchases** (`E-SC43-JAMESTOWN-HIGHPOINT-PURCHASES`). The city buys from PTRWA (2.7510 Mgal a day, contract
  2.78), Davidson Water (0.0354) and Archdale (0.0012 Mgal a day), 2.7876 Mgal a day in all. The PTRWA water
  includes the water that High Point passes to Jamestown.
- **Sales** (`E-SC43-JAMESTOWN-HIGHPOINT-SALES`). Jamestown bought 0.3550 Mgal a day under a contract of
  1.5 Mgal a day. The contract is 0.5 Mgal a day of PTRWA water and a separate High Point contract of
  1.0 Mgal a day. Archdale bought 0.0100 Mgal a day under a contract of 0.5 Mgal a day.

The town and the two cities report different volumes on both connections. Jamestown reports 0.4330 Mgal a day
from High Point, which reports 0.3550. Jamestown reports 0.0983 Mgal a day from Greensboro, which reports 0.1055.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report (`A-SC43-PEAK-DAY`).
  The three systems report one year at a time, so the record is their 2025 plan. Greensboro's ratio is 44.9818 /
  34.4067 = 1.3074, and High Point's is 17.87 / 14.9786 = 1.1930. Jamestown reports no highest day, so the family
  median ratio applies: 1.54385, the median of the 19 systems that report both a highest and an average day.
  0.5313 × 1.54385 = 0.8202 Mgal a day. This is below the 1.625 Mgal a day of the town's two contracts, so the
  rule's cap at what the system can buy does not apply.
- **Daily use** (`demand`). Jamestown sells no water: 0.8202 / 1.05 = 0.7812 Mgal a day. Greensboro:
  (44.9818 − 0.1069 × 1.3074) / 1.05 = 42.7067 Mgal a day. High Point: (17.87 − 0.365 × 1.1930) / 1.05 =
  16.6043 Mgal a day. The model adds the pipe losses of 5% on top.
- **Plant capacity** (`nameplate`). Jamestown 0, Greensboro 30 + 24 = 54 and High Point 24 Mgal a day.
- **Storage** (`storage`). Jamestown 0.4672, Greensboro 31.8 and High Point 19.0 Mgal, from the 2025 plans.
- **Purchases from outside the place** (`bought`). Jamestown none: its PTRWA water comes through the two cities,
  so the model gives it in the two connections. Greensboro 9.708 × 1.3074 = 12.6918 Mgal a day and High Point
  2.7876 × 1.1930 = 3.3257 Mgal a day, at each city's peak ratio.
- **Sales outside the place** (`sold`). Greensboro's own sales table shows only the Burlington sale outside the
  place: 0.0014 × 1.3074 = 0.0019 Mgal a day. High Point's shows only the Archdale sale: 0.0100 × 1.1930 =
  0.0119 Mgal a day.
- **Connections** (`capacity`). The connection from High Point carries 1.5 Mgal a day and the one from Greensboro
  0.125 Mgal a day, the contracts that both plans print. They are contract amounts, not pipe capacities. The
  model divides the water that the town asks for in proportion to them (`A-SC43-TIES`). The town asks High Point
  for 1.5 / 1.625 = 0.923 of it and Greensboro for 0.125 / 1.625 = 0.077. In 2025 the town took
  0.4330 / 0.5313 = 0.815 of its water from High Point.

From the family's evidence: SDWIS lists 6,543 people served by Jamestown (claim `E-SC43-SDWIS-NC0241030`),
319,588 by Greensboro (claim `E-SC43-SDWIS-NC0241010`) and 118,662 by High Point (claim
`E-SC43-SDWIS-NC0241020`). The value added comes from Guilford County, North Carolina. One hospital lies in
Greensboro's service area, the Moses H. Cone Memorial Hospital (claim `E-SC43-HOSPITALS-GREENSBORO`). One lies in
High Point's, High Point Regional Health System (claim `E-SC43-HOSPITALS-HIGH-POINT`). The family's join gives
the town no hospital.

## What the model does not show

The model counts the PTRWA water that reaches Jamestown as the purchase and the sale of the two cities. So a wipe
of a city's controls cuts that water. The plans do not say whether the water needs the cities' pumps or
controls. If it does not, the town keeps more water than the model gives it, and its interruption is longer here
than in fact.

At the peak ratio, some purchases of the cities go above their contracts. Greensboro buys 8.853 Mgal a day from
PTRWA against a contract of 7.955, and 1.297 Mgal a day from Reidsville against 1.0. High Point buys
3.282 Mgal a day from PTRWA against 2.78. With the contracts as caps, Greensboro would buy 11.497 Mgal a day and
High Point 2.824 Mgal a day. The values follow the family rule. So the model gives the cities more water from
outside the place than their contracts allow, and their stored water can last longer here than in fact.
