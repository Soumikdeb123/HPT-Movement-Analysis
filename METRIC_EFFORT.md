# Overall effort: external movement load (experimental v1)

Question: how much movement was visible on the selected track during usable metric time? Not a 0–100 score, a fatigue estimate, energy expenditure or a comparison of athlete fitness.

For each filtered sample use rate = (speed / 2 m/s)^2 + 0.5 * abs(tangential acceleration) / (2 m/s²). Accumulate the trapezoidal mean rate times interval duration in seconds (one reference second = one AU at unit rate). Keep positive acceleration and braking contributions separately. A constant 2 m/s for 10 usable seconds gives 10 AU. Doubling the duration doubles the score. The reference scales and equal acceleration/braking weighting are team-selected demonstration parameters, not thresholds validated for tennis.

This extends our historical pixel demo without mixing coordinate systems. Floodlight's [kinematics documentation](https://floodlight.readthedocs.io/en/latest/modules/models/kinematics.html) provides a conceptual reference for frame-wise movement measures; this formula is not from Floodlight, and no new package is required.

Use the existing court calibration gate and filtered per-frame series. Include adjacent frames only within the same segment and track; the upstream filter may interpolate short detection gaps. Omit long gaps and trimmed edges. Missing data is not zero effort. No body mass is required. A constant-speed turn is not captured as extra tangential acceleration; the existing direction-change metric remains separate.

JSON includes method, total AU, three component totals, valid seconds and AU per valid minute. Compare similar footage and coverage; use the valid-minute rate to distinguish intensity from duration. Before freezing v1, review a quiet, steady and stop–start drill at similar durations with the coach; repeat across viewpoints and inspect ranking sensitivity to reference values and weights. Keep versioned results if parameters change.
