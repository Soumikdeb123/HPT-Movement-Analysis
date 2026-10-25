# Yuchen private TennisCV integration (25 October 2026)

Source: private `tcv (2)/tcv/TennisCV`, supplied by Yuchen via the user.
The detector and `yuchen_player_tracker.py` are retained as supplied. The API
adapter calls the upstream distance-update and kinematic-filter routines rather
than approximating them with the previous speed-integration method.

## Active behavior

- YOLOv8x weights copied from the supplied package; startup script and defaults use x.
- Eight frames across the video; select the best full-court line-model match,
  retaining geometry and cross-frame consistency checks. Fixed camera required.
- Court run-off allowances match Yuchen: 4 m laterally, 8 m behind baseline.
- Distance: nine-detection moving-average displacement; >12 m/s jumps restart
  smoothing. Upstream may span missing observations when accumulating distance:
  this is not measured travel during an absence. Separate tracking IDs are never
  merged automatically.
- Kinematics: median size 5, 0.7 s quadratic Savitzky–Golay, split >5-frame gaps
  and >12 m/s jumps, trim one half-window per end. Removed the previous adapter's
  extra acceleration clipping/double trimming for this active engine.
- Force samples use these same speed/acceleration samples and entered mass.
  Force is not measured ground-reaction force or a fatigue score.
- Directional distance uses the same moving-average positions. Mean speed is the
  mean retained kinematic speed; do not divide cumulative distance by filtered
  duration because their coverage/smoothing differs.

## Identity continuity protections and limitations

The API still selects near/far athletes, unlike the standalone multi-player tool.
It no longer falls back to the opposite court half when a target is missing.
IDs expire after 30 elapsed frames (Yuchen default), including skipped frames.
Reappearance after that limit creates a separate ID. Results warn when multiple
segments exist and report coverage. Do not sum segments until identity is verified.
This is still geometric association, NOT appearance-based person re-identification;
same-half crossings or replacements can still switch IDs. Use uninterrupted,
fixed-camera singles clips for review and visually check annotated video.

## Run and outputs

Stop the old analysis process before running `backend/player_tracking/Start-LocalAnalysis.ps1`.
The script exits without replacing an existing server on port 8000; an old process
will continue to run old code/model until restarted. Restart the app and submit
a NEW analysis. No database or authentication configuration was changed.

Each job's results folder also includes `court_detection.jpg` for visual review.
Existing metric PNG/JSON/ZIP exports remain supported. The old n-model file is
retained for rollback but is not the startup default.
