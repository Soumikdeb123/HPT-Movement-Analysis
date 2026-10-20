import io
import json
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from hpt_tracking.api import create_app
from hpt_tracking.config import Settings
from test_api import FakeTrackingEngine


def test_analysis_requires_session_and_is_owned_by_the_logged_in_user(tmp_path, monkeypatch):
    def authenticate(request, timeout):
        header = request.get_header("Authorization")
        if header not in {"Bearer alice", "Bearer bob"}:
            raise HTTPError(request.full_url, 401, "Invalid", {}, None)
        return io.BytesIO(json.dumps({"email": header.split()[1] + "@example.com"}).encode())

    monkeypatch.setattr("hpt_tracking.api.urlopen", authenticate)
    app = create_app(
        Settings(runtime_dir=tmp_path, auth_url="http://auth.test"),
        FakeTrackingEngine(),
    )
    with TestClient(app) as client:
        assert client.post("/api/analyses").status_code == 401
        assert client.post("/api/analyses", headers={"Authorization": "Bearer bad"}).status_code == 401
        upload = client.post("/api/analyses",
            headers={"Authorization": "Bearer alice"},
            files={"video": ("example.mp4", b"test-video", "video/mp4")})
        assert upload.status_code == 202
        job = upload.json()["analysisId"]
        for method, suffix in [("GET", ""), ("GET", "/video"), ("POST", "/cancel"), ("DELETE", "")]:
            assert client.request(method, f"/api/analyses/{job}{suffix}",
                headers={"Authorization": "Bearer bob"}).status_code == 404
        assert client.get(f"/api/analyses/{job}",
            headers={"Authorization": "Bearer alice"}).status_code == 200
