# Local integration — 25 October 2026

## What is integrated

This working copy retains Suchang's UI, privacy gate and authentication flow,
Hanyu's upload/job/video integration, and the CSV/JSON/video export workflow.
No heatmap has been reintroduced. No GitHub branch is changed by this local integration.

Source contributions reviewed:

| Contributor / branch | Revision | Integration |
| --- | --- | --- |
| Yuchen — Calculation-of-actual-distances-in-meters | 8a59f8d | Physical court dimensions and metre-coordinate approach |
| Yuchen — Added-functions-Current-speed,-Current-acceleration,-Current-deceleration | a6a30fc | Baseline/service-line homography and median/Savitzky–Golay kinematics approach |
| Wentao — Add-acceleration | e7ef0ed | Interactive acceleration chart, adapted to actual API samples instead of demo data |
| Soumik — feature/soumik-ios-kinematics-integration | 2863992 | Kinematics/deceleration integration concepts; its old app shell is not copied over the current UI |
| Hanyu — feature/hanyu-force-velocity | fb3350b | API/video validation, mass input, force–velocity model/chart and integration foundation |

The source branch named iOS did not itself establish tested Apple-device support.
This integration adds platform-aware endpoints and an iOS local-network usage
description/limited ATS local-network permission. Actual iOS execution remains unverified.

## Important behaviour changes

1. `backend/player_tracking/hpt_tracking/metric_motion.py` owns a single screened
   time series. Metre-based speed, signed acceleration, positive deceleration peaks,
   braking events and optional estimated force use this same series.
2. There is no fixed 0.08 m-per-frame deadband. At 30/60 fps that old rule could
   erase genuine slow movement. A 2 m/s synthetic trajectory now remains 2 m/s
   at 15, 30 and 60 fps.
3. Coordinates must be finite and frames strictly increasing. Gaps over 0.2 s
   and raw motion over 12 m/s split the series before filtering. The 0.7 s
   centred quadratic Savitzky–Golay filter follows a five-frame median filter;
   two half-windows are trimmed because acceleration uses a second filter.
   Estimates over 12 m/s or |acceleration| >15 m/s² are withheld. These limits
   are prototype quality controls, not validated physiological limits.
4. Distances integrate speed (and absolute axis velocities) over adjacent
   retained samples only. They EXCLUDE gaps and filter edges. The UI shows
   valid calculation duration and excluded candidate samples. These are
   screened-interval distances, NOT a complete-session total. They may be
   lower than earlier results; do not compare values without their coverage.
5. Braking events: signed acceleration <= -2 m/s² for >=0.2 s continuously;
   a peak >=3 m/s² gets an experimental high-intensity flag in JSON. Rejected
   samples cannot join two events. Thresholds require client agreement.
6. Force is `mass × rate of change of scalar speed`. It omits turning-related
   normal acceleration. It is NOT ground-reaction force, metabolic effort,
   a standardized athlete force–velocity profile, or fatigue. Overall effort
   remains unavailable until the client defines and validates it. The old
   pixel-effort demo source is retained for reference, not presented as a
   verified metre-based workload score.
7. Mass is optional. Leave blank for normal motion analysis. Enter 20–250 kg
   for the experimental force plot; invalid nonempty input is flagged. The
   privacy notice describes sending optional mass to the configured server.
8. Court detection now uses Yuchen's near-baseline/service-line intersections,
   not arbitrary Hough segment endpoints. The near service line is 6.40 m
   from the net; the doubles court is 10.97 × 23.77 m. Low-confidence/short
   or implausible metric tracks fall back to explicitly labelled pixel data.
9. Speed and signed acceleration plots show actual samples, preserve breaks,
   label the correct units, and support tapping to inspect a sample. CSV now
   also includes timestamped motion/force samples and braking-event peaks;
   JSON preserves the complete nested result. Video export remains available.

## Start on the existing Windows machine

Use THREE terminals. Stop an old analysis server with Ctrl+C in its own terminal
before restarting; otherwise it will keep running the old Python code.

Terminal 1 — existing authentication/database configuration (no reinitialisation):

```powershell
cd C:\Users\admin\Desktop\github\project\code
powershell -NoProfile -ExecutionPolicy Bypass -File .\backend\auth\scripts\Start-LocalAuth.ps1
```

If the existing database cannot be found, supply its actual folder using
`-DatabaseDirectory`. Do not create a new database or overwrite `my.ini`.
This integration does not change MySQL, `.env`, passwords or auth startup.

Terminal 2 — analysis service (keep open):

```powershell
cd C:\Users\admin\Desktop\github\project\code
powershell -NoProfile -ExecutionPolicy Bypass -File .\backend\player_tracking\Start-LocalAnalysis.ps1
```

Terminal 3 — Android emulator and app:

```powershell
cd C:\Users\admin\Desktop\github\project\code
flutter emulators --launch HPT_API_36
flutter devices
powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-Android.ps1 -Device emulator-5554
```

Use the device ID reported by `flutter devices` if different. Launching the
emulator alone does not install new code. `Run-Android.ps1` now reuses existing
dependencies; no packages were added. Use `-RefreshDependencies` only when needed.
If dependency generation reports missing symlink support, enable Windows
Developer Mode manually and retry. Setting `FLUTTER_WINDOWS=false` does not
disable that platform in the installed Flutter SDK; no global setting is changed here.

## Apple / physical-phone preparation (not yet device-validated)

- Build on macOS with Xcode and the existing Flutter plugin toolchain. Windows
  cannot prove that an iOS build, signing or device playback succeeds.
- Android emulator default: `10.0.2.2`. iOS simulator default: `127.0.0.1`
  (only when backend services run on the same Mac). An iPhone's localhost is
  the phone, not your Windows server.
- For an actual phone, use your server computer's private LAN address in BOTH
  `--dart-define=HPT_AUTH_API_URL=http://<PC-IP>:3000` and
  `--dart-define=HPT_ANALYSIS_API_URL=http://<PC-IP>:8000`.
- The analysis launcher accepts `-ListenAddress 0.0.0.0` for deliberate private
  LAN testing. Ensure the auth server also listens on the LAN and firewall
  rules allow only the intended private network. Nothing has been opened or
  changed automatically. HTTP is for trusted local prototype testing only;
  use HTTPS and appropriate consent/security controls for deployment.
- On iPhone, accept the local-network permission prompt. Test sign-in, video
  selection (MP4 and MOV), upload, cancellation, playback, CSV/JSON save and
  video export. Large uploads, backgrounding and HEVC decoding remain test risks.
- Annotated video currently uses OpenCV MPEG-4 Part 2 (`mp4v`) inside MP4. iOS
  playback is NOT guaranteed by the filename. If playback fails, a tested
  H.264/yuv420p export/transcode pipeline is still required; no encoder is
  installed or silently downloaded by this integration.

Apple local-network references:
[Local network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy),
[ATS local networking](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking).
[Flutter iOS build requirements](https://docs.flutter.dev/deployment/ios).

## Validation and limits

- Backend: 55 tests passed, including known constant speed at three frame rates,
  known acceleration, mass independence/scaling, gaps, nonfinite/duplicate data,
  line-based synthetic court recovery, optional-mass API, and real OpenCV
  video read/write through the tracker with controlled fake detections.
- Flutter: 17 tests passed; final static analysis reports no issues. An Android
  debug APK was successfully built. The tests use fake services, not real users.
- Synthetic tests establish implementation consistency, not field accuracy.
  No real-client-video accuracy claim, real fatigue validation or iOS device
  certification is made. Keep the Experimental labels.
- Fixed rear-camera view and constant frame rate are assumed. No camera-motion
  compensation or frame-by-frame variable-rate timestamps are implemented.
  The confidence value measures detection repeatability, not accuracy.
- No new dependencies, database changes, deletions of user data or GitHub pushes.

## Local acceptance checklist

1. Log in through the privacy gate; confirm existing account still works.
2. Upload consented fixed-camera footage with visible court lines. Initially
   leave mass blank. Check whether units are m/m/s/m/s² or explicitly px.
3. Inspect calibration overlay against real sidelines/baseline; compare a known
   distance. Do not accept a consistently wrong mapping just because confidence
   is high. Failed mapping should show a clear pixel fallback.
4. Compare speed/acceleration curve samples, peaks and CSV/JSON at the same
   timestamps. Check that gaps remain breaks and retained duration is visible.
5. Reanalyse with known mass: movement metrics should be unchanged; the force
   plot should appear only for valid metric tracks. Do not call it a fatigue score.
6. Save CSV, JSON and annotated video. Check file contents and playback.
7. Test cancellation, invalid video, brief occlusion and an uncalibratable clip.
8. Record device, video FPS/resolution, camera position, units, coverage, mapping
   quality, runtime and observed errors for the supervisor review.
