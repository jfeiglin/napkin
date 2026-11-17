# Austin, Texas: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:austin, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Austin's water system and where each one comes from.

Austin is in the family because its storage records show how the reservoirs refilled after the February 2021
freeze (claim `E-SC43-REFILL`). The place has one system, Austin Water (`austin_water`, TX2270001), with the
Davis, Ullrich and Handcox treatment plants. It sells treated water to other utilities and buys none.

## The sources

Two documents of the City give the values. Both came from the City's document server on 25 October 2026, and the
sections that give the values were read in the retrieved text. All six claims are verified.

- The City's Water Conservation Plan and utility profile of 21 November 2024 (source
  `austin_austinwater2024_conservation_plan`).
- The preliminary official statement for the City's Series 2026 water and wastewater bonds (source
  `austin_austin2026_bond_statement`). It is a preliminary draft in the council backup of 12 March 2026, and its
  tables give Austin Water as their source. The final statement can have different figures.

What the documents give:

- **Peak day** (`E-SC43-AUSTIN-AUSTIN-WATER-PEAK-DAY`, bond statement). The pumpage table gives the total pumpage
  and the maximum day of each fiscal year from 2016 to 2025. A fiscal year ends on 30 September. The highest
  maximum day is 232 Mgal in fiscal 2023, when the total pumpage was 54,850 Mgal. The next highest are 228 Mgal
  (fiscal 2022) and 223 Mgal (fiscal 2024). The table gives the year of each maximum day, not its date.
- **Sales** (`E-SC43-AUSTIN-AUSTIN-WATER-SALES`, bond statement). Sales to other water utilities, which include
  all wholesale customers, were 2,679,954 thousand gallons in fiscal 2023. The statement gives no sales on the
  maximum day.
- **Plants** (`E-SC43-AUSTIN-AUSTIN-WATER-CAPACITY`, plan; `E-SC43-AUSTIN-AUSTIN-WATER-FACILITIES`, bond
  statement). Both documents give the rated capacities of the three plants: Davis 118, Ullrich 167 and Handcox
  50 Mgal a day, 335 Mgal a day in all. These are design capacities, not tested output. The plants also hold
  45 Mgal of clearwell storage on site.
- **Storage** (`E-SC43-AUSTIN-AUSTIN-WATER-STORAGE`, plan). The plan gives 176 Mgal of effective storage in
  38 reservoirs that the City maintains. Its utility profile form gives 15.5 Mgal of elevated and 156.6 Mgal of
  ground storage, 172.1 Mgal in all. Its text gives 14 and 158 Mgal. The plan does not reconcile these
  totals. The bond statement gives over 170 Mgal in 35 major facilities.
- **Supply** (`E-SC43-AUSTIN-AUSTIN-WATER-SUPPLY`, plan). In calendar 2023 Austin Water produced
  54,899,509,000 gallons, bought none and exported 2,731,521,000 gallons. These are 150.41 and 7.48 Mgal a day.
  It bought none in 2021 and 2022, 0.867 Mgal in 2019 and 1.18 Mgal in 2020.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report
  (`A-SC43-PEAK-DAY`). For Austin that is the bond statement's table of fiscal 2016 to 2025: 232 Mgal in fiscal
  2023. The average day of that year is 54,850 / 365 = 150.274 Mgal, a ratio of 232 / 150.274 = 1.54385. Austin
  uses its own ratio, not the family median.
- **Older days.** An older official statement of the City gives higher maximum days: 247 Mgal in fiscal 2005,
  241 Mgal in fiscal 2006 and 240 Mgal in fiscal 2009. It is a scanned exhibit in Texas PUC Docket Nos. 42857
  and 42867. These days came before the permanent year-round water use limits of 2012, which include a limit of
  once a week on automatic irrigation. The population was also much smaller then. These days lie outside the
  record of the latest report, so the family rule does not take them. No value uses the exhibit, and no claim
  records it.
- **Sales.** The fiscal 2023 sales are 2,679.954 Mgal / 365 days = 7.34234 Mgal a day. At the peak ratio they
  are 11.3354 Mgal a day (`sold`). The calendar 2023 exports of the plan, 7.4836 Mgal a day, agree within 2%.
- **Daily use.** (232 − 11.3354) / 1.05 = 210.157 Mgal a day (`demand`); the model adds the pipe losses of 5% on
  top.
- **Plant capacity.** 335 Mgal a day (`nameplate`), the rated capacity of the three plants.
- **Storage.** 176 Mgal (`storage`), the effective storage of the plan. It leaves out the 45 Mgal of clearwells
  at the plants; with them the storage is about 221 Mgal. The model keeps the family's usable share of 0.8878
  (claim `E-SC43-USABLE-STORAGE`).
- **Purchases.** None (`bought` = 0): Austin Water bought no treated water in 2021, 2022 or 2023.

From the family's evidence: SDWIS lists 1,115,323 people served (claim `E-SC43-SDWIS-TX2270001`). The plan gives
1,096,486 retail and 53,770 wholesale people in 2023, counts of a different kind. The value added comes from
Travis County, Texas, the county that SDWIS lists. Eleven hospitals lie in the system's service area (claim
`E-SC43-HOSPITALS-AUSTIN-WATER`). One of them is in Hays County and one in Williamson County, which the value
added does not include.

## What the model does not show

The storage of the model leaves out the 45 Mgal of clearwells at the three plants, so Austin's stored water runs
out sooner here than in fact. Austin sold water to 16 wholesale customers in 2023, and three more customers have
an emergency supply only. All of them are outside the place, so the model gives their water as one sale and does
not count their people. It does not show their contract limits. While Austin has stored water, the model keeps
the sales in full. It does not show an early cut of their supply.
