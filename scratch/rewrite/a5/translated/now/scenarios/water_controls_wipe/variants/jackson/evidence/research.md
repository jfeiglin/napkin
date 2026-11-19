# Jackson, Mississippi: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:jackson, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Jackson's water system and where each one comes from.

Jackson is in the family because federal help sped up the delivery of a replacement controller for the pumps of
its water plant (claim `E-SC43-EXPEDITED-DELIVERY`). The place has one system, the City of Jackson water system
(`jxn_water`, MS0250008). JXN Water runs it under the interim stipulated order of the federal court of
29 November 2022. Its plants are O.B. Curtis, with a conventional side and a membrane side, and J.H. Fewell. No
source names a wholesale sale or purchase.

## The sources

Three documents give the values. All three opened directly on 25 October 2026, and all four claims are verified.

- The survey of the system by the Mississippi State Department of Health of November 2021, with its design
  capacity sheet, reviewed on 13 December 2021 (source `jackson_msdh2021_inspection`).
- The report of the Interim Third-Party Manager for the quarter that ended on 30 June 2026, dated 31 July 2026
  (source `jackson_jxnwater2026_q2_report`).
- His report for the quarter that ended on 30 June 2025, dated 31 July 2025, in the copy on epa.gov (source
  `jackson_jxnwater2025_q2_report`).

What the documents give:

- **Production** (`E-SC43-JACKSON-JXN-PRODUCTION`, 2026 report). The report gives the mean daily production of
  the two plants into the distribution system for each quarter. From July 2025 to June 2026 the means are 40.4,
  35.9, 37.0 and 35.1 Mgal a day. The quarterly means of 2023 were 47 to 56 Mgal a day. The report estimates the
  water loss at about 50% (17 Mgal a day), against more than 65% in October 2023. The same table gives the output
  of each plant: the conventional side of O.B. Curtis gave 5.9 Mgal a day in the first quarter of 2026 and
  1.8 Mgal a day in the second.
- **Metered use** (`E-SC43-JACKSON-JXN-METERED`, 2025 report). The metered demand on the system is about
  18 Mgal a day, against a mean of 34.9 Mgal a day at the plants in June 2025. The difference is mostly water
  lost from the pipes.
- **Plants** (`E-SC43-JACKSON-JXN-PLANTS`, 2021 survey). The department rates each side of O.B. Curtis at
  25 Mgal a day. It sets a maximum of 20 Mgal a day at J.H. Fewell, from turbidity data. In 2021 it credited only
  16.8 Mgal a day to each side of O.B. Curtis, for the filters and membrane trains in service, so 53.6 Mgal a day
  in all with J.H. Fewell. J.H. Fewell averaged 22.3 Mgal a day in the third quarter of 2025, above its limit of
  2021.
- **Storage** (`E-SC43-JACKSON-JXN-STORAGE`, 2021 survey). The survey counts 13.8 Mgal at J.H. Fewell (a
  3.8 Mgal clearwell and two ground tanks of 5 Mgal), a 10 Mgal clearwell at O.B. Curtis and 7.75 Mgal in nine
  elevated tanks. It leaves out three elevated tanks, 2.2 Mgal in all, that were offline or empty. Their present
  condition is not known. The survey also says that the plants could not pump enough water to keep all elevated
  tanks full.

## The values

- **Average day.** The four quarterly means of July 2025 to June 2026, each weighted by its days, give
  37.106 Mgal a day. These twelve months include a summer quarter.
- **Peak use.** No source reports a highest day, so the family median ratio applies (`A-SC43-PEAK-DAY`):
  1.54385, the median of the 19 systems that report both a highest and an average day. 37.106 × 1.54385 =
  57.2860 Mgal a day. This is below the 70 Mgal a day that the plants can produce, so the rule's cap does not
  apply. Monthly operating reports of 2018 to 2021 give daily production estimates
  for each plant. They come from before the failure of 2022 and the leak repairs, when production was much
  higher, so no value uses them.
- **Daily use.** The system sells no water: 57.2860 / 1.05 = 54.5581 Mgal a day (`demand`). The family rule works on
  plant output, so this daily use includes the water lost from the pipes, about half of production. The model
  then adds its own pipe losses of 5%.
- **Plant capacity.** 25 + 25 + 20 = 70 Mgal a day (`nameplate`), the rated capacities of 2021.
- **Storage.** 13.8 + 10 + 7.75 = 31.55 Mgal (`storage`). With the 2.2 Mgal of tanks that the survey leaves out,
  it would be 33.75 Mgal.
- **Purchases and sales.** None (`bought` = 0, `sold` = 0): no source names a wholesale sale or purchase of
  treated water.

From the family's evidence: SDWIS lists 189,673 people served through 71,846 service connections (claim
`E-SC43-SDWIS-MS0250008`). The value added comes from Hinds County, Mississippi. Four hospitals lie in the
system's service area (claim `E-SC43-HOSPITALS-JXN-WATER`): Merit Health Central, Mississippi Baptist Medical
Center, Mississippi Methodist Rehab Center and the University of Mississippi Medical Center. The count is a floor.
The Census geocoder does not match the CMS addresses of the G. V. (Sonny) Montgomery VA Medical Center and of
St Dominic-Jackson Memorial Hospital, so the join does not place them.

## What the model does not show

The rated capacities are from 2021, before the plant failures of August 2022, and no newer rated capacity was
found. In 2026 the conventional side of O.B. Curtis gave little water, so the plants can probably produce less
than the 70 Mgal a day of the model. So JXN Water can produce more water by hand and refill faster here than in
fact. The model also leaves out the two hospitals that the join does not place. So the hospital hours short of
water are lower here than in fact.
