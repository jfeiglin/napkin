# Juneau, Alaska: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:juneau, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of the place's water system and where each one comes from.

Juneau is in the family because one water system serves the whole city (claims `E-SC43-JUNEAU-UTILITY`,
`E-SC43-JUNEAU-POP`). The place has one system, the City and Borough of Juneau water utility (`juneau`,
AK2110342). It draws on two sources: the Last Chance Basin wellfield, which needs chlorination only, and the
Salmon Creek membrane filtration plant. It sells to no other water system and buys from none.

## The sources

Six documents give the values. Six claims are verified and one is partial.

- **Supply** (`E-SC43-JUNEAU-CBJ-SUPPLY`, `E-SC43-JUNEAU-CBJ-STORAGE`, the draft Municipal Drinking Water Supply
  Plan of 5 June 2012). Average use is 3.5 to 4.5 Mgal a day, higher in summer, mostly from sales to cruise
  ships. Last Chance Basin typically gives 3 to 4 Mgal a day and Salmon Creek 0 to 2. Seven reservoirs store
  11 Mgal; the Mill Tunnel holds about 3.2 Mgal in the mountain. The plan gives no highest day and no rated
  capacity for the wells.
- **Peak day** (`E-SC43-JUNEAU-CBJ-PEAK`, Alaska Public Media, 21 November 2013). On average the utility
  distributes 3.5 Mgal a day, and in summer this can spike to 5 Mgal. In summer 2013 the cruise ships were held
  to 200,000 gallons a day in all. The superintendent gives the system a design capacity of 5 Mgal a day, with
  the wells running up to 23 hours a day.
- **Wellfield output** (`E-SC43-JUNEAU-CBJ-LCB-OUTPUT`, KTOO, 9 and 12 May 2014). With Salmon Creek offline for
  turbidity, Last Chance Basin drew about 2,100 gal/min, "pumping for all it's worth", and the city stopped its
  sales to cruise ships. This claim is partial: the site refused the fetch (HTTP 403), the archive could not be
  reached, and the text came through a third-party retrieval.
- **Plants** (`E-SC43-JUNEAU-CBJ-PLANTS`, the utility's water system page). The Salmon Creek plant has a
  production capacity of 2 Mgal a day; the wellfield draws through seven wells; the system has six reservoirs
  and three contact tanks.
- **Deliveries** (`E-SC43-JUNEAU-CBJ-DELIVERED`, the annual financial report for fiscal 2024). 1,251 Mgal were
  delivered in fiscal 2024, 3.418 Mgal a day.
- **Outages** (`E-SC43-JUNEAU-CBJ-SC-OUTAGE`, the 2026 water management plan page). Salmon Creek gives about a
  third of the source water. Penstock work stops it from 1 April to 30 June of each year from 2026 to 2029, and
  the utility then suspends its supply to cruise ships.

## The values

- **Peak use.** 5.0 Mgal a day, the summer peak of 2013, the latest that a source gives (`A-SC43-PEAK-DAY`). Its
  ratio to the 3.5 Mgal a day average of the same story is 1.42857.
- **Daily use.** The utility sells no water to other systems, so 5.0 / 1.05 = 4.7619 Mgal a day (`demand`). The
  cruise ships are customers, not water systems, so their water stays in the daily use.
- **Plant capacity.** The wellfield at full pumping, 2,100 gal/min or 3.024 Mgal a day, plus the Salmon Creek
  plant's 2 Mgal a day: 5.024 Mgal a day (`nameplate`). This agrees with the design capacity of 5 Mgal a day
  that the superintendent gave in 2013.
- **Storage.** 11 Mgal (`storage`), the 2012 figure. No later volume is published.
- **Purchases and sales.** None (`bought` = 0, `sold` = 0).

From the family's evidence: SDWIS lists 38,526 people served (claim `E-SC43-SDWIS-AK2110342`). That is more than
the City and Borough's residents: BEA gives 31,572 for 2024, and the Census Bureau 31,609 for July 2025 (claim
`E-SC43-JUNEAU-POP`). The utility says it serves most residents, businesses and tourists, so the system's count is
not a count of residents, and the study follows the larger figure. The value added comes from the City and
Borough of Juneau. One hospital lies in the system's
service area (claim `E-SC43-HOSPITALS-JUNEAU`).

## What the model does not show

On its peak day Juneau produces 5.024 Mgal against a need of 5.0 Mgal with its pipe losses, so its stored water
refills at almost nothing after an outage. In 2013 and 2014 the city met its peaks only because it cut its sales
to cruise ships and drew down its reservoirs; the model cannot cut the supply to one class of customers, so the
interruption can be longer here than in fact. No rated capacity of the wellfield was found: the 2014 reading
came before a planned expansion, and the wellfield now has seven wells, not five, so the capacity today may be
higher. The peak is a rounded figure from a news report, with no date, reached while the cruise sales were held
down. From April to June of 2026 to 2029 only the wellfield is available, which the model does not follow.
