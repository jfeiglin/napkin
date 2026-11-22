# Water service recovery after a controls outage: Los Angeles, California

Water service, stored supplies and restoration work in Los Angeles, California after an observed controls outage.

The people that the water system of Los Angeles, California serves, the hospitals that it supplies and the businesses that need public water there.

Model revision `ecebc0523837d12d80aeed66389acac40fb3f3574ccc19d4857fd31807878a27`. Readings are instantaneous, without reporting lags. All times are in hours.

## early

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 0 | 1937783 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| person_days_lost | 2160 | 161481.917 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 2160 | 25.5342421 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.006257069 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.161481917 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | -1.16529009e-12 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |

## delayed_none

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 0 | 1937783 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| person_days_lost | 2160 | 161481.917 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 2160 | 25.5342421 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00625706901 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.161481917 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 1.90698773e-06 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |

## standard

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 0 | 1937783 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| person_days_lost | 2160 | 161481.917 | person*days | service_share, population_basis, ladwp_homes_population, counts_people_once, demand_basis, ladwp_demand, stored_water_bridges |
| unserved_volume | 2160 | 25.5342421 | Mgal | clearance, bulk_dependence, ladwp_bought, counts_stocks_flows, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.006257069 | USD2025_bn | activity_transfer, economy, demand_basis, ladwp_demand, counts_stocks_flows, stored_water_bridges, ladwp_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, ladwp_homes_population, counts_people_once, service_share, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, ladwp_homes_population, service_share, counts_people_once, clearance, bulk_dependence, ladwp_bought, stored_water_bridges, demand_basis, ladwp_demand, depth, room_identity, storage_hours, losses, ladwp_nameplate, manual, ladwp_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.161481917 | Mgal | counts_stocks_flows, ration_basis, population_basis, ladwp_homes_population, counts_people_once, service_share, demand_basis, ladwp_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, ladwp_hospitals_facilities, demand_basis, ladwp_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | -1.33582034e-12 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 3875566 | people | population_basis, ladwp_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |

## Evidence

- **activity_transfer** (source_transfer). Businesses keep a share of their activity through an outage and its recovery, and the recovery lasts a multiple of the outage. A Swedish survey of stated impacts gives both for a 24-hour outage by sector, from a third of activity kept and a recovery factor of 2.7 in food production to four fifths kept and 1.1 in information services. The scenario applies sector averages chosen within that range to US areas.
- **advisory** (assumption). When the usable stored water is used up, the pressure falls and the system issues a boil-water advisory, as a utility did after a loss of pressure in 2026. The advisory restricts the permitted use of the water, not its physical delivery.
- **bulk_dependence** (assumption). A system that sells water to another system of the place serves its own customers first and shares what is left among its buyers in proportion to what each asks, so a buyer loses water when its seller runs short. Sales to and purchases from systems outside the place are the stated amounts of each system.
- **clearance** (assumption). Once its controls and its sellers' controls are back, the system samples its water and a laboratory tests it before the advisory ends, which takes a stated time. The boil-water notices after a hurricane and a feeder-main repair ended one to two days after sampling.
- **constraint_basis** (assumption). While reserves and deliveries do not meet the critical need, the hospitals constrain their functions in proportion to the shortfall, as a hospital that suspended new surgeries and diverted ambulances during a water loss did. The model reports the facility_hours constrained and converts them into no clinical harm.
- **counts_people_once** (identity). Each person is served by one system of the place, and the people of two systems never overlap.
- **counts_stocks_flows** (identity). Water and money move once between stocks and tallies; the flows and the sum checks create and lose nothing.
- **demand_basis** (assumption). The default daily use and plant capacity of a system, which each system of a place replaces with its own figures. The range is one that a reader can explore, from a system that only sells water to the largest metropolitan systems; it is not a measured interval.
- **depth** (assumption). With its controls wiped, a plant loses the stated share of its production and the stated share of its delivery until operators run it by hand. Production loss and pumping loss are kept apart, because stored water bridges one but not the other. The shares are choices for each kind of system.
- **economy** (assumption). The area that each system serves has a value added an hour, of which a stated share needs public water. A stated share of lost output is made up over a stated time once the water is back. A regional study estimated about 15 billion dollars of product lost in a month without water in the national capital region, and a flood study found that the duration of water loss explained business interruption; neither gives these shares, which are choices for this scenario.
- **hospital_join** (assumption). A system supplies the hospitals of the CMS list whose geocoded address lies in its EPA service area. The template's one hospital stands for none: each system gives its own count.
- **keeps_count_limited** (identity). Work moves once from still to do to done. A crew hour is used once, on one system's work.
- **ladwp_bought** (assumption). Purchases from the Metropolitan Water District averaged 239,173 acre-feet a year in FY2020-FY2024 (213.520 MGD), at the family median ratio 1.54385: 329.6421 MGD. Metropolitan's recorded summer peak days for LADWP were about 292 to 409 MGD in 2021-2023.
- **ladwp_demand** (assumption). No source reports a highest day, so the peak use is the FY2020-FY2024 average potable demand, 466,866 acre-feet a year (416.792 MGD), times the family median ratio 1.54385: 643.4629 MGD. LADWP sells no water to other systems, so demand = 643.4629 / 1.05 = 612.8218 MGD.
- **ladwp_homes_population** (assumption). SDWIS federal data list 3,875,566 people served by LADWP (CA1910067), the system's own report through its state.
- **ladwp_hospitals_facilities** (assumption). The CMS hospital list gives 28 hospitals of the counted types whose geocoded address lies in the EPA service area of LADWP. The count is a floor: the Census geocoder does not match the CMS address of VA Greater Los Angeles Healthcare System, so the join does not place it.
- **ladwp_nameplate** (source). The maximum treatment capacity of the Los Angeles Aqueduct Filtration Plant, as LADWP stated in October 2023. It leaves out the wells and groundwater treatment plants, and the plant can treat only the aqueduct water and untreated purchased water that reach it.
- **ladwp_storage** (source). The in-city (local) reservoirs and tanks, 13,056 acre-feet (4,254.3 million gallons; the table prints 4,240). It leaves out the aqueduct reservoirs (310,542 acre-feet of untreated water) and four emergency reservoirs not in use. Los Angeles Reservoir is 78% of it.
- **ladwp_va_rate** (assumption). 3,875,566 people served times the 2024 GDP per resident of its county (Los Angeles County, California (06037): 1,002,965,029 thousand dollars and 9,757,179 people: 102,792.52 dollars a resident) times the price factor 1.026324, over 8,760 h: 46,674,233.55 USD2025/h.
- **losses** (assumption). A stated share of normal use leaks from the pipes whether or not customers are served. The share is a choice for this scenario.
- **manual** (assumption). Operators switch to manual controls after a delay and keep a stated share of normal production. Two New Jersey systems switched to manual controls within an hour of losing their remote monitoring and kept service for one and a half and two and a half days; a Utah system ran by hand for about three weeks. The production that manual operation achieves is not reported, so the share is chosen for each kind of system. Running by hand never cuts the production that still runs without the controls, so a plant on manual controls produces the larger of the manual share and what the wiped controls leave.
- **min_of_capacities** (assumption). Emergency water reaches people at the smallest of four capacities, which are the approved supply, the tankers, the receiving points and the staff who hand it out. A hospital after a hurricane received about 300,000 gallons a day by tanker, and one health system deployed 28 tankers of 6,000 gallons and two 20,000 gallon pumping tankers for five hospitals. The capacities of each tier are choices for this scenario.
- **population_basis** (assumption). The default people of a system's homes, which each system of a place replaces with the people that it reports to the national inventory. Each person is served by one system only.
- **priority_basis** (assumption). Hospitals get the emergency water first, then the households, each in proportion to their need. Who comes first is a policy choice for this scenario.
- **ration_basis** (source_transfer). State planning guidance uses one gallon for each person a day as the minimum emergency drinking water allocation. The scenario applies it to each person without normal service.
- **relief_by_response** (assumption). The faster responses bring more approved water, more tankers and more staff within hours; the delayed response takes two days and brings less. Each tier is a choice for this scenario.
- **room_identity** (identity). Usable storage is stored water or empty room for it: water that leaves the store makes room, and water that arrives fills it.
- **sees_controls_fail** (assumption). Operators see their controls stop responding as soon as the platform runs the attacker's commands. Two New Jersey systems received alarms within minutes of losing their remote monitoring.
- **service_incident** (assumption). The initial reported outage starts the response clock. A subsequent field report specifies the observed additional repair work in work hours.
- **service_share** (assumption). The share of the system's people without their normal service equals the share of normal use that the system cannot deliver, and their time without service adds up over everyone the system serves. A pressure zone or a priority customer can differ from this average.
- **start_basis** (assumption). Deliveries start a stated time after responders recognize the attack, which is a choice for this scenario.
- **storage_hours** (source_transfer). A planning case shows that about nine tenths of nominal storage is usable once dead storage and allocations to others are excluded, and a national survey puts the storage of large systems at about 17 to 18 hours of mean production. The scenario applies the usable share to each system's reported finished-water storage.
- **stored_water_bridges** (assumption). Customers get their normal use while usable stored water remains, less the share that the wiped pumps cannot move. Once the stored water is used up, they get only what is produced, bought or received from a seller. This is a reduced form of pressure-dependent delivery; the hydraulic form needs local calibration.
- **work** (assumption). The work to recover a system's controls has three parts that different crews do, which are rebuilding and verifying the controls, reconfiguring equipment in the field and installing replacements, and each part is a stated number of standardized work hours for one system of its kind. A SCADA system was restored in three days after one incident and a city recovered for 18 months after another; measured field repairs took tens of labour hours each. The hours by skill are choices for this scenario.
- **work_completion** (identity). Work moves once from still to do to done, at the pace that the crews give it. A part of the recovery is complete when no work of it is left, and the controls are back when every part is complete.
