# Integrated HPT application

The mobile flow is privacy acknowledgement → Wentao's sign-in/sign-up screen
→ player analysis → authorised video upload → progress/cancel → movement results
→ CSV/JSON export and annotated-video playback/save. Sign out clears the
in-memory login token. Neither credentials nor consent are persisted across
application restarts.

## Contributions and integration scope

- Suchang/new-UI: privacy gate, directional-movement priorities and workload UI.
- Wentao/Log-In-and-Sign-Up: Flutter authentication screens and Node/MySQL login service.
- Hanyu/feature/hanyu-player-tracking-integration: video picker, HTTP job lifecycle,
  Python tracking service and annotated-video playback.
- Yuchen's player-tracking/court-detection implementation is retained through
  Hanyu's adapter. Movement/data and video outputs remain available.
- YuchennWu-patch-1 is not imported.

Source snapshots: new-UI a305264, Log-In-and-Sign-Up fb4b3a4,
feature/hanyu-player-tracking-integration 18f96b0. Imported files retain the
contributors' implementations with integration-specific changes around them.

The integration uses Hanyu's actual result contract instead of the old hardcoded
mock results. Automatic court calibration remains experimental. Unmapped results
are labelled in pixels, not metres. Directional components are sums of absolute
movement along each axis; diagonal movement contributes to both axes, so they
must not be added to reconstruct total travelled distance.

Overall effort remains visible but unavailable until the team/client agrees on
and validates a formula. No fabricated 0–100 effort score is used.

CSV contains summary metrics, units, availability and notes. JSON additionally
retains all returned trajectory/time-series fields. Save annotated video downloads
the returned MP4 to the platform's file-save dialog. Large video exports currently
buffer the output in memory; test with short clips first. Export before clearing
the result: clearing deletes the server's job, uploaded input and video output.

## Local setup

This is an Android/iOS Flutter application using two development servers.
It is not a browser-only application. Video processing currently runs on the
configured computer/server, not on the phone. Offline/on-device inference has
not been implemented.

### 1. Authentication service (Node.js + MySQL)

Create the database/tables using
`backend/auth/sql/complete_database_setup.sql` in a local MySQL instance.
Create an application database user with permissions on that database.
Copy `backend/auth/.env.example` to `backend/auth/.env`, fill in DB_USER,
DB_PASSWORD and TOKEN (a random secret at least 32 characters long).
Do not commit .env. Optional ADMIN_EMAIL and ADMIN_PASSWORD seed an administrator.

From `backend/auth`:

```powershell
npm ci
npm start
```

The default port is 3000. GET /health reports database connectivity.
Register/login use Wentao's original /api/auth/signIn and /api/auth/login paths.
GET /api/auth/session validates the token for the analysis service.
AUTH_TOKEN_TTL defaults to 8h to allow long video-processing sessions.
The original registration form requests a username; the inherited database/API
currently identifies accounts by email and does not persist the username.

### 2. Analysis service (Python 3.11)

From `backend/player_tracking`:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:HPT_AUTH_API_URL = 'http://127.0.0.1:3000'
$env:HPT_API_HOST = '0.0.0.0'
.venv\Scripts\python.exe run_server.py
```

Use the Python 3.11 environment for the pinned numerical/ML packages.
The default analysis port is 8000. The YOLO model is downloaded on first use;
pre-download/configure HPT_YOLO_MODEL for an offline demonstration.
The CPU path is sufficient for initial testing; see Hanyu's
`backend/player_tracking/README.md` for CUDA options.

Normal startup requires a valid login session for upload, polling, cancellation,
deletion and video download. Jobs are scoped to the authenticated email.
Settings(auth_url=None) is reserved for explicit isolated backend tests.
The current job registry is in memory: restarting the server does not restore
previous jobs. Files remain under runtime until explicitly removed.

### 3. Flutter application

From the repository root, with an Android emulator running:

```powershell
flutter pub get
flutter run --dart-define=HPT_AUTH_API_URL=http://10.0.2.2:3000 --dart-define=HPT_ANALYSIS_API_URL=http://10.0.2.2:8000
```

10.0.2.2 addresses the host computer from the standard Android emulator.
For a physical phone, replace both addresses with the computer's LAN address
and allow the two ports through its firewall on the private network.
For an iOS simulator, use 127.0.0.1. iOS compilation/device testing requires macOS
and Xcode and was not performed on this Windows machine.

Android debug builds allow HTTP for these development endpoints. Release builds
should use HTTPS. Configure iOS development networking/ATS for the chosen server
on the Mac; no blanket release ATS exception is included.

Flutter on Windows may request Developer Mode when creating desktop plugin
symlinks. Enable it if flutter pub get reports that requirement. Once packages
are resolved, flutter analyze --no-pub, flutter test --no-pub and
flutter build apk --debug --no-pub can validate the Android target.

## Verification and remaining acceptance checks

- Flutter tests exercise consent, failed/successful login, logout, video selection,
  HTTP result parsing, cancellation, results and export serialization.
- Python tests exercise geometry/tracking helpers, movement metrics,
  upload/poll/video/delete and session/ownership checks using a fake inference engine.
- These do not establish detection accuracy or an end-to-end run with real MySQL,
  real credentials, real YOLO inference and client footage.
- Before the client demonstration, run that real scenario on a short authorised
  clip, verify CSV/JSON and saved MP4 on both target phones, and compare court
  distances against a reference measurement.
- The privacy screen is a session acknowledgement; it does not store a signed
  guardian consent record. Agree retention, withdrawal and consent administration
  before using real participant footage.
