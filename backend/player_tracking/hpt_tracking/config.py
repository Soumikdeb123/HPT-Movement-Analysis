"""Configuration for the local analysis service."""

from dataclasses import dataclass
import os
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    runtime_dir: Path = REPOSITORY_ROOT / "runtime"
    model_path: str = "yolov8n.pt"
    maximum_upload_bytes: int = 500 * 1024 * 1024
    confidence_threshold: float = 0.5
    maximum_track_distance_pixels: float = 120.0
    maximum_track_distance_metres: float = 3.0
    maximum_missed_frames: int = 90
    maximum_players: int = 1
    inference_device: str = "auto"

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            runtime_dir=Path(
                os.getenv("HPT_RUNTIME_DIR", str(REPOSITORY_ROOT / "runtime"))
            ).resolve(),
            model_path=os.getenv("HPT_YOLO_MODEL", "yolov8n.pt"),
            maximum_upload_bytes=int(
                os.getenv("HPT_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024))
            ),
            confidence_threshold=float(os.getenv("HPT_YOLO_CONFIDENCE", "0.5")),
            maximum_track_distance_pixels=float(
                os.getenv("HPT_MAX_TRACK_DISTANCE", "120")
            ),
            maximum_track_distance_metres=float(
                os.getenv("HPT_MAX_TRACK_DISTANCE_METRES", "3.0")
            ),
            maximum_missed_frames=int(os.getenv("HPT_MAX_MISSED_FRAMES", "90")),
            maximum_players=int(os.getenv("HPT_MAX_PLAYERS", "1")),
            inference_device=os.getenv("HPT_INFERENCE_DEVICE", "auto"),
        )
