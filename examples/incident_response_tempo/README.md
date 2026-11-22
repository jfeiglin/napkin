# Attack tempo and incident response

The first attempt at hour zero admits an incident and starts the detection clock. Until containment, each attempt adds two hours of repair work. At detection one crew begins clearing the queue at one work-hour per hour. Containment blocks subsequent attempts, including one arriving exactly when containment takes effect. The crew keeps working until the queue is empty.

Four fixed-cadence runs change two clocks independently. The 24-hour horizon includes attempts at hour 24. Counts and times are illustrative assumptions for a tabletop exercise.

| Run | Attempt interval | Detection | Containment | Admitted | Blocked | Work left at containment |
|---|---:|---:|---:|---:|---:|---:|
| `standard` | 4 h | 3 h | 9 h | 3 | 4 | 1 h |
| `rapid_response` | 4 h | 1 h | 3 h | 1 | 6 | 0 h |
| `frequent_attempts` | 1 h | 3 h | 9 h | 9 | 16 | 12 h |
| `frequent_with_rapid_response` | 1 h | 1 h | 3 h | 3 | 22 | 4 h |

For hourly attempts and standard response, the first three attempts have already generated six work-hours when the defenders detect the incident. The attempt at hour three adds another two. By containment at hour nine, nine attempts have generated eighteen work-hours and the crew has completed six. The twelve hours left in the queue clear by hour 21.

Two further runs explicitly couple the next attempt to the defender’s recovery. An admitted attempt starts a recovery event that waits for the repair queue to empty. Only then does the one-hour return clock start. A blocked attempt creates no work and ends this sequence.

| Run | Repair finishes | Attempts arrive | Result |
|---|---|---|---|
| `recovery_linked` | Hours 5 and 8 | Hours 0, 6 and 9 | Two admitted. Containment blocks the third at hour 9. |
| `recovery_linked_rapid` | Hour 3 | Hours 0 and 4 | One admitted. Containment blocks the second at hour 4. |

Changing the work per incident from two hours to three shifts the standard sequence to hours 0, 7 and 11. Those timestamps follow from the repair trajectory.

Run from the repository root to inspect the trajectory.

```sh
python -m napkin run examples/incident_response_tempo --run frequent_attempts \
  --value attack.admitted,attack.blocked,response.phase,queue.pending,queue.completed \
  --at 0h,3h,9h,21h,24h
```

This example uses fixed-cadence or recovery-linked attempts, deterministic detection and containment delays, full containment and one repair crew. Its counts describe incident workload for a hypothetical system. The four historical catalogue packages have their own event rules and calibration.
