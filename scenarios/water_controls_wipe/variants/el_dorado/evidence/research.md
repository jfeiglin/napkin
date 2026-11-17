# El Dorado County, California: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:el_dorado, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

El Dorado County is in the family because of two reports of its districts. The El Dorado Irrigation District
(EID) estimates a lead time of about 32 weeks for new pumps (claim `E-SC43-PUMP-LEAD-TIME`). The Georgetown
Divide Public Utility District gives the labor hours of its field crews (claim `E-SC43-FIELD-HOURS`). The place
has two systems with no connection between them: the EID main system (`el_dorado`, CA0910001) and the Georgetown
Divide Public Utility District (`georgetown_divide`, CA0910013). EID sells treated water to the City of
Placerville, which is outside the place.

## The sources

Five documents give the values. All were retrieved on 25 October 2026.

- The El Dorado LAFCO review of EID, approved on 2 December 2020 (source `eldorado_edlafco2020_eid_msr`).
- The public review draft of the LAFCO review of the small and medium water districts, August 2022 (source
  `eldorado_edlafco2022_small_water_msr`).
- The public review draft of the Georgetown Divide 2025 Urban Water Management Plan, 29 May 2026 (source
  `eldorado_gdpud2026_uwmp2025_draft`).
- The EID 2025 Urban Water Management Plan, adopted on 8 June 2026 (source `eldorado_eid2026_uwmp2025`).
- The EID project page for the El Dorado Hills Water Treatment Plant, which carries no date (source
  `eldorado_eid2026_edhwtp_page`).

The first three opened directly. The EID site, eid.org, refused a direct download of the last two (HTTP 403),
and the Internet Archive reset every connection. So their text came through a third-party retrieval, which
loses some table cells. Their three claims are partial: `E-SC43-ELDORADO-EID-USE`, `E-SC43-ELDORADO-EID-STORAGE`
and `E-SC43-ELDORADO-EID-EDHWTP`. The other eight claims are verified.

The El Dorado Irrigation District:

- **Peak day** (`E-SC43-ELDORADO-EID-MAXDAY`, LAFCO 2020). The review reprints a table of the EID 2013 master
  plan. The highest day of each plant in 2013 was 43 Mgal at Reservoir A, 22.6 Mgal at Reservoir 1 and 14.3 Mgal
  at El Dorado Hills, 79.9 Mgal in all. The table does not say that the three days were the same day.
- **Use** (`E-SC43-ELDORADO-EID-USE`, EID 2025 plan). The total potable water use of 2025 is 33,103 acre-feet,
  with an estimated distribution loss of 4,440 acre-feet. The deliveries include 1,032 acre-feet to the City of
  Placerville. The loss is 13.4% of the total use, but the plan's text gives about 11.1%. The plan does not
  explain the difference.
- **Plants** (`E-SC43-ELDORADO-EID-PLANTS`, LAFCO 2020; `E-SC43-ELDORADO-EID-EDHWTP`, project page). The review
  gives the capacities as 56 to 64 Mgal a day at Reservoir A, 26 at Reservoir 1 and 19.5 to 26 at El Dorado
  Hills. The lower values include filter limits. The supply from Jenkinson Lake limits Reservoir A to about
  42 Mgal on a day. The project page still gives 19.5 Mgal a day as the operational capacity of El Dorado Hills,
  near the summer peak of the area that it serves.
- **Storage** (`E-SC43-ELDORADO-EID-STORAGE`, EID 2025 plan; `E-SC43-ELDORADO-EID-STORAGE2013`, LAFCO 2020). The
  2025 plan gives 33 storage facilities with approximately 93 Mgal. The 2013 master plan lists 33 facilities with
  81.12 Mgal.

The Georgetown Divide Public Utility District:

- **Peak day** (`E-SC43-ELDORADO-GDPUD-MAXDAY`, LAFCO 2022). The maximum day demand for treated water was
  3.88 Mgal in 2017. LAFCO cites it from a State Water Board inspection of 2019.
- **Use** (`E-SC43-ELDORADO-GDPUD-USE`, 2025 plan). The gross water use of 2025 is 1,726 acre-feet, the potable
  water that left the two plants. Of this, 363 acre-feet is real water loss. The district also delivered
  3,803 acre-feet of raw irrigation water outside the potable system.
- **Plants and system** (`E-SC43-ELDORADO-GDPUD-PLANTS`, LAFCO 2022; `E-SC43-ELDORADO-GDPUD-SYSTEM`, 2025
  plan). The Walton Lake plant and the Sweetwater Treatment Plant give about 3 Mgal a day each. The district has
  no intertie with another system and cannot buy or import water.
- **Storage** (`E-SC43-ELDORADO-GDPUD-STORAGE`, LAFCO 2022). 2.824 Mgal in 10 tanks. The 2025 plan counts
  11 tanks and gives no volume.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report (`A-SC43-PEAK-DAY`).
  The 2025 plans give no highest day, so the latest reports that give one are the LAFCO reviews. For EID that is the
  sum of the 2013 highest days of the three plants, 79.9 Mgal. The 2025 use, 33,103 acre-feet, is 29.55 Mgal a day,
  so the ratio is 2.7037. For Georgetown Divide it is the 3.88 Mgal of 2017. Its 2025 use, 1,726 acre-feet or 1.541
  Mgal a day, gives a ratio of 2.518.
- **Sales** (`sold`). EID's only sale to another system is to Placerville: 1,032 acre-feet in 2025, or
  0.921 Mgal a day. At the peak ratio it is 2.491 Mgal a day. Georgetown Divide sells no water.
- **Daily use** (`demand`). EID: (79.9 − 2.491) / 1.05 = 73.72 Mgal a day. Georgetown Divide: 3.88 / 1.05 =
  3.695 Mgal a day. The model adds the pipe losses of 5% on top.
- **Plant capacity** (`nameplate`). EID: 56 + 26 + 19.5 = 101.5 Mgal a day, the lower capacities. Georgetown
  Divide: 3 + 3 = 6 Mgal a day.
- **Storage** (`storage`). EID 93 Mgal, from the 2025 plan. Georgetown Divide 2.824 Mgal.
- **Purchases.** The model gives neither system a purchase (`bought` = 0). Georgetown Divide cannot buy or import
  water.

From the family's evidence: SDWIS lists 128,408 people served by EID (claim `E-SC43-SDWIS-CA0910001`) and 9,434
by Georgetown Divide (claim `E-SC43-SDWIS-CA0910013`). The value added comes from El Dorado County, California.
One hospital lies in EID's service area, Marshall Medical Center (claim `E-SC43-HOSPITALS-EL-DORADO`). Its point
also lies in the service area of the City of Placerville. The family's rule gives it to the system of the place
(`A-SC43-HOSPITAL-JOIN`). The join gives Georgetown Divide no hospital.

## What the model does not show

The EID peak is a sum of the highest days of three plants, and these days need not fall on one day. Annual use
was also higher in 2013. So the system's present highest day is probably lower. With the family ratio on the
2025 average, the peak would be 46.5 Mgal a day. The daily use would then be about 42.9 Mgal a day, against
73.72 in the model. So EID's stored water runs out sooner here than in fact. The 2024 EID master plan can give
a recent maximum day, but no copy of it opened.

The supply from Jenkinson Lake limits the three EID plants to about 87.5 Mgal a day together. This is less than
the 101.5 Mgal a day of the model. So EID can produce more water by hand and refill faster here than in fact.
