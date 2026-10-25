# Metric report integration — 25 October 2026

Court-line selection uses Yuchen Wu's `court_detector.py` from branch
`Added-functions-Current-speed,-Current-acceleration,-Current-deceleration`,
commit `a6a30fc` (the latest version found during this review).
The integrated `yuchen_court_detector.py` preserves subpixel corner coordinates;
selection logic is unchanged. `court_geometry.py` additionally checks geometry
and repeatability. It deliberately rejects implausible calibration instead of
displaying pixels as metres. A newer unpublished detector must be supplied before
it can be compared or integrated.

## Reports

Restart the analysis server and analyse a video again. Existing completed jobs
are not retroactively converted. Each job saves to `runtime/<analysis-id>/results/`:

- `movement_trajectories.png`: court paths and cumulative screened distance.
- `speed_deceleration.png`: speed and signed acceleration, braking-event bands.
- `analysis.json`: numeric results and validation notes.
- `reports.zip`: the two images and JSON (not the original athlete video).
- `annotated.mp4`: existing annotated video output.

The app shows the metric images, supports tap-to-zoom and ZIP export. Pixel speed
and acceleration plots are hidden. If calibration fails, the saved images explain
why metric reports are unavailable; they do not contain fabricated metric curves.
Current analysis selects one near/far athlete, so a single-player report is expected.
The supplied two-player screenshots came from a different standalone workflow.

Distance is integrated from the same screened velocity series as the metric cards.
Gaps are not joined or integrated. Braking thresholds (-2 m/s² for >=0.2 s,
high intensity >=3 m/s² magnitude) are prototype settings, not validated fatigue
criteria. Horizontal chart axes use seconds for easier interpretation.

The force–speed scatter requires accepted metric tracking and entered body mass
(20–250 kg). It estimates tangential net force as mass × rate of change of speed,
not ground-reaction force or fatigue. Without these inputs the existing card
explains why the plot is unavailable. Do not disable calibration checks to force it
to display.

The reviewed 150.9-second video previously failed calibration: the raw detector
selected roof/stand lines. Repeating the same source code cannot fix those lines.
Use the same video as Yuchen's approximately 22-second reference for comparison,
or provide his newer detector. Correct metric output on that specific failed video
remains unverified until a valid court mapping is available.
