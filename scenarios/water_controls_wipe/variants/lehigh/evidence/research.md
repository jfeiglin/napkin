# Lehigh County and Erie, Pennsylvania: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:lehigh, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

Lehigh County and Erie are in the family because their utilities helped each other after Superstorm Sandy in
2012. Erie Water Works answered a generator request from Lehigh County Authority within 13 minutes, and the unit
ran on site in less than 24 hours (claim `E-SC43-OFFER-TIME`). The place has two systems with no connection
between them. Lehigh County Authority (LCA) runs the City of Allentown water system, its City Division, under a
lease (`lehigh_county_authority`, PA3390024). Erie Water Works (`erie_water`, PA6250028) takes its water from
Lake Erie. Each system sells water to systems outside the place.

## The sources

Eleven documents give the values. All were retrieved on 25 October 2026, and all 15 claims are verified.

- For LCA: its Annual Comprehensive Financial Report for 2025, with a letter of 30 June 2026 (source
  `lehigh_lca2026_acfr_2025`); the 2022 financial statements in its board packet of 11 September 2023 (source
  `lehigh_lca2023_board_agenda_sep11`); its blog post of 14 July 2020 on where the water comes from (source
  `lehigh_lca2020_where_water`); and the City of Allentown's 2024 concession report of 30 August 2025 (source
  `lehigh_allentown2025_concession_2024`).
- For Erie Water Works: the executive summary of its Water System Master Plan, February 2017 (source
  `lehigh_eww2017_master_plan_summary`), and the slides of 14 February 2017 on the same plan (source
  `lehigh_eww2017_master_plan_presentation`); its newsletters of the third quarter of 2019 and of 2023 (sources
  `lehigh_eww2019_newsplash_q3` and `lehigh_eww2023_newsplash_q3`); the rate study of 17 October 2019 (source
  `lehigh_eww2019_rate_study`); its page about itself (source `lehigh_eww2026_who_we_are`); and its 2025 water
  quality report (source `lehigh_eww2026_wqr_2025`).

Lehigh County Authority:

- **Peak day** (`E-SC43-LEHIGH-LCA-PEAK`, 2025 report). A table gives the average day and the highest day of the
  City Division for each year from 2016 to 2025. The highest day of the ten years is 30,870,900 gallons in 2022,
  when the average day was 22,504,438 gallons. The page is printed sideways, and its text layer runs the four
  figures of each year together. The surplus column, safe yield less the highest day, confirms how they split.
- **Sales** (`E-SC43-LEHIGH-LCA-SALES-2022`, 2022 statements; `E-SC43-LEHIGH-LCA-SALES`, 2025 report;
  `E-SC43-LEHIGH-LCA-BULK`, concession report). LCA's Suburban Division bought 7.34 Mgal a day from the City
  Division in 2022, 6.89 in 2024 and 6.46 in 2025. The City also supplies South Whitehall, Salisbury and Hanover
  townships and the Whitehall Water Authority. No source gives the volumes of these four bulk users.
- **Plant** (`E-SC43-LEHIGH-LCA-CAPACITY`, concession report). The City's permits allow 39 Mgal a day of
  drinking water. At most 30 Mgal a day passes through the Water Filtration Plant. In 2024, 48% of the finished
  water came from two springs, and only the creek and river water needs treatment at the plant.
- **Storage** (`E-SC43-LEHIGH-LCA-STORAGE`, concession report; `E-SC43-LEHIGH-LCA-RESERVOIRS`, blog). Three
  finished water reservoirs, of 30, 10 and 10 Mgal, hold 50 Mgal. Four elevated tanks serve the higher parts of
  the city, and no source gives their volume.

Erie Water Works:

- **Peak day** (`E-SC43-LEHIGH-ERIE-DEMAND`, master plan). From ten years of data, the plan gives an average day
  of 23.9 Mgal and a highest day of 41.1 Mgal. It does not give the year of the highest day. The plan leaves out
  the system that Erie Water Works had just bought from the Millcreek Township Water Authority, one of its bulk
  customers.
- **Average after 2017** (`E-SC43-LEHIGH-ERIE-AVERAGE-2019`, 2019 newsletter). In 2019 the system treated an
  average of 24 Mgal a day, close to the average of the plan.
- **Sales** (`E-SC43-LEHIGH-ERIE-BULK`, rate study; `E-SC43-LEHIGH-ERIE-BUYERS`, web page). The rate study
  projects 513,293 hundred cubic feet of billed bulk sales for fiscal 2020, or 1.052 Mgal a day. The bulk buyers
  are the Summit Township and Fairview Township water authorities.
- **Plants** (`E-SC43-LEHIGH-ERIE-CAPACITY`, master plan; `E-SC43-LEHIGH-ERIE-RATINGS`, slides;
  `E-SC43-LEHIGH-ERIE-PLANTS-2025`, 2025 report). The Richard S. Wasielewski plant treats 45.0 Mgal a day, and the
  Chestnut Street plant 32.0. The Wasielewski membrane plant gives only 30.0 Mgal a day in water at 0.5 °C. The
  Chestnut Street plant adds water at peaks and during maintenance. In 2017 Erie Water Works and its engineers
  studied a lower rating of 25.0 Mgal a day for that plant, and no source says whether it was adopted. Both plants
  were in service in 2025.
- **Storage** (`E-SC43-LEHIGH-ERIE-STORAGE`, 2023 newsletter). Nearly 77 Mgal: about 14 Mgal in 13 tanks and
  63 Mgal in six ground reservoirs. Before the Millcreek tanks were added, the 2017 slides give 71.25 Mgal.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report, over the average
  of the same period where a source gives it (`A-SC43-PEAK-DAY`). For LCA that is 30.8709 Mgal in 2022, a ratio of
  30.8709 / 22.5044 = 1.3718. For Erie Water Works it is the 41.1 Mgal of the master plan, a ratio of
  41.1 / 23.9 = 1.7197.
- **Sales** (`sold`). LCA: the 2022 sale to its Suburban Division, 7.34 × 1.3718 = 10.0688 Mgal a day. The sale
  continues. The sales to the four other bulk users stay in the daily use, so this figure is a floor. Erie Water
  Works: 1.052 × 1.7197 = 1.8090 Mgal a day.
- **Daily use** (`demand`). LCA: (30.8709 − 10.0688) / 1.05 = 19.8115 Mgal a day. Erie Water Works:
  (41.1 − 1.8090) / 1.05 = 37.4200 Mgal a day. The model adds the pipe losses of 5% on top.
- **Plant capacity** (`nameplate`). LCA: 39 Mgal a day, the permitted output of the plant site, with filtered
  creek and river water and spring water that needs only disinfection. Erie Water Works: 45.0 + 32.0 =
  77 Mgal a day, both plants.
- **Storage** (`storage`). LCA 50 Mgal, the three reservoirs. Erie Water Works 77 Mgal. The model keeps the
  family's usable share of 0.8878 (claim `E-SC43-USABLE-STORAGE`).
- **Purchases.** The model gives neither system a purchase (`bought` = 0).

From the family's evidence: SDWIS lists 118,000 people served by LCA's Allentown Division (claim
`E-SC43-SDWIS-PA3390024`) and 220,001 by Erie Water Works (claim `E-SC43-SDWIS-PA6250028`). The value added comes
from Lehigh County and Erie County, Pennsylvania. Four hospitals lie in Erie Water Works' service area (claim
`E-SC43-HOSPITALS-ERIE-WATER`): Saint Vincent Hospital, the Erie VA Medical Center, UPMC Hamot and the LECOM
Medical Center. The family's join places no hospital in the service area of LCA's Allentown Division.

## What the model does not show

The City Division sells water to four bulk users whose volumes no source gives. The model keeps their water in LCA's
own use, which LCA serves before its sales. So LCA's own customers can get less of the water that is left here than
in fact. The volume of LCA's four elevated tanks is not known, and the model leaves it out, so LCA's stored water
can run out sooner here than in fact.
