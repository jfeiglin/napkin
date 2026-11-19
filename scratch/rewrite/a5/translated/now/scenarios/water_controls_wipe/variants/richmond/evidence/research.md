# Richmond, Virginia: research note

Research date: 25 October 2026. Scenario: water_controls_wipe:richmond, a place of the water_controls_wipe package. The family's research note
([water_controls_wipe](../../../evidence/research.md)) gives the mechanism and the evidence that every place shares; this note
gives the values of Richmond's water system and where each one comes from.

Richmond is in the family because of the failure of its water plant in January 2025 and its staff on manual
operation (claims `E-SC43-RESERVOIR-BOUND`, `E-SC43-OPERATOR-COVERAGE` and `E-SC43-MANUAL-TASKS-UNFINISHED`). The
place has one system, the water system of the City of Richmond Department of Public Utilities (DPU) (`richmond`,
VA4760100), with one plant on the James River. It sells water to Henrico, Chesterfield and Hanover counties,
which are outside the place.

## The sources

Four documents give the values. All were retrieved on 25 October 2026, and all five claims are verified.

- DPU's 2025 Consumer Confidence Report, May 2026 (source `richmond_dpu2026_ccr_2025`). The Richmonder posts the
  same bytes; the note cites the City's copy.
- The packet of the joint special meeting of the Henrico County Board of Supervisors and Richmond City Council of
  30 June 2025, with DPU's slides, Henrico's slides and a draft memorandum of agreement (source
  `richmond_henrico2025_joint_meeting`).
- Henrico County's news release of 17 July 2025 (source `richmond_henrico2025_cooperation_news`).
- The follow-up report of the VDH Office of Drinking Water of 7 April 2025 (source `richmond_vdh2025_followup`).

What the documents give:

- **Production** (`E-SC43-RICHMOND-DPU-PRODUCTION`, report of 2025). The plant can produce up to 132 Mgal a day.
  In 2025 it treated 64.2 Mgal a day on average. This includes the wholesale sales and the losses, and also the
  days of 6 to 8 January 2025, when the plant produced no water. DPU supplies parts of Henrico, Chesterfield,
  Hanover, Goochland and Powhatan counties through wholesale contracts.
- **Peak day and storage** (`E-SC43-RICHMOND-DPU-STORAGE`, DPU slides; `E-SC43-RICHMOND-DPU-PEAK`, news
  release). DPU gives 69 Mgal of finished water storage. It gives a minimum storage of 48 Mgal, based on a peak
  day of 96 Mgal, under the Virginia waterworks regulation 12VAC5-590-640. Henrico calls about 96 Mgal a day the
  historical peak demand in summer. Neither source gives the year of the peak, and both round it.
- **Wholesale** (`E-SC43-RICHMOND-DPU-WHOLESALE`, slides and memorandum). DPU's slide gives three contracts, with
  average demands of 12.43, 9.14 and 6.0 Mgal a day and maximum capacities of 35, 32 and 20 Mgal a day. The
  slide does not name the counties. The memorandum matches each by its capacity and expiry: Henrico (35, to
  2040), Chesterfield (32, to 2045) and Hanover (20, to 2035). The averages carry no year. Henrico's own slides
  give its 2021 purchases from the City as 14.45 Mgal a day on average and 24.87 at most.
- **Plant** (`E-SC43-RICHMOND-DPU-PLANT`, VDH). The plant is permitted for 132 Mgal a day in two trains that can
  run independently: Plant No. 1 of 60 and Plant No. 2 of 72 Mgal a day. Two standby generators can run two
  trains at about 50 Mgal a day. The distribution system has 11 finished water storage facilities in 9 pressure
  zones. In 2025 a roof replacement took one basin of the Byrd Park Reservoir, the main reservoir, out of
  service. This halved the capacity of that reservoir.

The storage table of the VDH report is an image without a text layer, so no claim records its volumes. The
page image shows 73.2 Mgal in all and 54.18 Mgal usable, with 54.8 Mgal in the Byrd Park Reservoir. No value uses
these figures.

## The values

- **Peak use.** The family takes the highest day in the record of the system's latest report (`A-SC43-PEAK-DAY`):
  here the 96 Mgal of DPU's slides of June 2025, the one peak that the sources report. Against the 2025 average it
  is a ratio of 96 / 64.2 = 1.4953. The 2025 average includes the two days without production in January 2025.
- **Sales.** 12.43 + 9.14 + 6.0 = 27.57 Mgal a day, none of it to a system of the place. At the peak ratio it is
  41.2262 Mgal a day (`sold`). This is within the contract limits on a peak day: 35 Mgal a day for Henrico, and
  105% of 32 and 20 Mgal a day for Chesterfield and Hanover. Henrico's own figures of 2021 give it a ratio of
  24.87 / 14.45 = 1.72.
- **Daily use.** (96 − 41.2262) / 1.05 = 52.1656 Mgal a day (`demand`); the model adds the pipe losses of 5% on
  top.
- **Plant capacity.** 60 + 72 = 132 Mgal a day (`nameplate`), the permitted capacity.
- **Storage.** 69 Mgal (`storage`), the figure of DPU. The model keeps the family's usable share of 0.8878
  (claim `E-SC43-USABLE-STORAGE`).
- **Purchases.** None: the model gives the system no purchase (`bought` = 0).

From the family's evidence: SDWIS lists 233,655 people served through 83,254 service connections (claim
`E-SC43-SDWIS-VA4760100`). The report of 2025 gives 75,000 customers in the metro area, a count of a different
kind. The value added comes from the independent city of Richmond, which BEA reports as a county. Three hospitals
lie in the system's service area (claim `E-SC43-HOSPITALS-RICHMOND`): Bon Secours Richmond Community Hospital,
CJW Medical Center and the Medical College of Virginia Hospitals. The count is a floor: the Census geocoder does
not match the CMS address of the Richmond VA Medical Center, so the join does not place it.

## What the model does not show

In 2025 one basin of the Byrd Park Reservoir was out of service, which halved the main reservoir. The model keeps
the 69 Mgal of DPU, so the stored water lasts longer here than in fact while the basin is out of service. The
model also has no loss of power. In January 2025 the plant lost its power, and its generators can run only two
trains at about 50 Mgal a day. The model's production by hand is a share of the full 132 Mgal a day.
