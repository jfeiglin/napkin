# Auburn, Washington: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:auburn, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Auburn's water system and where each one comes from.

Auburn is in the family because its water plan shows how much of a city's stored water is usable (claim
`E-SC43-USABLE-STORAGE`). The place has one system, the City of Auburn water utility (`auburn`, WA5303350).

## The source

Every value of the system comes from the City's 2024 Water System Plan of May 2025 (source
`auburn_auburn2025_water_plan`), retrieved from the City's site on 25 October 2026 and read in full. Its bytes
are the same as those of the family source that the usable-storage claim cites. All five claims are verified.

- **Peak day** (`E-SC43-AUBURN-AUBURN-PEAK-DAY`). Table 2-9 gives the average day and the maximum day for 2015
  to 2022, from the City's production and purchase records. The highest maximum day is 12.56 Mgal on
  25 August 2016. From 2017 to 2022 the highest is 12.43 Mgal on 29 July 2020, with an average day of 6.32 Mgal.
  The executive summary gives a range of 11.25 to 12.43 Mgal a day, which leaves out the 2016 figure; the plan
  does not explain this.
- **Sales** (`E-SC43-AUBURN-AUBURN-SALES`). Algona has a firm supply. It used 132.07 Mgal in 2020 and
  averaged 0.36 Mgal a day from 2018 to 2022. Lake Meridian Water District bought about 303 Mgal a year in 2015
  and 2016, stopped in 2017, and now buys only on an interruptible basis.
- **Source capacity** (`E-SC43-AUBURN-AUBURN-SOURCE-CAPACITY`). Table 3-19 gives 15,610 gal/min in all: the
  wells give 7,955 gal/min, Coal Creek Springs 3,500 gal/min, West Hill Springs 600 gal/min and the Tacoma
  interties 3,555 gal/min.
- **Storage** (`E-SC43-AUBURN-AUBURN-STORAGE`). The storage analysis (Table 3-29) gives 15.86 Mgal in eight
  reservoirs, of which 14.08 Mgal is usable. The text rounds the total to 15.7 Mgal, and Table 3-7 sums to
  15.8 Mgal.
- **Purchases** (`E-SC43-AUBURN-AUBURN-PURCHASES`). A 2014 agreement with Tacoma gives 3.5 Mgal a day of
  average use and 5.12 Mgal a day of peak use. The City bought 732 Mgal in 2015, 321 Mgal in 2016 and none
  since.

## The values

- **Peak use.** The family takes each system's highest day on record (`A-SC43-PEAK-DAY`). The highest day in
  Table 2-9 is that of 2016, but it included the regular sales to Lake Meridian, which ended in 2017. Less the
  2016 sales at the 2016 ratio, the retail peak of 2016 is 10.64 Mgal, below the 11.72 Mgal of 2020. So the
  scenario takes 2020 as the highest day of the present system and of its retail customers: 12.43 Mgal, a ratio
  of 12.43 / 6.32 = 1.96677 to the average day. The literal reading, 2016, gives a daily use of 10.1368 Mgal and
  sales of 0.5607 Mgal a day.
- **Sales.** The Algona sale of 2020 is 132.07 Mgal / 366 days = 0.360847 Mgal a day. At the peak ratio it is
  0.709704 Mgal a day (`sold`).
- **Daily use.** (12.43 − 0.709704) / 1.05 = 11.1622 Mgal a day (`demand`); the model adds the pipe losses of
  5% on top.
- **Plant capacity.** The City's own wells and springs, 7,955 + 3,500 + 600 = 12,055 gal/min (`nameplate`).
  The system has no central treatment plant. The Tacoma interties are left out: they carry water bought from
  another system.
- **Storage.** 15.86 Mgal (`storage`). The family's usable share, 0.8878, is 14.08 / 15.86 from the same table,
  so the model uses the plan's own usable storage.
- **Purchases.** None (`bought` = 0): the City has bought no water since 2016.

From the family's evidence: SDWIS lists 107,655 people served (claim `E-SC43-SDWIS-WA5303350`); the plan gives
about 63,450 customers through 15,046 connections at the end of 2022, a count of a different kind. The value
added comes from King County, Washington. One hospital lies in the system's service area: MultiCare Auburn
Medical Center (claim `E-SC43-HOSPITALS-AUBURN`).

## What the model does not show

Auburn can call on Tacoma through two interties (5.12 Mgal a day under the contract) and on emergency interties
with seven systems, and the plan counts the Tacoma interties in its own supply analysis. The model gives the
system no standby supply from outside the place: with no purchases on a normal day, Auburn gets none of this
water during the event, so its interruption can be longer here than in fact. Algona's agreement lets the City
cut Algona's supply in proportion to a failure of its own supply; the model keeps the sale in its share of the
water that is left.
