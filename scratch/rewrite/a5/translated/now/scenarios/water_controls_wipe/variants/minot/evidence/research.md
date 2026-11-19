# Minot, North Dakota: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:minot, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water systems and where each one comes from.

Minot is in the family because ransomware at the city cut the link to the controls of a regional water supply
in March 2026 (claim `E-SC43-NAWS-SCADA`). The Northwest Area Water Supply (NAWS) ended its connection with the
city's SCADA at once. Its own SCADA was back in full operation three days later, and the link with the city
stayed cut for at least 67 days. The place has two systems. The City of Minot (`minot`, ND5100660) has the only
treatment plant. NAWS (`naws`, ND5101687), which the State Water Commission owns, buys all its water from
Minot.

## How the water moves

The Minot plant treats ground water from 16 wells (`E-SC43-MINOT-MINOT-TANKS`). It sends the water to the High
Service Pump Station beside the plant, which the State Water Commission owns. City operators set all its pumps
through the city SCADA (`E-SC43-MINOT-NAWS-PUMPS`). Four pumps supply the city directly. Five NAWS pumps feed
the NAWS pipeline, which carries city water to two city connections and to Minot Air Force Base. The same
pipeline carries water to ten North Prairie Rural Water connections and to the nine NAWS contract customers
(`E-SC43-MINOT-NAWS-BUYERS`).

In 2024 the two meters of the station pumped 2,448,402,000 gallons, 6.6896 Mgal a day over 366 days
(`E-SC43-MINOT-MINOT-PRODUCTION`). Of the city's 2,179,687,415 gallons, 1,230,117,904 went through the NAWS
meter, about half. The nine contract customers used 295,837,470 gallons, 0.8083 Mgal a day.

## The sources

Fourteen documents give the values. All were retrieved on 25 October 2026 and read in full, and all 19 claims
are verified.

- From the Department of Water Resources and the State Water Commission: the NAWS project update to the legislature
  of 9 March 2023 (source `minot_dwr2023_naws_project_update`), the NAWS brochure of March 2024 (source
  `minot_dwr2024_naws_brochure`), the packets of the NAWS Authority meetings of 25 November 2025 and 28 May 2026
  (sources `minot_dwr2025_naws_authority_nov` and `minot_dwr2026_naws_authority_may`) and the NAWS flow demands of
  Amendment No. 2, 28 September 2022 (source `minot_swc2022_naws_flow_demands`).
- From the city: the 2014 distribution master plan (source `minot_hei2014_distribution_master_plan`), a blog
  post of 11 June 2021 (source `minot_minot2021_blog_naws`) and the page of the water treatment plant (source
  `minot_minot2026_wtp_page`).
- From the news: the Minot Daily News of 24 June 2020, 4 June 2021, 12 October 2021 and 31 January 2025
  (sources `minot_minotdailynews2020_water_use`, `minot_minotdailynews2021_restriction`,
  `minot_minotdailynews2021_sw_tower` and `minot_minotdailynews2025_naws_funds`), KFYR of 30 July 2018 (source
  `minot_kfyr2018_north_tower`) and the Kenmare News of 23 September 2009 (source
  `minot_kenmarenews2009_naws_tower`).

## The values

The City of Minot:

- **Peak use.** The highest day that a source reports is in a 2020 article: peak summer use often rises to the
  13 to 14 Mgal a day that the plant can treat, in dry times (`E-SC43-MINOT-MINOT-PEAK`). The scenario takes the
  lower end, 13 Mgal (`A-SC43-PEAK-DAY`). Against the 2024 average of 6.6896 Mgal a day, the ratio is 1.9433;
  it divides a 2020 peak by a 2024 average.
- **Other reports.** The 2014 plan gives a maximum day of 7,200 gal/min, but this equals the mean of July 2012,
  so it is a monthly mean and not one day (`E-SC43-MINOT-MINOT-PRODUCTION-2012`). In early June 2021 several wells
  failed, use rose to about 11 Mgal a day and the city restricted water use (`E-SC43-MINOT-MINOT-USE-2021`).
  These are context and set no value.
- **Sales.** North Prairie Rural Water takes about 0.717 Mgal a day, which the 2022 flow table counts inside the
  Minot estimated peak usage (`E-SC43-MINOT-NAWS-CONTRACT`). The scenario takes it as the peak-day sale (`sold`).
  The water for NAWS goes through the connection.
- **Daily use.** Less the NAWS sale at the city's ratio (0.8083 × 1.9433 = 1.5708) and the North Prairie sale:
  (13 − 1.5708 − 0.717) / 1.05 = 10.2021 Mgal a day (`demand`). No source separates the use of Minot Air Force
  Base from the city's use, so it stays in this use.
- **Plant capacity.** 18 Mgal a day (`nameplate`), the capacity that the Department of Water Resources gave in 2023
  and in January 2025 (`E-SC43-MINOT-MINOT-CAPACITY`, `E-SC43-MINOT-MINOT-CAPACITY-2025`). The wells give about 17
  Mgal a day. In June 2021, before the second phase of plant work, the plant could treat about 12 Mgal a day
  (`E-SC43-MINOT-MINOT-OUTSIDE-USE-2021`).
- **Storage.** The 2014 plan gives 12.5 Mgal (`E-SC43-MINOT-MINOT-STORAGE-2014`), and a 1.5 Mgal southwest tower
  went online in 2022 (`E-SC43-MINOT-MINOT-SW-TOWER`): 12.5 + 1.5 = 14.0 Mgal (`storage`). The city page lists
  three ground reservoirs of 3 Mgal and five elevated tanks. With the tank volumes of the other sources, among
  them the 1.5 Mgal north tower of 2018 (`E-SC43-MINOT-MINOT-NORTH-TOWER`), it gives the same total.
- **Purchases.** None (`bought` = 0): no lake water flowed through NAWS in the period.

NAWS:

- **Daily use and plant capacity.** None (`demand` = 0, `nameplate` = 0). NAWS has no retail customers. Phase I
  of its Biota plant was still under construction in May 2026, with completion expected at the end of August 2026
  (`E-SC43-MINOT-NAWS-BIOTA`). That plant only pretreats lake water before final treatment at the Minot plant.
  The 24.5 Mgal a day of the brochure (`E-SC43-MINOT-NAWS-DESIGN`) and the 9 Mgal a day of January 2025 are
  design capacities.
- **Storage.** 8.5 Mgal (`storage`): Lansford 4.5 and Bottineau 3 Mgal (`E-SC43-MINOT-NAWS-RESERVOIRS`,
  `E-SC43-MINOT-NAWS-BOTTINEAU`) and the Kenmare tower of 1 Mgal (`E-SC43-MINOT-NAWS-KENMARE-TOWER`). This is a
  lower bound: the tanks on Speedway Hill and near Berthold have no reported volume. The 10.5 Mgal South Prairie
  reservoir holds raw water and is left out.
- **Sales.** No source reports a highest day for NAWS, so the family median ratio applies: 1.54385, the median
  of the 19 systems that report both a highest and an average day. 0.8083 × 1.54385 = 1.2479 Mgal a day
  (`sold`).

The connection from Minot to NAWS carries 1.4393 Mgal a day (`capacity`). This is the total of the daily
amounts of Amendment 2 of the interim water supply agreement, 1,439,300 gallons; the 2008 agreement gave 767,600
(`E-SC43-MINOT-NAWS-CONTRACT`). The exhibit does not say whether these amounts are highest days or averages. The
NAWS pumps can move 5.76 Mgal a day on their pump curve, a figure in a draft agreement for 2027. They also carry
the city's own water (`E-SC43-MINOT-NAWS-PUMPS`). NAWS has one seller, so it asks Minot for all that it needs, up
to the capacity (`A-SC43-TIES`).

From the family's evidence: SDWIS lists 48,743 people served by Minot (claim `E-SC43-SDWIS-ND5100660`) and
0 people and 17 connections for NAWS (claim `E-SC43-SDWIS-ND5101687`), so NAWS has no value added of its own.
The value added comes from Ward County, North Dakota. One hospital lies in Minot's service area: Trinity
Hospitals (claim `E-SC43-HOSPITALS-MINOT`).

## What the model does not show

About half of the city's own water runs through the NAWS pumps and pipeline. The model counts that water as
Minot's own delivery. A stop of the NAWS pumps or pipeline would also cut those city connections, which would
need a connection back from NAWS to Minot. So the model can show a smaller loss for the city than in fact.

The peak of 13 Mgal a day rests on a general statement of 2020. Later reports are lower. In June 2021 the city
wrote that peak use comes near the 12 Mgal a day that the plant could treat then, and the 2022 flow table
estimates the city's peak usage at 9 Mgal a day. So the peak here can be high, and Minot's stored water can run
out sooner here than in fact.
