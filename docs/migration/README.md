# Porting a scenario to the current language

Start with one run whose incident inputs and response choices are known. Write down which event reads each condition, which action changes each stock or state, and which later events depend on that change. Compare the old and new trajectories before changing assumptions. The [construct inventory](../scratch/rewrite/a5/migration-table.md) covers the old spellings and their replacements.

## Keep the cause of an event

The reservoir operator decides when the stored water and forecast meet the original conditions. The decision stage sets the gate. The spill pipe then reads the gate on every interval. A scheduled release at a time copied from a previous run would give the wrong result when the inflow or the operator's choice changes. In the shipped example, choosing OPEN at hour 40 produces 0.5 reservoir capacities of spill by hour 120. Choosing WAIT leaves all of that water in storage. [Runnable example](../examples/reservoir/README.md)

Use a trigger for a state-dependent start, an event parameter for a fact known at that start, and a stage delay for time that elapses after it. A duration tied to recognition or delivery should start from that event. A stock threshold should read the live stock. Use an outside input for a reported incident, then let inventories, queues, rates and decisions determine the response.

## Keep state changes atomic

A stage can update several related fields together. Starting another event with a zero-hour stage introduces a new round at the same clock time. Guards can observe the state between those rounds. For example, the water model records the loss of automatic controls and the associated repair work in one stage. Splitting those writes lets the completion guard see failed controls with an empty queue and restore service immediately. [Water recovery model](../scenarios/water_controls_wipe/water.scn)

Use a flow for work or material moving over time. Give it the original source, destination, request and applicable capacity. Preserve any coupling to crews, parts or supply. Keep each named value's physical scale when converting units, including the implicit one-unit scale. Keep the evidence for amounts and rates attached to the declarations that use it.

## Check a causal change

Run the baseline and candidate from separate processes with the same input choices. Compare start and completion times and read the affected stocks and rates before, during and after the event. Then change one input. Verify that a delayed input delays its dependants, a condition can prevent an event entirely, and the final balance includes exactly what moved. Check the public run command and the displayed unit and evidence for each reported value.

The reservoir comparison includes the operator's two choices. The water test supplies a second interruption in one run and omits it in another. It checks the additional work, restoration time, second laboratory clearance and the balance between identified, remaining and completed work. [Reservoir comparison](../scratch/rewrite/audit/reservoir-package-migration.md) · [Water tests](../scenarios/water_controls_wipe/tests/test_service_recovery.py)
