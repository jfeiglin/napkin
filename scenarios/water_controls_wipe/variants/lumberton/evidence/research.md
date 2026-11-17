# Lumberton, North Carolina: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:lumberton, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Lumberton's water system and where each one comes from.

Lumberton is in the family because of a study of how long its businesses closed after the flood of Hurricane
Matthew in October 2016 (claim `E-SC43-LUMBERTON`). Of 163 businesses that gave a closure time, the mean was
17.5 days. The place has one system, the City of Lumberton water system (`lumberton`, NC0378010), with one plant
on the Lumber River and four wells that feed it. It sells and buys no water.

## The sources

The values come from the system's Local Water Supply Plans for 2025 and 2018, on the site of the NC DEQ Division
of Water Resources (sources `lumberton_ncdeq2025_lwsp` and `lumberton_ncdeq2018_lwsp`). Both pages were
retrieved on 25 October 2026 and read in the retrieved text. The plans are the system's own report, and the
pages say that the Division's staff does not field verify the data. All five claims are verified.

- **Use** (`E-SC43-LUMBERTON-CITY-USE`, 2025 plan). The highest day of 2025 is 5.7 Mgal, reached in January, June
  and December. The total demand of 2025 is 4.5767 Mgal a day, all of it in the service area, with no sales. Of
  this, metered use is 2.146 Mgal a day, system processes (backwash, line cleaning and flushing) take 2.2000 and
  unaccounted-for water is 0.2307. The monthly figures are raw water flows.
- **Plant** (`E-SC43-LUMBERTON-CITY-CAPACITY`, 2025 plan). The City of Lumberton Water Plant on the Lumber River
  has a permitted capacity of 16.0 Mgal a day. In 2025 it drew 3.75 Mgal a day on average from the river. Four
  wells were in regular use, and the plan counts a ground water supply of 2.1456 Mgal a day.
- **Raw water of 2018** (`E-SC43-LUMBERTON-CITY-RAW-2018`, 2018 plan). The monthly values are blended flows from
  the river and the wells, which one meter at the plant measures together. The software counted the well water
  twice: the 2018 total is 4.3917 Mgal a day, not 4.9020. The highest day of the plan is 8.5 Mgal, in January
  2018. The note shows that the wells feed the plant, so they are not a separate treatment capacity.
- **Storage** (`E-SC43-LUMBERTON-CITY-STORAGE`, 2025 plan). The finished water storage is 7.5 Mgal. The 16 Mgal
  of off-stream raw water storage is separate. Earlier plans give other totals, such as 9.0 Mgal in 2018, and do
  not say why.
- **Connection** (`E-SC43-LUMBERTON-CITY-INTERCONNECT`, 2025 plan). The only connection is with Robeson County,
  through an 8-inch pipe. It is for emergencies, with a contract of 0.5 Mgal a day to 2029, and it carried no
  water in either direction in 2025.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report
  (`A-SC43-PEAK-DAY`). It leaves out a day that the source attributes to a counting error. Lumberton reports one
  year at a time, so the record is the 2025 plan: 5.7 Mgal. The ratio to the 2025 total demand is 5.7 / 4.5767 =
  1.2454. The 8.5 Mgal of January 2018 is not a day of use: the 2018 plan says that its raw water figures counted
  the well water twice. Older plans show higher days, so the peak here can be low.
- **Daily use.** Lumberton sells no water: 5.7 / 1.05 = 5.4286 Mgal a day (`demand`); the model adds the pipe
  losses of 5% on top. About 2.2 of the 4.58 Mgal a day go to system processes, so this use includes process
  water as well as the customers' use.
- **Plant capacity.** 16 Mgal a day (`nameplate`), the permitted capacity of the one plant.
- **Storage.** 7.5 Mgal (`storage`). The model keeps the family's usable share of 0.8878 (claim
  `E-SC43-USABLE-STORAGE`).
- **Purchases and sales.** None (`bought` = 0, `sold` = 0). The emergency connection with Robeson County is not in
  the model.

From the family's evidence: SDWIS lists 24,460 people served through 9,784 service connections (claim
`E-SC43-SDWIS-NC0378010`). The 2025 plan gives a population of 19,000, below the SDWIS figure. The value added
comes from Robeson County, North Carolina. One hospital lies in the system's service area: Southeastern Regional
Medical Center (claim `E-SC43-HOSPITALS-LUMBERTON`).

## What the model does not show

Almost half of the daily use is process water for backwash, line cleaning and flushing. The model draws the
stored water at the full daily use. With the plant stopped, part of that process water is not drawn, so the
stored water can run out sooner here than in fact. The emergency connection with Robeson County can supply up to
0.5 Mgal a day, and the model gives the system none of it. So its interruption can be longer here than in fact.
