# Cape May County, New Jersey: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:cape_may, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

Cape May County is in the family because two of its systems lost their remote monitoring in July 2026, and
staff ran them by hand. Cape May changed to manual controls one hour after its alarm and went back to normal
operation 34.5 hours later (claim `E-SC43-CAPEMAY-MANUAL`). Woodbine's operator ran its system by hand for
58 hours (claim `E-SC43-WOODBINE-MANUAL`). The place has two systems with no connection between them: the City
of Cape May Water & Sewer Utility (`cape_may`, NJ0502001) and the Borough of Woodbine (`woodbine`, NJ0516001).

## The sources

Seven documents give the values. All were retrieved on 25 October 2026 and read in full, and all nine claims are
verified.

- For Cape May: the City's Master Plan Reexamination, adopted on 12 March 2019 (source
  `capemay_capemay2019_master_plan_reexamination`), the project narrative of its water treatment plant, 25 April
  2025 (source `capemay_capemay2025_wtp_narrative`), an SDWIS query of the systems that buy from it (source
  `capemay_epa2026_sdwis_capemay_buyers`) and its NJDEP water supply page of 27 September 2024 (source
  `capemay_njdep2024_capemay_deficit_surplus`).
- For Woodbine: its NJDEP water supply page of 17 April 2024 (source
  `capemay_njdep2024_woodbine_deficit_surplus`), the Borough's Master Plan of October 2019 (source
  `capemay_woodbine2019_master_plan`) and its drinking water quality report for 2025 (source
  `capemay_woodbine2026_ccr`).

New Jersey's Drinking Water Watch refused the retrieval (HTTP 403), so no source gives the capacity of each of
Woodbine's wells.

## The values

The City of Cape May:

- **Peak use.** The 2025 narrative gives a maximum day demand of approximately 2.80 Mgal and an annual average of
  approximately 0.95 Mgal a day (`E-SC43-CAPEMAY-CAPE-MAY-DEMAND`), a ratio of 2.9474 (`A-SC43-PEAK-DAY`). The
  maximum day has no year; the narrative says that demand was steady from 2018 to 2023. The 2019 reexamination
  also gives 2.8 Mgal on a peak summer day (`E-SC43-CAPEMAY-CAPE-MAY-STORAGE`). The summer population is about
  ten times the permanent one, so the ratio is high.
- **Sales.** SDWIS lists three systems that buy from Cape May: Cape May Point, West Cape May and Lower Township
  MUA (`E-SC43-CAPEMAY-CAPE-MAY-BUYERS`). In 2023 they took 30.78, 48.854 and 1.913 Mgal, 81.547 Mgal in all or
  0.2234 Mgal a day. At the peak ratio: 0.2234 × 2.9474 = 0.6585 Mgal a day (`sold`).
- **The Coast Guard.** The narrative lists the U.S. Coast Guard training center as a bulk customer, with
  25.119 Mgal in 2023. SDWIS shows no Coast Guard water system, so its use stays in the city's daily use.
- **Daily use.** (2.80 − 0.6585) / 1.05 = 2.0395 Mgal a day (`demand`); the model adds the pipe losses of 5% on
  top.
- **Plant capacity.** Two reverse osmosis trains of 0.98 Mgal a day and Well 5 at 1.00 Mgal a day, 2.96 Mgal a
  day in all (`nameplate`; `E-SC43-CAPEMAY-CAPE-MAY-CAPACITY`). With the largest unit out of service, the plant
  gives 1.96 Mgal a day (2.000 for NJDEP, `E-SC43-CAPEMAY-CAPE-MAY-NJDEP`), below the maximum day. The City plans
  a new plant of 3.24 Mgal a day, which was not built in the period.
- **Storage.** A 1 Mgal standpipe and a 0.75 Mgal elevated tank, 1.75 Mgal (`storage`). The same document also
  calls the elevated tank 700,000 gallons, which gives 1.70 Mgal. No source gives a clearwell volume.
- **Purchases.** None (`bought` = 0). NJDEP records no contract for purchased water. The only link is an
  emergency interconnect with Lower Township MUA, and no source gives its capacity.
- **NJDEP's demand figures.** NJDEP gives a peak of 2.847 Mgal a day (July 2020) and 588.680 Mgal for 2021. These
  are far above the deliveries of the narrative and seem to count raw water before the reverse osmosis losses,
  so no value uses them. NJDEP's peak is the mean of the highest month, not one day.

The Borough of Woodbine:

- **Peak use.** No source reports a highest day. NJDEP gives 116.475 Mgal for 2020, or 0.3182 Mgal a day, and
  0.457 Mgal a day as the mean of the highest month, July 2020 (`E-SC43-CAPEMAY-WOODBINE-DEMAND`). That mean is
  not a highest day, so Woodbine is not one of the systems behind the family median. The median ratio applies:
  1.54385, the median of the 19 systems that report both a highest and an average day. 0.3182 × 1.54385 =
  0.4913 Mgal a day, above the 0.457 of the highest month and below the firm capacity of 1.08.
- **Daily use.** Woodbine sells no water: 0.4913 / 1.05 = 0.4679 Mgal a day (`demand`).
- **Plant capacity.** 1.08 Mgal a day (`nameplate`), the NJDEP firm capacity of the two wells
  (`E-SC43-CAPEMAY-WOODBINE-CAPACITY`). This is the capacity with the largest unit out of service, so the full
  capacity is larger; no source gives it.
- **Storage.** The Borough's one water tower, 0.5 Mgal (`storage`; `E-SC43-CAPEMAY-WOODBINE-STORAGE`).
- **Purchases and sales.** None (`bought` = 0, `sold` = 0). The two wells are the only source
  (`E-SC43-CAPEMAY-WOODBINE-SOURCES`), and no source names a buyer. NJDEP's committed peak of 0.405 Mgal a day is
  for approved projects that are not built.

From the family's evidence: SDWIS lists 35,000 people served by Cape May (claim `E-SC43-SDWIS-NJ0502001`) and
2,650 by Woodbine (claim `E-SC43-SDWIS-NJ0516001`). The value added comes from Cape May County, New Jersey. The
family's list of hospitals assigns none to these two systems, so the place has no hospital in the model.

## What the model does not show

Cape May has an emergency interconnect with Lower Township MUA, of unknown capacity. The model gives the city no
water from outside the place during the event, so its interruption can be longer here than in fact. Woodbine's
plant capacity is its firm capacity, with its largest unit out of service. So the model's production by hand and its
refill can be slower here than in fact.
