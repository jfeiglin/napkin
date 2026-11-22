# Water service recovery after a controls outage: Jackson, Mississippi

Water service, stored supplies and restoration work in Jackson, Mississippi after an observed controls outage.

The people that the water system of Jackson, Mississippi serves, the hospitals that it supplies and the businesses that need public water there.

Model revision `00a7b84b1ecf327e398d582f1fad57fe4fe1d3e944d785992f9a23496da30c2c`. Readings are instantaneous, without reporting lags. All times are in hours.

## early

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 29269.9 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 8.41929 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000804866 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## delayed_none

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 200251 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 57.6009 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00552529 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.0623823 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |

## standard

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 130949 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 37.6664 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00360826 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## support_single

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 130949 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 37.6664 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00360826 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_single_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 29269.9 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 8.41929 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000804866 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 130949 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 37.6664 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00360826 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 29269.9 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 8.41929 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000804866 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 32 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0032 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 130949 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 37.6664 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00360826 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 8 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 128 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0128 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 29269.9 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 8.41929 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000804866 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 64 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0064 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 130949 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 37.6664 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.00360826 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 0 | 94836.5 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 0 | 0.5 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 720 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 29269.9 | person*days | service_share, population_basis, jxn_water_homes_population, counts_people_once, demand_basis, jxn_water_demand, stored_water_bridges |
| unserved_volume | 2160 | 8.41929 | Mgal | clearance, bulk_dependence, counts_stocks_flows, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 0.000804866 | USD2025_bn | activity_transfer, economy, demand_basis, jxn_water_demand, counts_stocks_flows, stored_water_bridges, jxn_water_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, jxn_water_homes_population, counts_people_once, service_share, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, clearance, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, jxn_water_homes_population, service_share, counts_people_once, clearance, bulk_dependence, stored_water_bridges, demand_basis, jxn_water_demand, depth, room_identity, storage_hours, losses, jxn_water_nameplate, manual, jxn_water_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00790304 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, jxn_water_hospitals_facilities, demand_basis, jxn_water_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 189673 | people | population_basis, jxn_water_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 7 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | constraint_basis, counts_stocks_flows, ration_basis, population_basis, jxn_water_homes_population, counts_people_once, service_share, demand_basis, jxn_water_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

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
- **jxn_water_demand** (assumption). No source reports a highest day. The average production into the distribution system from July 2025 to June 2026 is 37.106 MGD (four quarterly means weighted by their days). Times the family median ratio 1.54385 that is a peak of 57.2860 MGD; there are no sales, so demand is 57.2860 / 1.05 = 54.5581 MGD.
- **jxn_water_homes_population** (assumption). SDWIS federal data list 189,673 people served by JXN Water (MS0250008), the system's own report through its state.
- **jxn_water_hospitals_facilities** (assumption). The CMS hospital list gives 4 hospitals of the counted types whose geocoded address lies in the EPA service area of JXN Water. The count is a floor: the Census geocoder does not match the CMS addresses of G. V. (Sonny) Montgomery VA Medical Center (Jackson), St Dominic-Jackson Memorial Hospital, so the join does not place them.
- **jxn_water_nameplate** (source). Rated capacities in the 2021 state survey: O.B. Curtis 25 MGD for each of its conventional and membrane sides, and J.H. Fewell 20 MGD, the maximum that the state set. In 2021 the state credited only 53.6 MGD for the filters and trains then in service.
- **jxn_water_storage** (source). Storage that the 2021 state survey counts: 13.8 MG at J.H. Fewell, the 10 MG clearwell at O.B. Curtis and 7.75 MG of elevated tanks. It leaves out 2.2 MG of tanks that were offline or empty.
- **jxn_water_va_rate** (assumption). 189,673 people served times the 2024 GDP per resident of its county (Hinds County, Mississippi (28049): 15,444,192 thousand dollars and 211,975 people: 72,858.55 dollars a resident) times the price factor 1.026324, over 8,760 h: 1,619,073.64 USD2025/h.
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
