# Water service recovery after a controls outage: Asheville, North Carolina

Water service, stored supplies and restoration work in Asheville, North Carolina after an observed controls outage.

The people that the water system of Asheville, North Carolina serves, the hospitals that it supplies and the businesses that need public water there.

Model revision `d03419f1412b829bd0865cdd4f9b12cfe6a20737ff677fda23566e1a7e6e949d`. Readings are instantaneous, without reporting lags. All times are in hours.

## early

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## delayed_none

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |

## standard

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## support_single

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_single_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 32 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0032 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 8 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 128 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0128 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 64 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0064 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 0 | 78715.5 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 6559.62 | person*days | service_share, population_basis, asheville_homes_population, counts_people_once, demand_basis, asheville_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.996842 | Mgal | clearance, bulk_dependence, asheville_bought, counts_stocks_flows, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000188295 | USD2025_bn | activity_transfer, economy, demand_basis, asheville_demand, counts_stocks_flows, stored_water_bridges, asheville_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, asheville_homes_population, counts_people_once, service_share, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, asheville_homes_population, service_share, counts_people_once, clearance, bulk_dependence, asheville_bought, stored_water_bridges, demand_basis, asheville_demand, depth, room_identity, storage_hours, losses, asheville_nameplate, asheville_sold, manual, asheville_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00655963 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, asheville_hospitals_facilities, demand_basis, asheville_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 157431 | people | population_basis, asheville_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 7 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, asheville_homes_population, counts_people_once, service_share, demand_basis, asheville_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## Evidence

- **activity_transfer** (source_transfer). Businesses keep a share of their activity through an outage and its recovery, and the recovery lasts a multiple of the outage. A Swedish survey of stated impacts gives both for a 24-hour outage by sector, from a third of activity kept and a recovery factor of 2.7 in food production to four fifths kept and 1.1 in information services. The scenario applies sector averages chosen within that range to US areas.
- **advisory** (assumption). When the usable stored water is used up, the pressure falls and the system issues a boil-water advisory, as a utility did after a loss of pressure in 2026. The advisory restricts the permitted use of the water, not its physical delivery.
- **asheville_bought** (source). Asheville bought no water in 2025: its four purchase connections (Hendersonville, Black Mountain, Weaverville, Woodfin) are for emergencies and carried nothing.
- **asheville_demand** (assumption). Highest maximum day of 2025, 26.48 Mgal/day (January), is 1.1689 times the 2025 total demand of 22.6544. Less the 2025 sales of 1.1632 at the same ratio (1.3596) and divided by 1.05: (26.48 - 1.3596) / 1.05 = 23.9242 Mgal/day. The higher 2022 day (29.01 Mgal/day) is left out because the 2022 plan attributes it to 27 main breaks during a freeze.
- **asheville_homes_population** (assumption). SDWIS federal data list 157,431 people served by Asheville (NC0111010), the system's own report through its state.
- **asheville_hospitals_facilities** (assumption). The CMS hospital list gives 2 hospitals of the counted types whose geocoded address lies in the EPA service area of Asheville.
- **asheville_nameplate** (source). Sum of the permitted capacities of the three plants in the 2025 plan: North Fork WTP 31.5, Mills River WTP 7.5 and William DeBruhl WTP 5.0 Mgal/day.
- **asheville_sold** (assumption). Regular sales in 2025 to Black Mountain (0.7057), Woodfin (0.3136) and Biltmore Forest (0.1439), 1.1632 Mgal/day in all, none of them in the scenario; at the peak ratio 1.1689: 1.3596 Mgal/day. The contracts total 2.15 Mgal/day.
- **asheville_storage** (source). Finished water storage capacity reported in the 2025 plan, 27.3560 Mgal (the 15 Mgal of off-stream raw water storage is not counted).
- **asheville_va_rate** (assumption). 157,431 people served times the 2024 GDP per resident of its county (Buncombe County, North Carolina (37021): 21,262,054 thousand dollars and 279,210 people: 76,150.76 dollars a resident) times the price factor 1.026324, over 8,760 h: 1,404,575.35 USD2025/h.
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
- **losses** (assumption). A stated share of normal use leaks from the pipes whether or not customers are served. The share is a choice for this scenario.
- **manual** (assumption). Operators switch to manual controls after a delay and keep a stated share of normal production. Two New Jersey systems switched to manual controls within an hour of losing their remote monitoring and kept service for one and a half and two and a half days; a Utah system ran by hand for about three weeks. The production that manual operation achieves is not reported, so the share is chosen for each kind of system. Running by hand never cuts the production that still runs without the controls, so a plant on manual controls produces the larger of the manual share and what the wiped controls leave.
- **min_of_capacities** (assumption). Emergency water reaches people at the smallest of four capacities, which are the approved supply, the tankers, the receiving points and the staff who hand it out. A hospital after a hurricane received about 300,000 gallons a day by tanker, and one health system deployed 28 tankers of 6,000 gallons and two 20,000 gallon pumping tankers for five hospitals. The capacities of each tier are choices for this scenario.
- **population_basis** (assumption). The default people of a system's homes, which each system of a place replaces with the people that it reports to the national inventory. Each person is served by one system only.
- **priority_basis** (assumption). Hospitals get the emergency water first, then the households, each in proportion to their need. Who comes first is a policy choice for this scenario.
- **ration_basis** (source_transfer). State planning guidance uses one gallon for each person a day as the minimum emergency drinking water allocation. The scenario applies it to each person without normal service.
- **relief_by_response** (assumption). The faster responses bring more approved water, more tankers and more staff within hours; the delayed response takes two days and brings less. Each tier is a choice for this scenario.
- **removal_basis** (assumption). After recognition, responders take a stated time to find and remove the attacker's credential and rebuild the platform's access controls. A regional system restored its SCADA in three days and kept its shared connections isolated for more than two months; a city took three weeks of manual operation.
- **response_basis** (assumption). Operators see their controls fail at once, but recognizing a cyber attack on the shared platform takes the integrator and the state's responders a stated time. One New Jersey system's vendor identified a potential cyberattack twelve hours after the alarm, and a state cyber centre arrived the next morning.
- **room_identity** (identity). Usable storage is stored water or empty room for it: water that leaves the store makes room, and water that arrives fills it.
- **sees_controls_fail** (assumption). Operators see their controls stop responding as soon as the platform runs the attacker's commands. Two New Jersey systems received alarms within minutes of losing their remote monitoring.
- **service_incident** (assumption). The initial reported outage starts the response clock. A subsequent field report specifies the observed additional repair work in work hours.
- **service_share** (assumption). The share of the system's people without their normal service equals the share of normal use that the system cannot deliver, and their time without service adds up over everyone the system serves. A pressure zone or a priority customer can differ from this average.
- **start_basis** (assumption). Deliveries start a stated time after responders recognize the attack, which is a choice for this scenario.
- **storage_hours** (source_transfer). A planning case shows that about nine tenths of nominal storage is usable once dead storage and allocations to others are excluded, and a national survey puts the storage of large systems at about 17 to 18 hours of mean production. The scenario applies the usable share to each system's reported finished-water storage.
- **stored_water_bridges** (assumption). Customers get their normal use while usable stored water remains, less the share that the wiped pumps cannot move. Once the stored water is used up, they get only what is produced, bought or received from a seller. This is a reduced form of pressure-dependent delivery; the hydraulic form needs local calibration.
- **support_exercise** (assumption). The exercise sends batches of regional casework to one emergency water support office. While cases wait, a share of the region's delivery capacity is reserved for them. The office completes requests with water from the shared supply. Containment filters subsequent notices.
- **work** (assumption). The work to recover a system's controls has three parts that different crews do, which are rebuilding and verifying the controls, reconfiguring equipment in the field and installing replacements, and each part is a stated number of standardized work hours for one system of its kind. A SCADA system was restored in three days after one incident and a city recovered for 18 months after another; measured field repairs took tens of labour hours each. The hours by skill are choices for this scenario.
- **work_completion** (identity). Work moves once from still to do to done, at the pace that the crews give it. A part of the recovery is complete when no work of it is left, and the controls are back when every part is complete.
