from pathlib import Path
from threading import Event
import time

from fastapi.testclient import TestClient

from hpt_tracking.api import create_app
from hpt_tracking.config import Settings
from hpt_tracking.tracking_engine import AnalysisCancelled


class FakeTrackingEngine:
    def analyse(
        self,
        input_path: Path,
        output_dir: Path,
        progress_callback,
        cancellation_callback,
        target_player,
    ):
        assert input_path.read_bytes() == b"test-video"
        assert target_player == "near"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "annotated.mp4").write_bytes(b"annotated")
        progress_callback(0.5)
        return {
            "schemaVersion": 1,
            "calibrationStatus": "uncalibrated",
            "selectedTrackId": "0",
            "players": [],
            "annotatedVideoFilename": "annotated.mp4",
            "warnings": [],
        }


class BlockingTrackingEngine:
    def __init__(self):
        self.started = Event()

    def analyse(
        self,
        input_path: Path,
        output_dir: Path,
        progress_callback,
        cancellation_callback,
        target_player,
    ):
        self.started.set()
        while not cancellation_callback():
            time.sleep(0.01)
        raise AnalysisCancelled()


def test_upload_poll_download_and_delete(tmp_path):
    settings = Settings(runtime_dir=tmp_path)
    app = create_app(settings=settings, engine=FakeTrackingEngine())

    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"video": ("example.mp4", b"test-video", "video/mp4")},
        )
        assert response.status_code == 202
        analysis_id = response.json()["analysisId"]

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/analyses/{analysis_id}").json()
            if snapshot["status"] == "completed":
                break
            time.sleep(0.01)

        assert snapshot["status"] == "completed"
        assert snapshot["progress"] == 1.0
        assert snapshot["result"]["annotatedVideoUrl"].endswith("/video")

        video_response = client.get(f"/api/analyses/{analysis_id}/video")
        assert video_response.status_code == 200
        assert video_response.content == b"annotated"

        delete_response = client.delete(f"/api/analyses/{analysis_id}")
        assert delete_response.status_code == 204
        assert client.get(f"/api/analyses/{analysis_id}").status_code == 404
        assert list(tmp_path.iterdir()) == []


def test_rejects_unsupported_files(tmp_path):
    app = create_app(
        settings=Settings(runtime_dir=tmp_path),
        engine=FakeTrackingEngine(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"video": ("notes.txt", b"not video", "text/plain")},
        )

    assert response.status_code == 415


def test_rejects_unknown_target_player(tmp_path):
    app = create_app(
        settings=Settings(runtime_dir=tmp_path),
        engine=FakeTrackingEngine(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            data={"target_player": "spectator"},
            files={"video": ("example.mp4", b"test-video", "video/mp4")},
        )

    assert response.status_code == 422


def test_allows_local_flutter_web_origin(tmp_path):
    app = create_app(
        settings=Settings(runtime_dir=tmp_path),
        engine=FakeTrackingEngine(),
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/analyses",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )


def test_running_analysis_can_be_cancelled_then_deleted(tmp_path):
    engine = BlockingTrackingEngine()
    app = create_app(settings=Settings(runtime_dir=tmp_path), engine=engine)

    with TestClient(app) as client:
        response = client.post(
            "/api/analyses",
            files={"video": ("example.mp4", b"test-video", "video/mp4")},
        )
        analysis_id = response.json()["analysisId"]
        assert engine.started.wait(timeout=1)

        cancel_response = client.post(f"/api/analyses/{analysis_id}/cancel")
        assert cancel_response.status_code == 202
        assert cancel_response.json()["status"] in {"cancelling", "cancelled"}

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/analyses/{analysis_id}").json()
            if snapshot["status"] == "cancelled":
                break
            time.sleep(0.01)

        assert snapshot["status"] == "cancelled"
        assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
