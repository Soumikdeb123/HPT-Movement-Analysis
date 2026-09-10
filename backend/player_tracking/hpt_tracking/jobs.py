"""Single-worker analysis job manager used by the local API."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from threading import Event, Lock
from typing import Dict, Optional
from uuid import uuid4

from .tracking_engine import AnalysisCancelled, TrackingEngine


@dataclass
class AnalysisJob:
    job_id: str
    input_path: Path
    output_dir: Path
    original_filename: str
    target_player: str
    status: str = "queued"
    progress: float = 0.0
    result: Optional[Dict] = None
    error: Optional[str] = None
    cancel_event: Event = field(default_factory=Event, repr=False)
    lock: Lock = field(default_factory=Lock, repr=False)

    def snapshot(self) -> Dict:
        with self.lock:
            result = dict(self.result) if self.result is not None else None
            if result is not None and result.get("annotatedVideoFilename"):
                result["annotatedVideoUrl"] = f"/api/analyses/{self.job_id}/video"
                result.pop("annotatedVideoFilename", None)
            return {
                "analysisId": self.job_id,
                "status": self.status,
                "progress": self.progress,
                "originalFilename": self.original_filename,
                "targetPlayer": self.target_player,
                "result": result,
                "error": self.error,
            }


class AnalysisJobManager:
    """Runs one memory-intensive YOLO analysis at a time."""

    def __init__(self, runtime_dir: Path, engine: TrackingEngine):
        self.runtime_dir = runtime_dir
        self.engine = engine
        self.jobs: Dict[str, AnalysisJob] = {}
        self._jobs_lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hpt")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def create_job(
        self, input_path: Path, original_filename: str, target_player: str
    ) -> AnalysisJob:
        job_id = uuid4().hex
        job_root = self.runtime_dir / job_id
        output_dir = job_root / "results"
        job_root.mkdir(parents=True, exist_ok=False)
        managed_input_path = job_root / input_path.name
        shutil.move(str(input_path), managed_input_path)
        if input_path.parent != self.runtime_dir:
            shutil.rmtree(input_path.parent, ignore_errors=True)
        job = AnalysisJob(
            job_id=job_id,
            input_path=managed_input_path,
            output_dir=output_dir,
            original_filename=original_filename,
            target_player=target_player,
        )
        with self._jobs_lock:
            self.jobs[job_id] = job
        self._executor.submit(self._run_job, job)
        return job

    def get_job(self, job_id: str) -> Optional[AnalysisJob]:
        with self._jobs_lock:
            return self.jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                return False
            with job.lock:
                if job.status in {"queued", "processing", "cancelling"}:
                    raise RuntimeError("A running analysis cannot be deleted.")
            del self.jobs[job_id]
        shutil.rmtree(self.runtime_dir / job_id, ignore_errors=True)
        return True

    def cancel_job(self, job_id: str) -> Optional[AnalysisJob]:
        """Request cooperative cancellation and return the current job."""

        job = self.get_job(job_id)
        if job is None:
            return None
        with job.lock:
            if job.status in {"queued", "processing", "cancelling"}:
                job.status = "cancelling"
                job.cancel_event.set()
        return job

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run_job(self, job: AnalysisJob) -> None:
        with job.lock:
            if job.cancel_event.is_set():
                job.status = "cancelled"
                shutil.rmtree(self.runtime_dir / job.job_id, ignore_errors=True)
                return
            job.status = "processing"
            job.progress = 0.0

        def update_progress(value: float) -> None:
            with job.lock:
                job.progress = max(job.progress, min(1.0, float(value)))

        try:
            result = self.engine.analyse(
                input_path=job.input_path,
                output_dir=job.output_dir,
                progress_callback=update_progress,
                cancellation_callback=job.cancel_event.is_set,
                target_player=job.target_player,
            )
            with job.lock:
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    job.result = None
                else:
                    job.result = result
                    job.progress = 1.0
                    job.status = "completed"
        except AnalysisCancelled:
            with job.lock:
                job.status = "cancelled"
                job.result = None
                job.error = None
            shutil.rmtree(self.runtime_dir / job.job_id, ignore_errors=True)
        except Exception as error:  # The API must turn engine failures into job state.
            with job.lock:
                job.status = "failed"
                job.error = str(error) or error.__class__.__name__
