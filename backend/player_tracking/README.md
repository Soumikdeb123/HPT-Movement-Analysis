# Local player-tracking service

This directory contains the first integration boundary between the Flutter UI
and the team's Yuchen-supplied player-tracking prototype. FastAPI handles
uploads and job status; `YuchenPrototypeTrackingEngine` adapts Yuchen's YOLO and
centroid-tracking loop; `court_geometry.py` adapts his court dimensions,
Hough-line detection and homography; and `metrics.py` owns the output
calculations. Keeping these responsibilities separate allows later algorithm
work without rewriting the mobile UI or API.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check service and calibration status |
| `POST` | `/api/analyses` | Upload multipart field `video`; returns `202` |
| `GET` | `/api/analyses/{id}` | Poll status, progress, and completed result |
| `GET` | `/api/analyses/{id}/video` | Stream the annotated result video |
| `POST` | `/api/analyses/{id}/cancel` | Cooperatively cancel queued/running work |
| `DELETE` | `/api/analyses/{id}` | Remove a final job and its local files |

Jobs move through `queued`, `processing`, `cancelling`, `cancelled`,
`completed`, or `failed`. Only one YOLO job runs at a time to avoid exhausting
memory on a development laptop.

The completed JSON returns one persistent track for the athlete selected by
their starting court side (`near` or `far`). It includes the court calibration,
processing device, movement path, total distance, speed,
acceleration/deceleration and direction changes. Court-mapped metre values and
pixel fallbacks both carry explicit status/warning fields.

## Run

From the repository root:

```powershell
py -3.11 -m venv backend\player_tracking\.venv
backend\player_tracking\.venv\Scripts\python.exe -m pip install -r backend\player_tracking\requirements-dev.txt
backend\player_tracking\.venv\Scripts\python.exe backend\player_tracking\run_server.py
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

For an NVIDIA GPU, run `install_cuda.ps1` after creating the environment. It
installs the pinned CUDA 12.4 PyTorch build and verifies whether CUDA is visible.

## Configuration

The following environment variables are optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `HPT_API_HOST` | `127.0.0.1` | Server bind address |
| `HPT_API_PORT` | `8000` | Server port |
| `HPT_RUNTIME_DIR` | `<repo>/runtime` | Upload/output directory |
| `HPT_YOLO_MODEL` | `yolov8n.pt` | Ultralytics model name or local path |
| `HPT_MAX_UPLOAD_BYTES` | `524288000` | Upload limit (500 MiB) |
| `HPT_YOLO_CONFIDENCE` | `0.5` | Minimum person confidence |
| `HPT_MAX_TRACK_DISTANCE` | `120` | Maximum pixel association distance |
| `HPT_MAX_TRACK_DISTANCE_METRES` | `3.0` | Association distance after court mapping |
| `HPT_MAX_MISSED_FRAMES` | `90` | Frames retained through a detection gap |
| `HPT_MAX_PLAYERS` | `1` | Maximum selected-athlete tracks returned |
| `HPT_INFERENCE_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, `cuda:0`, or `0` |

Example:

```powershell
$env:HPT_YOLO_CONFIDENCE = '0.4'
$env:HPT_YOLO_MODEL = 'yolov8s.pt'
backend\player_tracking\.venv\Scripts\python.exe backend\player_tracking\run_server.py
```

Changing these values changes prototype behaviour and should be recorded when
comparing results.

## Tests

```powershell
Set-Location backend\player_tracking
.venv\Scripts\python.exe -m pytest tests -q
```

The API tests inject a deterministic fake engine; the metrics tests exercise
the real calculation code without downloading model weights. A short real-video
smoke test should also be run before demonstrations.
