# Pixel movement effort demonstration

This prototype demonstrates a computable candidate for the undefined overall
effort requirement. It is NOT a validated measure of effort, energy, fatigue,
fitness or injury risk. No client approval is implied.

## Relationship to Floodlight

Reference: https://floodlight.readthedocs.io/en/latest/modules/models/kinetics.html
Floodlight estimates metabolic power from metre-based trajectories. We borrow
only the general sequence of trajectory -> velocity -> acceleration -> cumulative
summary. We do NOT implement its physiological model, copy its formula or claim
scientific equivalence. Our dimensionless normalisation and weights are arbitrary
demonstration parameters pending supervisor/client review. No new dependency is needed.

## Formula version pixel_motion_effort_v1

For each valid tracked interval, v is image displacement / elapsed time (px/s).
Smooth scalar speed with a five-sample moving median (shorter at boundaries).
Speeds below 3 px/s are treated as zero. Acceleration a is the difference between
smoothed scalar speeds divided by the interval-midpoint time difference (px/s^2).
The first interval in each continuous segment has acceleration set to zero.

E = sum[(dt / 1 second) * ((v / 100 px/s)^2 + 0.5 * abs(a) / 100 px/s^2)]

E is reported in arbitrary units (AU), has no fixed maximum, and is not a 0-100
score. Both speeding up and slowing down contribute through abs(a). Constant-speed
turning is not separately rewarded: this formula differentiates scalar speed,
not the velocity vector. Duration increases cumulative E.

Gaps longer than 0.25 seconds are excluded. Segments with fewer than two speed
intervals are excluded. No interpolation is performed across these gaps.
Insufficient/invalid data gives unavailable/null, not a misleading zero.
Zero is valid for a sufficiently observed stationary trajectory.

## Visible output and compatibility

The analysis engine now defaults primary result positions to image_pixels,
distance to px, speed to px/s and acceleration to px/s^2 even if calibration
succeeds. This uses actual image foot positions, not renamed metre values.
Court detection can still assist tracking. Prior court-derived results remain
under each player's courtMetrics in JSON (or null if unavailable).
The overallEffort API field remains for compatibility but its UI label is
Pixel effort index (demo). Its JSON includes the formula, parameters, component
contributions, valid duration, excluded time and cumulative samples.
CSV includes the summary value, AU, experimental status and limitation note.

Other movement metrics retain their pre-existing smoothing and gap behaviour;
their values need not reconstruct this separately calculated effort exactly.
Only effort currently applies the new explicit gap exclusion rule.

## Interpretation and limits

Compare only controlled recordings with the same camera, resolution, framing,
frame rate, tracking settings and duration, and even then only exploratorily.
Perspective changes apparent speed within one court. Bounding-box jitter and
identity switches can inflate the score; the filter does not solve those errors.
The five-sample smoothing window varies in time with frame rate. Re-encoding,
resizing and missing frames can change results. Export valid/excluded time when
reviewing a result. Do not use this score for training or health decisions.

## Run and demonstrate

Restart the analysis service after updating its Python files. Do not restart it
while someone is analysing a video: jobs are held in memory. Re-run Flutter to
apply the UI changes, and analyse a new video; old results are not recalculated.

From backend/player_tracking:

    .venv\Scripts\python.exe demo_pixel_effort.py
    .venv\Scripts\python.exe -m pytest tests -q

Synthetic expected examples: stationary 10s -> 0 AU; 100 px/s for 10s -> 10 AU;
200 px/s for 10s -> 40 AU; 100 px/s for 20s -> 20 AU. These illustrate the formula,
not real athlete performance or YOLO accuracy.

For the supervisor, demonstrate authorised video -> selected player -> pixel
trajectory and speed curve -> experimental effort value -> export JSON formula
and component contributions. Ask whether the final metric should represent
movement, perceived exertion or physiological load before selecting a final model.
