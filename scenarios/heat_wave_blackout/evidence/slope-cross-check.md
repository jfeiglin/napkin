# SC41: measured check of the experienced-temperature slope

SC41 converts a group's experienced temperature (IET) into an equivalent outdoor temperature with one slope per group: how much the group's IET rises for each degree of outdoor airport temperature (OAT) under normal power. The slopes come from the method's own regression, Table S5 of the supplement to Gronlund et al. 2026 (claim `E-GRONLUND26-S5-PHX`): 0.208 °C per °C on average in Phoenix, and 0.257 for the reference profile. This note checks the average against measured personal temperatures.

## Data

- Personal temperatures: the DesignSafe 3HEAT collection "Hygrochron Temperature and Humidity iButton and Time Activity Diary - Wave 1" (doi:10.17603/ds2-rakj-a122), file `PhoenixAZ_iButton_Sensors.csv`. Phoenix participants wore iButton sensors that logged temperature every 5 minutes, 7 August to 23 September 2016.
- Outdoor temperatures: the Phoenix Sky Harbor series in the dataset of Wright et al. 2020 (doi:10.17632/t9cgvfd572.1), file `skyharbor.csv`, every 5 minutes from 21 August to 19 September 2016, local time (MST) per that dataset's description.

Both files were saved by a browser search for this scenario and kept outside the repository.

## Method

1. For each participant and day, the mean of the sensor temperatures, kept when the day has at least 240 of 288 readings.
2. For each day, the mean airport temperature, kept when the day has at least 240 readings.
3. The two joined by date. The slope is fitted within participants (each participant's own mean removed), the same quantity as the regression's average slope. A pooled slope and one slope per participant are also computed.

Temperatures stay in °F; a slope in °F per °F equals the slope in °C per °C.

## Result

| Quantity | Value |
|---|---|
| Participants, person-days | 52, 1,124 |
| Days | 21 August to 19 September 2016 |
| Daily mean airport temperature | 28.5 to 35.1 °C |
| Slope within participants | 0.189 (standard error 0.024) |
| Pooled slope | 0.148 |
| Slopes of single participants | median 0.146; middle half -0.013 to 0.374; range -0.656 to 0.998 |

The measured slope within participants, 0.189, is 9% lower than the regression's Phoenix average of 0.208. The difference is inside the 30% that the SC41 plan set as the point at which the slopes would be reviewed, so SC41 uses the Table S5 slopes.

The slopes of single participants spread widely, and about a quarter are at or below zero. A conversion that divides a person's temperature rise by that person's own slope therefore gives extreme or undefined equivalent temperatures for some people. One slope per group does not.

## Limits

The days are late summer, not an extreme heat wave, and the power is on. The participants are volunteers. The standard error treats person-days as independent; it does not allow for correlation between a participant's days. The time zone of the airport series follows its dataset's description.
