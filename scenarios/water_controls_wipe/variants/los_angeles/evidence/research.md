# Los Angeles, California: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:los_angeles, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water system and where each one comes from.

Los Angeles is in the family because a study of how its water system recovers after damage shows what a finer,
hydraulic model would need (claim `E-SC43-REWET-PRECEDENT`). The place has one system, the Los Angeles
Department of Water and Power (`ladwp`, CA1910067). It takes water from the two Los Angeles aqueducts, which its
Los Angeles Aqueduct Filtration Plant in Sylmar treats, from wells, and from the Metropolitan Water District. The
Metropolitan Water District is outside the scenario, so its water is a purchase from outside. LADWP sells no water
to other systems.

## The sources

Five documents give the values. All seven claims are verified.

- **The bond statement of 4 August 2025** (Water System Revenue Bonds, 2025 Series A and B):
  - Demand (`E-SC43-LOSANGELES-LADWP-DEMAND`): the supply and demand table for fiscal 2020 to 2024 (years to
    30 June), in acre-feet. Total demand includes recycled water, which the table also lists.
  - Purchases (`E-SC43-LOSANGELES-LADWP-MWD`): deliveries from the Metropolitan Water District averaged about
    239,173 acre-feet a year in fiscal 2020 to 2024, from 140,497 (fiscal 2024, a wet year) to 366,690 (fiscal
    2022, a dry year).
  - Storage (`E-SC43-LOSANGELES-LADWP-STORAGE`): the storage table, with the aqueduct reservoirs (310,542
    acre-feet of untreated water) apart from the in-city reservoirs and tanks (13,056 acre-feet).
- **The service letter of 11 October 2023** (`E-SC43-LOSANGELES-LADWP-CAPACITY`): the filtration plant's maximum
  treatment capacity is 600 Mgal a day; its average flow in 2023 to that date was 333 Mgal a day.
- **The 2024-25 Briefing Book** (`E-SC43-LOSANGELES-LADWP-FY2024`): more than 399 Mgal a day on average in fiscal
  2024, and 323,545 acre-feet of storage in the city and along the aqueduct.
- **The Metropolitan Water District's budget for fiscal 2025 and 2026** (`E-SC43-LOSANGELES-LADWP-MWD-PEAK`):
  LADWP's peak day on the district's system from May to September was 579.4, 633.1 and 452.2 ft³/s in 2021 to
  2023, about 292 to 409 Mgal a day.
- **The 2025 urban water management plan, February 2026 draft** (`E-SC43-LOSANGELES-LADWP-UNTREATED`): LADWP buys
  untreated State Water Project water from the district and treats it at the filtration plant. The plan gives no
  highest day and no split between treated and untreated purchases.

## The values

- **Average day.** The mean total demand of fiscal 2020 to 2024 is 477,381.2 acre-feet a year, less mean
  recycled water of 10,515.2: 466,866.0 acre-feet a year, or 416.792 Mgal a day.
- **Peak use.** No source reports a highest day of the system's total use, so the family median ratio applies
  (`A-SC43-PEAK-DAY`): 416.792 × 1.54385 = 643.463 Mgal a day.
- **Daily use.** LADWP sells no water, so 643.463 / 1.05 = 612.822 Mgal a day (`demand`).
- **Purchases.** 239,173 acre-feet a year is 213.520 Mgal a day; at the median ratio, 329.642 Mgal a day
  (`bought`). The district's recorded summer peak days for LADWP, about 292 to 409 Mgal a day, bracket it.
- **Plant capacity.** 600 Mgal a day, the filtration plant only (`nameplate`). Wells are left out.
- **Storage.** 13,056 acre-feet = 4,254.3 Mgal, the in-city reservoirs and tanks (`storage`). The table prints
  4,240 Mgal for the total, but its own column adds to 4,255 Mgal, and the acre-feet total is used. Los Angeles
  Reservoir holds 78% of it; without it the in-city storage is 940 Mgal.

The daily use with its losses, 643.5 Mgal a day, is above the plant's 600, and the plant with the purchases,
929.6 Mgal a day, covers it.

From the family's evidence: SDWIS lists 3,875,566 people served (claim `E-SC43-SDWIS-CA1910067`). The value added
comes from Los Angeles County, California. Twenty-eight hospitals lie in the system's service area (claim
`E-SC43-HOSPITALS-LADWP`). The count is a floor: the Census geocoder does not match the CMS address of the VA
Greater Los Angeles Healthcare System, so the join does not place it. Cedars-Sinai Medical Center lies in the
service areas of both LADWP and Beverly Hills, which is not in the scenario, and goes to LADWP.

## What the model does not show

Part of the purchased water is untreated and goes through the filtration plant, so it would stop when the plant's
controls are wiped; the model counts all purchases as treated water from outside, so LADWP keeps more water here
than in fact. The model has no limit on raw water: the plant's 600 Mgal a day is more than the two aqueducts can
carry (about 437 Mgal a day) and much more than they delivered on average in fiscal 2020 to 2024 (about
172 Mgal a day, and 62 in fiscal 2022), so production by hand can be overstated in dry years. Groundwater is
left out of the plant capacity; the wells gave only 6,521 acre-feet in fiscal 2024.
