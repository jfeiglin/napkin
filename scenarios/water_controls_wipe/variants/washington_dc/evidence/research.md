# Washington, DC: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:washington_dc, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

Washington, DC is in the family because a study estimates the cost of a loss of the region's water supply (claim
`E-SC43-NCR-BENCHMARK`). It gives almost 15 billion dollars of regional product lost in the first month. The
place has five systems that take Potomac water. The Washington Aqueduct (`washington_aqueduct`, DC0000001)
treats water and sells all of it to DC Water (`dc_water`, DC0000002), Arlington (`arlington`, VA6013010) and
Fairfax Water (`fairfax_water`, VA6059501). Fairfax Water also has its own plants. WSSC Water (`wssc_water`,
MD0150005) has its own plants and no connection to the others in the model.

## The sources

Twelve documents give the values. All were retrieved on 25 October 2026.

- The Interstate Commission on the Potomac River Basin (ICPRB) 2025 Washington Metropolitan Area Water Supply
  Study, December 2025 (source `dc_icprb2025_wma_supply_study`).
- DC Water's Annual Comprehensive Financial Report for fiscal 2025, 16 February 2026 (source
  `dc_dcwater2026_acfr_fy2025`), the overview of its FY 2027 budget, adopted on 5 March 2026 (source
  `dc_dcwater2026_budget_fy2027`), and its 2023 Independent Engineering Assessment, 30 September 2023 (source
  `dc_peer2023_dcwater_iea`).
- Arlington's draft Water Distribution System Master Plan of 19 May 2014 (source `dc_arlington2014_wdsmp`), its
  Water Quality Overview 2025 (source `dc_arlington2025_wqr`) and its undated water page (source
  `dc_arlington_water_page`).
- The Water Supply chapter of the Fairfax County FY 2026 to FY 2030 Capital Improvement Program (source
  `dc_fairfaxcounty2025_cip_water`) and Fairfax Water's 2026 budget, adopted on 11 December 2025 (source
  `dc_fairfaxwater2025_budget_2026`).
- WSSC Water's undated page about itself (source `dc_wssc_about`), Chapter 3 of the Montgomery County water and
  sewer plan for 2022 to 2031 (source `dc_montgomery2022_wsp_ch3`) and Chapter 3 of the Prince George's County
  2018 water and sewer plan, adopted in 2019 (source `dc_princegeorges2019_wsp_ch3`).

The Arlington and Prince George's sites refused a direct download (HTTP 403), and the Montgomery address now
returns HTTP 404. The Internet Archive reset the connection on repeated tries. So four documents came through a
third-party retrieval; the Montgomery plan came from the archive capture of 13 February 2026. Their six claims
are partial: `E-SC43-DC-ARLINGTON-PEAK`, `E-SC43-DC-ARLINGTON-CONNECTION`, `E-SC43-DC-WSSC-STORAGE-MONTGOMERY`,
`E-SC43-DC-WSSC-MAXDAY-HISTORY`, `E-SC43-DC-WSSC-SALES` and `E-SC43-DC-WSSC-STORAGE-PG`. The other 20 claims are
verified.

## The values

Every system of the place has a recorded peak, so the family median ratio does not apply here
(`A-SC43-PEAK-DAY`). The model adds the pipe losses of 5% on top of each daily use.

The Washington Aqueduct:

- **Daily use and sales.** None (`demand` = 0, `sold` = 0). The Aqueduct has no distribution system. ICPRB names
  three customers only: DC Water, Arlington County and Fairfax Water (`E-SC43-DC-AQUEDUCT-CUSTOMERS`). Its table
  of Arlington's purchases counts the 0.30 Mgal a day of Fort Myer inside them (`E-SC43-DC-ARLINGTON-PURCHASES`).
  The 2023 production from data, 130.6 Mgal a day, is 5.1 Mgal a day more than the customer estimates. The study
  does not explain the gap, and no source calls it a sale.
- **Plant capacity.** 300 Mgal a day (`nameplate`), the design capacity of the Dalecarlia and McMillan plants
  (`E-SC43-DC-AQUEDUCT-PLANT`). Their current maximum production rates are 225 and 120 Mgal a day, 345 in all.
  The study does not say why the design capacity is lower.
- **Storage.** 49 Mgal (`storage`), as DC Water reports it (`E-SC43-DC-AQUEDUCT-STORAGE`). DC Water's 2023
  assessment places three Aqueduct reservoirs in DC Water's pressure zones: Foxhall 14.5, Van Ness 14.6 and Fort
  Reno No. 2 20 Mgal, 49.1 Mgal in all (`E-SC43-DC-AQUEDUCT-RESERVOIRS`).

DC Water:

- **Peak use.** Exhibit 18 of the financial report gives the maximum day of water delivered to the system for
  fiscal 2016 to 2025 (`E-SC43-DC-DCWATER-MAXDAY`). The highest is 137.2 Mgal in fiscal 2024, from October 2023
  to September 2024, with an average day of 100.5 Mgal. The water delivered includes water that is lost or not
  billed.
- **Daily use.** No source reports a sale to another system: 137.2 / 1.05 = 130.667 Mgal a day (`demand`).
- **Plant capacity and storage.** No plant (`nameplate` = 0): DC Water buys all its water from the Aqueduct,
  about 74% of the Aqueduct's finished water (`E-SC43-DC-DCWATER-PURCHASE`). It stores about 60 Mgal at eight
  facilities (`storage`; `E-SC43-DC-DCWATER-STORAGE`).

Arlington:

- **Peak use.** The 2025 overview gives a use of about 20 Mgal a day and a peak near 33 Mgal a day on the hottest
  summer days (`E-SC43-DC-ARLINGTON-PEAK`). The undated page gives about 23 and near 35 Mgal a day
  (`E-SC43-DC-ARLINGTON-CONNECTION`). Its 23 matches the Aqueduct supply of 2007 to 2012 in the 2014 plan,
  22.46 to 24.81 Mgal a day (`E-SC43-DC-ARLINGTON-PLAN`). The 20 matches the 2023 purchases, 20.84 Mgal a day. So
  the scenario takes the 33 Mgal a day of the 2025 overview.
- **Daily use.** 33 / 1.05 = 31.429 Mgal a day (`demand`). The 0.30 Mgal a day that Arlington bills to Fort Myer
  stays in this use, because no separate Fort Myer system was found.
- **Plant capacity and storage.** No plant (`nameplate` = 0): virtually all the water comes from the Dalecarlia
  plant. Fort Barnard, Lee and Minor Hill hold 32 Mgal (`storage`), and the county page gives the same figure.
  Arlington also buys water for its Willston area from Fairfax Water; the model leaves out this small sale.

Fairfax Water:

- **Peak use.** The record is 259 Mgal on 7 July 2010 (`E-SC43-DC-FAIRFAX-PEAKDAY`). It is from before Fairfax
  Water took over the Falls Church system in 2014. The 2024 supply was 170.5 Mgal a day: 64.1 from the Occoquan,
  95.0 from the Potomac and 11.4 bought from the Aqueduct (`E-SC43-DC-FAIRFAX-SUPPLY`). The study gives the
  peak-day factor of the record year, peak-day production over that year's average production: 1.9 for Fairfax
  Water. The ratio is that factor, 1.9, not the record over the 2024 supply (1.5191).
- **Sales.** Fairfax Water sold 73.8 Mgal a day to wholesale customers in 2024, none of them in the place
  (`E-SC43-DC-FAIRFAX-WHOLESALE`). At the peak ratio: 73.8 × 1.9 = 140.22 Mgal a day (`sold`).
- **Daily use.** (259 − 140.22) / 1.05 = 113.124 Mgal a day (`demand`). This leaves 118.78 Mgal of retail use on
  the peak day, 1.23 times the 2024 supply less the wholesale sales (170.5 − 73.8 = 96.7 Mgal a day). The factor is
  rounded and comes from 2010, when Fairfax Water sold more water to Loudoun Water, so the peak sales here can be
  high and the daily use low.
- **Plant capacity.** The Corbalis plant 225 and the Griffith plant 120 Mgal a day, 345 Mgal a day in all
  (`nameplate`; `E-SC43-DC-FAIRFAX-PLANTS`). The Occoquan Reservoir has a safe yield of about 82.5 Mgal a day,
  below the capacity of the Griffith plant.
- **Storage.** 56 Mgal of distribution storage at 21 locations and 37 Mgal of clear wells at the two plants,
  93 Mgal in all (`storage`; `E-SC43-DC-FAIRFAX-STORAGE`).

WSSC Water:

- **Peak use.** The record is 263 Mgal on 8 June 1999 (`E-SC43-DC-WSSC-PEAKDAY`). ICPRB also gives a previous
  high of 267 Mgal on 8 July 1988, outside the period that it reviews. The WSSC table in the Montgomery plan
  agrees: 263.4 Mgal in 1999 is the highest day of 1995 to 2020, with an average of 168.2 Mgal
  (`E-SC43-DC-WSSC-MAXDAY-HISTORY`), a ratio of 1.57. In 2020 the highest day was 222.2 Mgal. ICPRB gives the
  peak-day factor of the record year as 1.6, and the ratio is that factor. The 2023 mean production is 159 Mgal a
  day.
- **Sales.** Charles County withdraws 1.8 and Howard County 4.0 Mgal a day on average, 5.8 Mgal a day in all
  (`E-SC43-DC-WSSC-SALES`). The withdrawals of Rockville and Washington, DC are negligible. At the peak ratio:
  5.8 × 1.6 = 9.28 Mgal a day (`sold`).
- **Daily use.** (263 − 9.28) / 1.05 = 241.638 Mgal a day (`demand`).
- **Plant capacity.** The Potomac plant 280 and the Patuxent plant 110 Mgal a day, 390 Mgal a day in all, as WSSC
  Water states them (`nameplate`; `E-SC43-DC-WSSC-NAMEPLATE`). ICPRB calls the 110 the emergency capacity of the
  Patuxent plant and gives 72 Mgal a day as its current capacity (`E-SC43-DC-WSSC-PLANT-RATINGS`).
- **Storage.** The Montgomery table gives 126.8 Mgal (`E-SC43-DC-WSSC-STORAGE-MONTGOMERY`). The 18 rows of the
  Prince George's table sum to 87.45 Mgal (`E-SC43-DC-WSSC-STORAGE-PG`). Both list the 18.4 Mgal of the Patuxent
  plant reservoirs: 126.8 + 87.45 − 18.4 = 195.85 Mgal (`storage`).

The connections (`capacity`):

- **Aqueduct to DC Water: 194 Mgal a day.** DC Water's Bryant Street Pumping Station can pump 194 Mgal a day into
  the zones that the Aqueduct supplies (`E-SC43-DC-DCWATER-PUMPING`). This is a floor. The Aqueduct's Dalecarlia
  Pumping Station, 310 Mgal a day firm, feeds the same zones, and it also serves Arlington and Fairfax Water. The
  purchase agreement sets no limit.
- **Aqueduct to Arlington: 35 Mgal a day.** This is the highest flow that Arlington reports, so it is a floor. The
  agreement places no limit on purchases, and no source rates the mains.
- **Aqueduct to Fairfax Water: 31 Mgal a day.** The Falls Church contract allows up to 31 Mgal a day
  (`E-SC43-DC-FAIRFAX-CONTRACT`). ICPRB uses the same limit, and the pipe from Dalecarlia can carry 35 Mgal a day
  (`E-SC43-DC-FAIRFAX-TIE-LIMITS`).
- Each buyer has one seller, so it asks the Aqueduct for all that it needs, up to the capacity (`A-SC43-TIES`).
  On an average day DC Water takes 100.7 Mgal (fiscal 2025), Arlington 20.84 Mgal (2023) and Fairfax Water
  11.4 Mgal (2024).

From the family's evidence: SDWIS lists 0 people and 3 connections for the Aqueduct (claim
`E-SC43-SDWIS-DC0000001`), so it has no value added of its own. It lists 632,323 people for DC Water, 215,000 for
Arlington, 1,121,613 for Fairfax Water and 1,900,000 for WSSC Water (claims `E-SC43-SDWIS-DC0000002`,
`E-SC43-SDWIS-VA6013010`, `E-SC43-SDWIS-VA6059501` and `E-SC43-SDWIS-MD0150005`). The value added comes from the
District of Columbia, Arlington County, the BEA area of Fairfax County with Fairfax City and Falls Church, and
Montgomery and Prince George's counties. SDWIS lists Montgomery County only for WSSC Water, but four of its
hospitals are in Prince George's County. The hospitals in the service areas are 8 for DC Water, 1 for Arlington,
2 for Fairfax Water and 9 for WSSC Water (claims `E-SC43-HOSPITALS-DC-WATER`, `E-SC43-HOSPITALS-ARLINGTON`,
`E-SC43-HOSPITALS-FAIRFAX-WATER` and `E-SC43-HOSPITALS-WSSC-WATER`). The counts of Fairfax Water and WSSC Water
are floors. The Census geocoder does not match the CMS addresses of Inova Mount Vernon Hospital and Walter Reed
National Military Medical Center. United Medical Center lies in both the WSSC Water and the DC Water areas, and
the family's rule gives it to DC Water, the smaller area (`A-SC43-HOSPITAL-JOIN`).

The Aqueduct's plants also supply the federal government (`E-SC43-DC-DCWATER-PURCHASE`). A federally owned
system serves the Pentagon and Arlington Cemetery and supplies National Airport, and the 2014 plan does not say
who supplies it (`E-SC43-DC-ARLINGTON-PLAN`). SDWIS lists Naval Station Washington (DC0000003) and Joint Base
Anacostia-Bolling (DC0000004) as community systems in DC that buy surface water. No source gives the volumes of
these systems. So the model gives them no sale of their own: their water stays in the buyers' use, and the
model does not count their people.

The place also has the run "The Aqueduct only". In it the first move reaches the Aqueduct alone, and its buyers
lose water only through their connections.

## What the model does not show

The Aqueduct's 49 Mgal sit in three reservoirs in DC Water's zones. The model keeps them with the Aqueduct, so
they serve all three buyers. So Arlington and Fairfax Water can keep water longer here than in fact, and DC Water
can lose it sooner.

The peak records of two systems are old: Fairfax Water's is from 2010 and WSSC Water's from 1999. WSSC Water's
recent highest days are lower, 222.2 Mgal in 2020. So the stored water of these systems can run out sooner here
than in fact.

Fairfax Water buys Aqueduct water for its Falls Church area through the pipe from Dalecarlia. In the model its
own plants cover all its use on a normal day, so it takes no Aqueduct water then. A loss of the Aqueduct alone
can then cut less water for Fairfax Water here than in fact. The sources do not say whether its own plants can
supply the Falls Church area.
