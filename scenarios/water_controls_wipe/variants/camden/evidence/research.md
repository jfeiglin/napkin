# Camden, New Jersey: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:camden, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water system and where each one comes from.

Camden is in the family because it is the seat of American Water, whose business systems an attacker disrupted
in October 2024 with no effect on water service (claim `E-SC43-AMWATER-2024`). The place has one system, the
company's largest in New Jersey: New Jersey American Water's Raritan system (`raritan`, NJ2004002). It has two
surface water plants, Raritan-Millstone in Bridgewater and Canal Road in Somerset, and 69 active wells. It buys
raw water from the New Jersey Water Supply Authority, which it treats itself, so it buys no treated water. It
sells treated water to nine bulk customers and passes water to the company's Passaic Basin system; none of them
is in the scenario.

## The sources

Seven documents give the values. Six claims are verified and one is partial.

- **Capacity** (`E-SC43-CAMDEN-RARITAN-CAPACITY`, the NJDEP water supply record of the system, updated
  30 January 2024). The firm capacity is 245.155 Mgal a day: all plants and wells with the largest unit out of
  service. The record also gives a "current peak" of 160.922 Mgal a day for July 2020; its glossary says that
  this is the average day of the highest month, not a highest day.
- **Average day** (`E-SC43-CAMDEN-RARITAN-AVERAGE`, the company's 2024 infrastructure filing to the Board of
  Public Utilities, 19 April 2024). Table 5.1 gives an average day of 124.427 Mgal and a peak month of
  141.108 Mgal a day for 2023, and 563,000 people served. The filing lists the nine bulk customers and the
  transfers to the Passaic Basin system, and gives the plants' total capacities (156.6 and 80.0 Mgal a day).
- **Highest day** (`E-SC43-CAMDEN-RARITAN-MAXDAY`, a MercerMe article of 31 July 2025 on a tour of the Canal
  Road plant). The company's senior production manager says that the system is "peaking at about 180 million
  combined systemwide". The claim is verified as a record of what the article says; the figure is a rounded,
  spoken one.
- **Sales to Middlesex Water** (`E-SC43-CAMDEN-RARITAN-MSEX-CONTRACT`, a Board order of 12 February 2025).
  Middlesex buys treated water from the company with a minimum take of 1,095.0 Mgal a year, 3.0 Mgal a day.
  Middlesex's 2024 annual report gives the same purchase (`E-SC43-CAMDEN-RARITAN-MSEX-PURCHASES`); that claim
  is partial, because the SEC site refused the fetch and the text came through a third-party retrieval.
- **Transfer to the Passaic Basin system** (`E-SC43-CAMDEN-RARITAN-PASSAIC-TRANSFER`, rate-case testimony of
  January 2022). The Diamond Hill booster station moves 4 to 10 Mgal a day on average from the Raritan system
  to the Passaic system.
- **Storage** (`E-SC43-CAMDEN-RARITAN-STORAGE`, rate-case testimony of January 2024). The Oak Tree site in
  Edison has tanks of 10, 10, 5 and 1 Mgal, 26 Mgal in all.

## The values

- **Peak use.** The highest day that a source reports is about 180 Mgal (`A-SC43-PEAK-DAY`), production of the
  whole system, so it includes the sales. The ratio to the 2023 average day is 180 / 124.427 = 1.4466.
- **Sales.** The known average sales are 3.0 Mgal a day to Middlesex and 4 Mgal a day to the Passaic Basin
  system (the low end of the range): 7.0 Mgal a day. At the peak ratio they are 7.0 × 1.4466 = 10.126 Mgal a
  day (`sold`).
- **Daily use.** (180 − 10.126) / 1.05 = 161.784 Mgal a day (`demand`).
- **Plant capacity.** 245.155 Mgal a day, the firm capacity (`nameplate`). It is a floor on the rated
  capacity: the two plants alone total 236.6 Mgal a day, and the wells add the rest.
- **Storage.** 26 Mgal, the Oak Tree site only (`storage`). No source gives the system's total.
- **Purchases.** None (`bought` = 0).

From the family's evidence: SDWIS lists 615,430 people served (claim `E-SC43-SDWIS-NJ2004002`); the company's
filing gives 563,000. The value added comes from Union County, New Jersey, the one county that SDWIS lists for
the system, although the system's three hospitals are in Hunterdon, Middlesex and Somerset counties. Three
hospitals lie in the system's service area (claim `E-SC43-HOSPITALS-RARITAN`): Hunterdon Medical Center, Robert
Wood Johnson University Hospital Somerset and the University Medical Center of Princeton at Plainsboro.

## What the model does not show

The 26 Mgal of storage is one site. It holds about 3.7 hours of the peak day's use, and the system's real total
is probably several times larger, so the stored water runs out much sooner here than in fact. The other bulk
customers, among them Liberty Water for Elizabeth and Edison Water, have no published volumes, so the sales are
a floor and the daily use a ceiling; their sum on the peak day, 180 Mgal, does not depend on the split. The
Middlesex agreement ended on 27 February 2026, and no source read here says whether it was renewed. The 2023
average day may leave out some sales (the two plants averaged 135.4 Mgal a day in 2021 to 2023); if it does,
the peak ratio is lower.
