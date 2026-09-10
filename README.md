# HPT Movement Analysis

HPT Movement Analysis is a Flutter prototype for uploading a fixed-camera
tennis video, running local player tracking, and reviewing movement outputs.

The current integration runs the player-tracking prototype supplied by Yuchen:
YOLO person detection, centroid-based track association, tennis-court line
detection, and homography onto a standard 10.97 m × 23.77 m doubles court. The
mapping is automatic and has not been manually validated, so every derived
movement value remains clearly labelled **Experimental**. If court detection
fails, the same analysis safely falls back to image-pixel units.

## Current workflow

```text
Flutter app
  -> select a local video
  -> upload it to the local FastAPI service
  -> poll analysis progress
  -> Yuchen prototype: YOLO + centroid tracking + court homography
  -> keep the selected near- or far-court athlete's persistent track
  -> receive JSON metrics and an annotated video
  -> review a player, cancel work, clear results, or enlarge the video
```

The result screen keeps the existing Material visual style and exposes the
outputs agreed by the team:

- movement path;
- total distance;
- average and peak speed;
- acceleration;
- deceleration; and
- direction changes.

Every estimated or uncalibrated result is labelled `Experimental` or
`Not available`.

## What belongs to this integration

The tracking foundation is Yuchen's prototype in the separately supplied
`Playertracking` repository. The corresponding runtime adapters are:

- `player_tracker.py` -> YOLO detection, centroid association and track history
  in `tracking_engine.py`;
- `court_detector.py` -> Hough court lines, standard dimensions and homography
  in `court_geometry.py`; and
- the original processing loop -> the annotated-video and metric pipeline.

Hanyu's sprint work connects that pipeline to Flutter through a local FastAPI
service: real video selection/upload, progress, cancellation, results, cleanup,
and annotated-video playback. Small integration safeguards were also added for
the supplied blue-court footage: the roof/stands are excluded during line
detection, converging sidelines are selected over vertical building lines,
three frames are combined for a steadier court estimate, off-court people are
filtered, broken detections are retained longer, trajectories are smoothed,
and only the selected athlete's most persistent court track is returned. These
changes do not claim to make the research prototype accurate or
production-ready.

## Repository layout

```text
backend/player_tracking/       Local Python analysis service
lib/features/analysis/         Flutter models, API client, state and UI
test/                          Flutter unit/widget tests
runtime/                       Local uploads, outputs and caches (ignored)
```

## Prerequisites

- Flutter 3.47 or a compatible recent stable release;
- Android Studio, Android SDK, and an Android emulator;
- Python 3.11 (recommended for the pinned computer-vision dependencies); and
- enough free disk space for PyTorch, the YOLO model, and processed videos.

## First-time backend setup (Windows PowerShell)

Run these commands from the repository root:

```powershell
py -3.11 -m venv backend\player_tracking\.venv
backend\player_tracking\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\player_tracking\.venv\Scripts\python.exe -m pip install -r backend\player_tracking\requirements-dev.txt
```

Start the service and leave this terminal open:

```powershell
backend\player_tracking\.venv\Scripts\python.exe backend\player_tracking\run_server.py
```

Verify it at `http://127.0.0.1:8000/health`. The first real analysis may
download `yolov8n.pt`; model weights and processed videos are ignored by Git.

### Optional NVIDIA GPU acceleration

The service selects CUDA automatically when the virtual environment contains a
CUDA-enabled PyTorch build, otherwise it uses CPU. On the current NVIDIA
development laptop, run this once after normal setup:

```powershell
powershell -ExecutionPolicy Bypass -File backend\player_tracking\install_cuda.ps1
```

`GET /health` and each completed result report the actual inference device.

## Run the Android app

Start the emulator, open a second terminal in the repository root, then run:

```powershell
flutter pub get
flutter devices
flutter run -d emulator-5554
```

Replace `emulator-5554` with the ID shown by `flutter devices`. Android
emulators reach the host service through the app's default URL,
`http://10.0.2.2:8000/`.

For Chrome or a Windows desktop run, override the URL:

```powershell
flutter run -d chrome --dart-define=HPT_ANALYSIS_API_URL=http://127.0.0.1:8000/
```

A physical Android phone needs the computer's LAN IP and a backend bound to
`0.0.0.0`; do not expose this prototype service to the public internet.

## Validation commands

Flutter:

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

Backend:

```powershell
Set-Location backend\player_tracking
.venv\Scripts\python.exe -m pytest tests -q
```

## Prototype boundaries

- Player identity can still be lost or switched when detections disappear or
  players overlap; the returned track is a candidate, not a confirmed name.
- Automatic court detection and metre estimates vary with camera position,
  visibility and perspective, and still require manual validation with client
  footage.
- When automatic court detection fails, pixel measurements are used instead.
- Authentication, database persistence, manual calibration and formal accuracy
  validation are future work and are outside this integration sprint.
- Uploaded and generated files remain under the ignored local `runtime/`
  directory until the analysis is deleted or the directory is cleaned.

See [backend/player_tracking/README.md](backend/player_tracking/README.md) for
the API contract and configuration options.
