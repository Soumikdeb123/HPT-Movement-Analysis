"""FastAPI application exposing the local player-tracking prototype."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
import json
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings
from .jobs import AnalysisJobManager
from .tracking_engine import PrototypeTrackingEngine, TrackingEngine


ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}
CHUNK_SIZE = 1024 * 1024


def create_app(
    settings: Optional[Settings] = None,
    engine: Optional[TrackingEngine] = None,
) -> FastAPI:
    configured_settings = settings or Settings.from_environment()
    if engine is None:
        ultralytics_config_dir = configured_settings.runtime_dir / "ultralytics"
        ultralytics_config_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(ultralytics_config_dir))
        configured_engine: TrackingEngine = PrototypeTrackingEngine(
            model_path=configured_settings.model_path,
            confidence_threshold=configured_settings.confidence_threshold,
            maximum_track_distance_pixels=(
                configured_settings.maximum_track_distance_pixels
            ),
            maximum_track_distance_metres=(
                configured_settings.maximum_track_distance_metres
            ),
            maximum_missed_frames=configured_settings.maximum_missed_frames,
            maximum_players=configured_settings.maximum_players,
            inference_device=configured_settings.inference_device,
        )
    else:
        configured_engine = engine

    manager = AnalysisJobManager(
        runtime_dir=configured_settings.runtime_dir,
        engine=configured_engine,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(
        title="HPT Player Tracking API",
        version="0.1.0",
        description="Local-only prototype analysis service.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
    app.state.job_manager = manager
    owners = {}

    def authenticated_user(request: Request) -> str:
        if configured_settings.auth_url is None:
            return "local-test"
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Please sign in.")
        try:
            upstream = UrlRequest(
                configured_settings.auth_url.rstrip("/") + "/api/auth/session",
                headers={"Authorization": authorization},
            )
            with urlopen(upstream, timeout=10) as response:
                email = json.load(response).get("email")
            if not isinstance(email, str) or not email:
                raise HTTPException(status_code=401, detail="Invalid session. Please sign in again.")
            return email
        except HTTPError as error:
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise HTTPException(status_code=503, detail="Authentication service unavailable.") from error

    def check_owner(job_id: str, user: str):
        if owners.get(job_id) != user:
            raise HTTPException(status_code=404, detail="Analysis job was not found.")


    @app.get("/health")
    async def health() -> dict:
        response = {
            "status": "ok",
            "model": configured_settings.model_path,
            "algorithm": "Yuchen Playertracking prototype",
        }
        device_label = getattr(configured_engine, "device_label", None)
        if device_label is not None:
            response["inferenceDevice"] = device_label
        return response

    @app.post("/api/analyses", status_code=status.HTTP_202_ACCEPTED)
    async def create_analysis(
        request: Request,
        video: UploadFile = File(...),
        target_player: str = Form("near"),
        user: str = Depends(authenticated_user),
    ) -> dict:
        if target_player not in {"near", "far"}:
            raise HTTPException(
                status_code=422,
                detail="Select either the near-court or far-court player.",
            )
        suffix = Path(video.filename or "").suffix.lower()
        if suffix not in ALLOWED_VIDEO_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Select an MP4, MOV, AVI or MKV video.",
            )

        upload_id = uuid_for_upload()
        job_root = configured_settings.runtime_dir / upload_id
        job_root.mkdir(parents=True, exist_ok=False)
        input_path = job_root / f"input{suffix}"

        total_bytes = 0
        try:
            with input_path.open("wb") as output:
                while True:
                    chunk = await video.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > configured_settings.maximum_upload_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="The selected video exceeds the local upload limit.",
                        )
                    output.write(chunk)
        except Exception:
            shutil.rmtree(job_root, ignore_errors=True)
            raise
        finally:
            await video.close()

        if total_bytes == 0:
            shutil.rmtree(job_root, ignore_errors=True)
            raise HTTPException(status_code=400, detail="The selected video is empty.")

        job = request.app.state.job_manager.create_job(
            input_path=input_path,
            original_filename=Path(video.filename or f"video{suffix}").name,
            target_player=target_player,
        )
        owners[job.snapshot()["analysisId"]] = user
        return job.snapshot()

    @app.get("/api/analyses/{job_id}")
    async def get_analysis(request: Request, job_id: str, user: str = Depends(authenticated_user)) -> dict:
        check_owner(job_id, user)
        job = request.app.state.job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job was not found.")
        return job.snapshot()

    @app.get("/api/analyses/{job_id}/video")
    async def get_annotated_video(request: Request, job_id: str, user: str = Depends(authenticated_user)):
        check_owner(job_id, user)
        job = request.app.state.job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job was not found.")
        snapshot = job.snapshot()
        if snapshot["status"] != "completed" or job.result is None:
            raise HTTPException(status_code=409, detail="Analysis is not complete.")

        filename = job.result.get("annotatedVideoFilename")
        video_path = job.output_dir / filename if filename else None
        if video_path is None or not video_path.is_file():
            raise HTTPException(status_code=404, detail="Annotated video was not found.")
        return FileResponse(video_path, media_type="video/mp4", filename="annotated.mp4")

    @app.post(
        "/api/analyses/{job_id}/cancel",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def cancel_analysis(request: Request, job_id: str, user: str = Depends(authenticated_user)) -> dict:
        check_owner(job_id, user)
        job = request.app.state.job_manager.cancel_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job was not found.")
        return job.snapshot()

    @app.delete("/api/analyses/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_analysis(request: Request, job_id: str, user: str = Depends(authenticated_user)) -> None:
        check_owner(job_id, user)
        try:
            deleted = request.app.state.job_manager.delete_job(job_id)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Analysis job was not found.")

    return app


def uuid_for_upload() -> str:
    from uuid import uuid4

    return f"upload-{uuid4().hex}"
