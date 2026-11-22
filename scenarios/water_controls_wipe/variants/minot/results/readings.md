# Water service recovery after a controls outage: Minot, North Dakota

Water service, stored supplies and restoration work in Minot, North Dakota after an observed controls outage.

The people that the water systems of Minot, North Dakota serve, the hospitals that those systems supply and the businesses that need public water there.

Model revision `8692394439a225afa3e1c63189364877330a050c593d1214db897b987848e2f9`. Readings are instantaneous, without reporting lags. All times are in hours.

## early

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.9891e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## delayed_none

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, start_basis, priority_basis, support_exercise |

## standard

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 0 | 1 | support_exercise |
| support.filtered | 0 | 0 | 1 | support_exercise |
| support.waiting | 0 | 0 | work_h | support_exercise |
| support.completed | 0 | 0 | work_h | support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 0 | 1 | support_exercise |
| support.filtered | 2160 | 0 | 1 | support_exercise |
| support.waiting | 2160 | 0 | work_h | support_exercise |
| support.completed | 2160 | 0 | work_h | support_exercise |
| support.delivered | 2160 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, min_of_capacities, relief_by_response, start_basis, priority_basis, support_exercise |

## support_single

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_single_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.9891e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_daily_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 32 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0032 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 8 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 128 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0128 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_frequent_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.9891e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 4 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 64 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0064 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.98911e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 6 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 2 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 96 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0096 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

## support_recovery_rapid

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| person_days_lost | 0 | 0 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 0 | 0 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 0 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 0 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 0 | 0 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 0 | 34120.1 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 0 | 0 | people | advisory, counts_people_once |
| restored_share | 0 | 0.3 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 0 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 0 | 1200 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 0 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 0 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 0 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 0 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 0 | 0 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 0 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 0 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 0 | 0 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| person_days_lost | 2160 | 1421.67 | person*days | service_share, population_basis, minot_homes_population, counts_people_once, demand_basis, minot_demand, stored_water_bridges |
| unserved_volume | 2160 | 0.297561 | Mgal | refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, counts_stocks_flows, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage |
| rework_caused | 2160 | 0 | work_h | keeps_count_limited, service_incident |
| deaths | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service of a given depth and length converts into deaths. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| casualties | 2160 | Not estimated (The reviewed evidence does not establish how a loss of water service converts into serious harm. The model reports the hospitals' hours short of water instead. This outcome is not zero.) |  |  |
| economic_loss | 2160 | 3.9891e-05 | USD2025_bn | activity_transfer, economy, demand_basis, minot_demand, naws_demand, counts_stocks_flows, stored_water_bridges, minot_va_rate, naws_va_rate |
| people_interrupted_now | 2160 | 0 | people | population_basis, minot_homes_population, counts_people_once, service_share, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| people_under_advisory | 2160 | 0 | people | advisory, counts_people_once |
| restored_share | 2160 | 1 | fraction | population_basis, minot_homes_population, service_share, counts_people_once, refill_basis, tie_weight, bulk_dependence, minot_to_naws_capacity, clearance, minot_bought, naws_bought, stored_water_bridges, demand_basis, minot_demand, naws_demand, depth, room_identity, storage_hours, losses, minot_nameplate, naws_nameplate, minot_sold, naws_sold, manual, minot_storage, naws_storage, counts_stocks_flows |
| emergency_water_deficit | 2160 | 0.00142167 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |
| hospital_hours_constrained | 2160 | 0 | facility_hours | constraint_basis, hospital_join, minot_hospitals_facilities, demand_basis, minot_demand, stored_water_bridges, start_basis |
| work_remaining | 2160 | 0 | work_h | work_completion, keeps_count_limited, work, sees_controls_fail |
| people_followed | 2160 | 48743 | people | population_basis, minot_homes_population, counts_people_once |
| wider_loss | 2160 | Not estimated (Effects on other areas need a model of trade, inventories and substitution between areas that this scenario does not hold. This outcome is not zero.) |  |  |
| people_beyond_week | 2160 | Not estimated (The model follows the water that each system delivers, not each person's own days without it, so it cannot say how many people went a week or more without a break. This outcome is not zero.) |  |  |
| support.accepted | 2160 | 1 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.filtered | 2160 | 7 | 1 | service_incident, response_basis, removal_basis, support_exercise |
| support.waiting | 2160 | 0 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.completed | 2160 | 16 | work_h | service_incident, response_basis, removal_basis, support_exercise |
| support.delivered | 2160 | 0.0016 | Mgal | counts_stocks_flows, ration_basis, population_basis, minot_homes_population, counts_people_once, service_share, demand_basis, minot_demand, stored_water_bridges, service_incident, min_of_capacities, relief_by_response, start_basis, priority_basis, response_basis, removal_basis, support_exercise |

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
- **losses** (assumption). A stated share of normal use leaks from the pipes whether or not customers are served. The share is a choice for this scenario.
- **manual** (assumption). Operators switch to manual controls after a delay and keep a stated share of normal production. Two New Jersey systems switched to manual controls within an hour of losing their remote monitoring and kept service for one and a half and two and a half days; a Utah system ran by hand for about three weeks. The production that manual operation achieves is not reported, so the share is chosen for each kind of system. Running by hand never cuts the production that still runs without the controls, so a plant on manual controls produces the larger of the manual share and what the wiped controls leave.
- **min_of_capacities** (assumption). Emergency water reaches people at the smallest of four capacities, which are the approved supply, the tankers, the receiving points and the staff who hand it out. A hospital after a hurricane received about 300,000 gallons a day by tanker, and one health system deployed 28 tankers of 6,000 gallons and two 20,000 gallon pumping tankers for five hospitals. The capacities of each tier are choices for this scenario.
- **minot_bought** (source). Minot produces all its water from its own wells and plant. Lake water through NAWS had not begun in the period: the Biota plant was not complete in May 2026.
- **minot_demand** (assumption). The highest day that a source reports is 13 million gallons, the lower end of the 13 to 14 million gallons a day that peak summer use often reaches (2020). The 2024 pumped average is 6.6896 million gallons a day, so the peak ratio is 1.9433. Less the sales to NAWS at that ratio (0.8083 x 1.9433 = 1.5708) and about 0.717 million gallons a day to North Prairie Rural Water, over 1.05: (13 - 1.5708 - 0.717) / 1.05 = 10.2021.
- **minot_homes_population** (assumption). SDWIS federal data list 48,743 people served by Minot (ND5100660), the system's own report through its state.
- **minot_hospitals_facilities** (assumption). The CMS hospital list gives 1 hospital of the counted types whose geocoded address lies in the EPA service area of Minot.
- **minot_nameplate** (source). The rated capacity of the one Minot water treatment plant, 18 million gallons a day, as the Department of Water Resources reported in 2023 and again in January 2025. The plant has only ground water until lake water arrives, and the wells give about 17 million gallons a day.
- **minot_sold** (assumption). About 717,000 gallons a day to North Prairie Rural Water, which the NAWS flow table counts inside the Minot estimated peak usage; it is taken as the peak-day sale. North Prairie is outside the scenario, and the rate memo of November 2025 bills its NAWS connections under the city rate.
- **minot_storage** (source). The 2014 master plan gives 12.5 million gallons in the city reservoirs and towers; the 1.5 million-gallon southwest tower went online in 2022, so 12.5 + 1.5 = 14.0. The current city page lists three 3-million-gallon ground reservoirs and five elevated tanks, which with the tank volumes of the 2014 plan and the 2018 and 2021 reports also gives 14.0 million gallons.
- **minot_to_naws_capacity** (source). The daily amounts of Amendment 2 to the interim water supply agreement, for all NAWS customers, total 1,439,300 gallons a day. The NAWS pumps at the High Service Pump Station can move 4,000 gallons a minute (5.76 million gallons a day), but they also carry the city's own water through the NAWS meter, so the contract total is the capacity for the NAWS customers.
- **minot_va_rate** (assumption). 48,743 people served times the 2024 GDP per resident of its county (Ward County, North Dakota (38101): 5,093,673 thousand dollars and 68,427 people: 74,439.52 dollars a resident) times the price factor 1.026324, over 8,760 h: 425,105.14 USD2025/h.
- **naws_bought** (source). NAWS buys all its water from Minot, which is in the scenario (the tie). No lake water flowed in the period.
- **naws_demand** (source). NAWS has no retail customers of its own: it delivers to nine contract customers and to connections that the City of Minot bills.
- **naws_nameplate** (source). NAWS had no treatment plant in service in the period. Phase I of the Biota plant was still under construction in May 2026, with substantial completion expected at the end of August 2026, and it only pretreats lake water before final treatment at the Minot plant.
- **naws_sold** (assumption). The nine NAWS contract customers used 295,837,470 gallons in 2024, 0.8083 million gallons a day. No source reports a NAWS highest day, so the family median ratio 1.54385 applies: 0.8083 x 1.54385 = 1.2479.
- **naws_storage** (source). Sum of the NAWS tanks with a reported volume: Lansford 4.5, Bottineau 3 and the Kenmare tower 1 million gallons, 8.5 in all. It is a lower bound: the tanks on Speedway Hill at Minot and near Berthold have no reported volume.
- **naws_va_rate** (assumption). NAWS (ND5101687) is a wholesale system with no retail customers: SDWIS lists 0 people, so its own homes and businesses add no value added; its buyers carry theirs.
- **population_basis** (assumption). The default people of a system's homes, which each system of a place replaces with the people that it reports to the national inventory. Each person is served by one system only.
- **priority_basis** (assumption). Hospitals get the emergency water first, then the households, each in proportion to their need. Who comes first is a policy choice for this scenario.
- **ration_basis** (source_transfer). State planning guidance uses one gallon for each person a day as the minimum emergency drinking water allocation. The scenario applies it to each person without normal service.
- **refill_basis** (assumption). A buyer asks its sellers for what it needs, plus the water that refills its usable storage over a stated time while its storage has room. The refill time is a choice.
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
- **tie_weight** (assumption). A buyer with two sellers asks each in proportion to the capacity of its connection. When a seller can fill only part of its connection, the buyer asks the others for the part that it cannot fill, up to their capacities.
- **work** (assumption). The work to recover a system's controls has three parts that different crews do, which are rebuilding and verifying the controls, reconfiguring equipment in the field and installing replacements, and each part is a stated number of standardized work hours for one system of its kind. A SCADA system was restored in three days after one incident and a city recovered for 18 months after another; measured field repairs took tens of labour hours each. The hours by skill are choices for this scenario.
- **work_completion** (identity). Work moves once from still to do to done, at the pace that the crews give it. A part of the recovery is complete when no work of it is left, and the controls are back when every part is complete.
