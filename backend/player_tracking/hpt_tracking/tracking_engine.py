"""UI adapter for the team's Yuchen-supplied Playertracking prototype.

The detector, centroid association, track history and annotated-video loop are
based on the prototype's ``player_tracker.py``. This integration adds court
filtering, selected-athlete reporting, cancellation and explicit device use;
it does not replace the team prototype with an unrelated tracking system.
"""

from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from .court_geometry import CourtCalibration, CourtDetector
from .metrics import TrajectorySample, analyse_trajectory


ProgressCallback = Callable[[float], None]
CancellationCallback = Callable[[], bool]
BBox = Tuple[float, float, float, float]


class AnalysisCancelled(RuntimeError):
    """Raised when a cooperative cancellation reaches the video loop."""


class TrackingEngine(Protocol):
    """Contract used by the job service and deterministic test doubles."""

    def analyse(
        self,
        input_path: Path,
        output_dir: Path,
        progress_callback: ProgressCallback,
        cancellation_callback: CancellationCallback,
        target_player: str,
    ) -> Dict:
        """Analyse a video and return a JSON-serialisable dictionary."""


@dataclass
class Detection:
    """YOLO person detection, optionally mapped onto the standard court."""

    bbox: BBox
    confidence: float
    court_position: Optional[Tuple[float, float]] = None

    @property
    def foot_position(self) -> Tuple[float, float]:
        left, _top, right, bottom = self.bbox
        return ((left + right) / 2.0, bottom)

    @property
    def association_position(self) -> Tuple[float, float]:
        return self.court_position or self.foot_position

    @property
    def ranking_score(self) -> float:
        left, top, right, bottom = self.bbox
        area = max(1.0, (right - left) * (bottom - top))
        return self.confidence * area**0.5


@dataclass
class Track:
    """Full trajectory for one ID, extending Yuchen's PlayerTrack structure."""

    track_id: int
    colour: Tuple[int, int, int]
    image_trajectory: List[TrajectorySample] = field(default_factory=list)
    court_trajectory: List[TrajectorySample] = field(default_factory=list)
    association_trajectory: List[TrajectorySample] = field(default_factory=list)
    latest_bbox: Optional[BBox] = None
    missed_frames: int = 0

    @property
    def latest_position(self) -> Optional[Tuple[float, float]]:
        if not self.association_trajectory:
            return None
        _frame, x, y = self.association_trajectory[-1]
        return (x, y)

    def predicted_position(self, frame_number: int) -> Optional[Tuple[float, float]]:
        if len(self.association_trajectory) < 2:
            return self.latest_position
        previous_frame, previous_x, previous_y = self.association_trajectory[-2]
        latest_frame, latest_x, latest_y = self.association_trajectory[-1]
        elapsed_frames = latest_frame - previous_frame
        if elapsed_frames <= 0:
            return (latest_x, latest_y)
        prediction_frames = min(frame_number - latest_frame, 5)
        return (
            latest_x + ((latest_x - previous_x) / elapsed_frames) * prediction_frames,
            latest_y + ((latest_y - previous_y) / elapsed_frames) * prediction_frames,
        )

    def update(self, frame_number: int, detection: Detection) -> None:
        image_x, image_y = detection.foot_position
        self.image_trajectory.append((frame_number, float(image_x), float(image_y)))
        if detection.court_position is not None:
            court_x, court_y = detection.court_position
            self.court_trajectory.append(
                (frame_number, float(court_x), float(court_y))
            )
        association_x, association_y = detection.association_position
        self.association_trajectory.append(
            (frame_number, float(association_x), float(association_y))
        )
        self.latest_bbox = detection.bbox
        self.missed_frames = 0


class YuchenCentroidTrackManager:
    """Small, strengthened adapter around the prototype centroid tracker."""

    _colours: Sequence[Tuple[int, int, int]] = (
        (255, 80, 80),
        (80, 210, 120),
        (80, 140, 255),
        (230, 180, 60),
        (190, 90, 220),
    )

    def __init__(self, maximum_distance: float, maximum_missed_frames: int):
        self.maximum_distance = maximum_distance
        self.maximum_missed_frames = maximum_missed_frames
        self.tracks: Dict[int, Track] = {}
        self._next_track_id = 0

    def update(self, frame_number: int, detections: Sequence[Detection]) -> None:
        candidates: List[Tuple[float, int, int]] = []
        for track_id, track in self.tracks.items():
            previous = track.predicted_position(frame_number)
            if previous is None or track.missed_frames > self.maximum_missed_frames:
                continue
            distance_limit = self.maximum_distance * (
                1.0 + min(track.missed_frames, 10) * 0.12
            )
            for detection_index, detection in enumerate(detections):
                current = detection.association_position
                distance = (
                    (previous[0] - current[0]) ** 2
                    + (previous[1] - current[1]) ** 2
                ) ** 0.5
                if distance <= distance_limit:
                    candidates.append((distance, track_id, detection_index))

        matched_tracks = set()
        matched_detections = set()
        for _distance, track_id, detection_index in sorted(candidates):
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            self.tracks[track_id].update(frame_number, detections[detection_index])
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)

        for track_id, track in self.tracks.items():
            if track_id not in matched_tracks:
                track.missed_frames += 1

        unmatched = [
            (index, detection)
            for index, detection in enumerate(detections)
            if index not in matched_detections
        ]
        unmatched.sort(key=lambda item: item[1].ranking_score, reverse=True)
        for _detection_index, detection in unmatched[:2]:
            track = Track(
                track_id=self._next_track_id,
                colour=self._colours[self._next_track_id % len(self._colours)],
            )
            track.update(frame_number, detection)
            self.tracks[track.track_id] = track
            self._next_track_id += 1


def select_primary_tracks(
    tracks: Sequence[Track], minimum_frames: int, maximum_players: int
) -> List[Track]:
    """Return the requested number of most persistent player trajectories."""

    eligible = [
        track for track in tracks if len(track.image_trajectory) >= minimum_frames
    ]
    eligible.sort(
        key=lambda track: (
            len(track.image_trajectory),
            track.image_trajectory[-1][0] - track.image_trajectory[0][0],
        ),
        reverse=True,
    )
    return eligible[:maximum_players]


class YuchenPrototypeTrackingEngine:
    """Service adapter that executes the team's player-tracking approach."""

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.5,
        maximum_track_distance_pixels: float = 120.0,
        maximum_track_distance_metres: float = 3.0,
        maximum_missed_frames: int = 90,
        minimum_track_frames: int = 5,
        maximum_players: int = 1,
        inference_device: str = "auto",
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.maximum_track_distance_pixels = maximum_track_distance_pixels
        self.maximum_track_distance_metres = maximum_track_distance_metres
        self.maximum_missed_frames = maximum_missed_frames
        self.minimum_track_frames = minimum_track_frames
        self.maximum_players = maximum_players
        self.inference_device = inference_device
        self._model = None
        self._device_argument: object = "cpu"
        self._device_label = "CPU"

    @property
    def device_label(self) -> str:
        self._resolve_device()
        return self._device_label

    def _resolve_device(self) -> None:
        try:
            import torch
        except ImportError as error:
            raise RuntimeError(
                "PyTorch is not installed. Run: pip install -r requirements.txt"
            ) from error

        requested = self.inference_device.strip().lower()
        cuda_available = torch.cuda.is_available()
        wants_cuda = requested in {"auto", "cuda", "cuda:0", "0"}
        if wants_cuda and cuda_available:
            self._device_argument = 0
            self._device_label = f"CUDA: {torch.cuda.get_device_name(0)}"
            return
        if requested not in {"auto", "cpu"} and not cuda_available:
            raise RuntimeError(
                f"Inference device '{self.inference_device}' requested, but CUDA "
                "is unavailable in the installed PyTorch build."
            )
        self._device_argument = "cpu"
        self._device_label = "CPU"

    def _load_model(self):
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError as error:
                raise RuntimeError(
                    "Ultralytics is not installed. Run: pip install -r requirements.txt"
                ) from error
            self._resolve_device()
            self._model = YOLO(self.model_path)
            print(f"[HPT] Playertracking inference device: {self._device_label}")
        return self._model

    def analyse(
        self,
        input_path: Path,
        output_dir: Path,
        progress_callback: ProgressCallback,
        cancellation_callback: CancellationCallback,
        target_player: str,
    ) -> Dict:
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError(
                "OpenCV is not installed. Run: pip install -r requirements.txt"
            ) from error

        if target_player not in {"near", "far"}:
            raise ValueError("Target player must be 'near' or 'far'.")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_video = output_dir / "annotated.mp4"
        capture = cv2.VideoCapture(str(input_path))
        if not capture.isOpened():
            raise ValueError("The selected video could not be opened by OpenCV.")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if fps <= 0:
            fps = 30.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            capture.release()
            raise ValueError("The selected video has invalid dimensions.")

        calibration_frames = []
        for sample_frame in (0, int(fps), int(fps * 2)):
            capture.set(cv2.CAP_PROP_POS_FRAMES, sample_frame)
            has_sample, sample = capture.read()
            if has_sample:
                calibration_frames.append(sample)
        calibration = CourtDetector().detect_from_frames(calibration_frames)
        capture.release()
        capture = cv2.VideoCapture(str(input_path))

        writer = cv2.VideoWriter(
            str(output_video),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            capture.release()
            raise RuntimeError("Could not create the annotated output video.")

        model = self._load_model()
        tracker = YuchenCentroidTrackManager(
            maximum_distance=(
                self.maximum_track_distance_metres
                if calibration is not None
                else self.maximum_track_distance_pixels
            ),
            maximum_missed_frames=self.maximum_missed_frames,
        )

        frame_number = 0
        try:
            while True:
                if cancellation_callback():
                    raise AnalysisCancelled("Analysis cancelled by the user.")
                has_frame, frame = capture.read()
                if not has_frame:
                    break

                detections: List[Detection] = []
                inference_results = model.predict(
                    frame,
                    verbose=False,
                    device=self._device_argument,
                    classes=[0],
                    conf=self.confidence_threshold,
                )
                for result in inference_results:
                    if result.boxes is None:
                        continue
                    for box in result.boxes:
                        confidence = float(box.conf[0].item())
                        left, top, right, bottom = (
                            float(value) for value in box.xyxy[0].cpu().tolist()
                        )
                        detection = Detection(
                            bbox=(left, top, right, bottom),
                            confidence=confidence,
                        )
                        if calibration is not None:
                            if not calibration.contains_player_position(
                                detection.foot_position
                            ):
                                continue
                            detection.court_position = calibration.image_to_court(
                                detection.foot_position
                            )
                        detections.append(detection)

                detections = self._select_target_detection(
                    detections,
                    target_player=target_player,
                    calibration=calibration,
                    frame_height=height,
                )

                tracker.update(frame_number, detections)
                self._draw_annotations(
                    cv2,
                    frame,
                    tracker.tracks,
                    calibration,
                    target_player,
                )
                writer.write(frame)

                frame_number += 1
                if total_frames > 0:
                    progress_callback(min(frame_number / total_frames, 0.99))
        finally:
            capture.release()
            writer.release()

        minimum_report_frames = max(
            self.minimum_track_frames,
            min(int(fps * 2), max(5, int(frame_number * 0.02))),
        )
        primary_tracks = select_primary_tracks(
            list(tracker.tracks.values()),
            minimum_frames=minimum_report_frames,
            maximum_players=self.maximum_players,
        )

        players = []
        for track in primary_tracks:
            if calibration is not None and track.court_trajectory:
                trajectory = self._smooth_trajectory(track.court_trajectory)
                metrics = analyse_trajectory(
                    trajectory,
                    fps,
                    minimum_step=0.08,
                    coordinate_system="estimated_court_metres",
                    distance_unit="m",
                    measurement_note=(
                        "Estimated from automatically detected court lines and "
                        "standard doubles-court dimensions; not manually validated."
                    ),
                )
            else:
                trajectory = self._smooth_trajectory(track.image_trajectory)
                metrics = analyse_trajectory(trajectory, fps)
            players.append(
                {
                    "trackId": str(track.track_id),
                    "trackedFrames": len(track.image_trajectory),
                    **metrics,
                }
            )

        progress_callback(1.0)
        warnings = [
            "Tracking is based on the team's Yuchen-supplied Playertracking prototype.",
            f"Only the selected {target_player}-court athlete is reported.",
            "Player association may still lose or switch identities after occlusion.",
        ]
        if calibration is None:
            warnings.append(
                "Court detection was not reliable enough; movement remains in pixels."
            )
        else:
            warnings.append(
                "Court-to-metre mapping is automatic and experimental, not validated."
            )
        if not players:
            warnings.append("No player track met the persistence threshold.")

        return {
            "schemaVersion": 2,
            "algorithm": "Yuchen Playertracking prototype with integration safeguards",
            "calibrationStatus": "estimated" if calibration is not None else "uncalibrated",
            "courtCalibration": calibration.as_dict() if calibration else None,
            "inferenceDevice": self._device_label,
            "targetPlayer": target_player,
            "selectedTrackId": players[0]["trackId"] if players else None,
            "video": {
                "fps": round(fps, 3),
                "processedFrames": frame_number,
                "width": width,
                "height": height,
            },
            "players": players,
            "annotatedVideoFilename": output_video.name,
            "warnings": warnings,
        }

    @staticmethod
    def _select_target_detection(
        detections: Sequence[Detection],
        target_player: str,
        calibration: Optional[CourtCalibration],
        frame_height: int,
    ) -> List[Detection]:
        """Keep one court-side athlete while still detecting everyone with YOLO."""

        if not detections:
            return []

        if calibration is not None:
            centre_line = calibration.length_metres / 2.0
            side_margin = 1.5
            if target_player == "near":
                on_target_side = [
                    detection
                    for detection in detections
                    if detection.court_position is not None
                    and detection.court_position[1] >= centre_line - side_margin
                ]
                pool = on_target_side or list(detections)
                return [
                    max(
                        pool,
                        key=lambda detection: detection.court_position[1]
                        if detection.court_position is not None
                        else float("-inf"),
                    )
                ]

            on_target_side = [
                detection
                for detection in detections
                if detection.court_position is not None
                and detection.court_position[1] <= centre_line + side_margin
            ]
            pool = on_target_side or list(detections)
            return [
                min(
                    pool,
                    key=lambda detection: detection.court_position[1]
                    if detection.court_position is not None
                    else float("inf"),
                )
            ]

        # Pixel fallback for a fixed rear-court camera. The lower player is near;
        # the upper player is far. Ignore the upper stands before ranking.
        visible_court = [
            detection
            for detection in detections
            if detection.foot_position[1] >= frame_height * 0.45
        ]
        pool = visible_court or list(detections)
        selector = max if target_player == "near" else min
        return [selector(pool, key=lambda detection: detection.foot_position[1])]

    @staticmethod
    def _smooth_trajectory(
        samples: Sequence[TrajectorySample], radius: int = 2
    ) -> List[TrajectorySample]:
        """Reduce frame-to-frame YOLO box jitter without inventing new points."""

        smoothed = []
        for index, (frame, _x, _y) in enumerate(samples):
            window = samples[max(0, index - radius) : index + radius + 1]
            smoothed.append(
                (
                    frame,
                    float(median(point[1] for point in window)),
                    float(median(point[2] for point in window)),
                )
            )
        return smoothed

    @staticmethod
    def _draw_annotations(
        cv2_module,
        frame,
        tracks: Dict[int, Track],
        calibration: Optional[CourtCalibration],
        target_player: str,
    ) -> None:
        if calibration is not None:
            import numpy as np

            corners = calibration.corners.astype(np.int32)
            cv2_module.polylines(frame, [corners], True, (20, 220, 255), 2)
        cv2_module.putText(
            frame,
            "Yuchen Playertracking prototype - experimental",
            (16, 28),
            cv2_module.FONT_HERSHEY_SIMPLEX,
            0.65,
            (20, 220, 255),
            2,
        )
        for track in tracks.values():
            if track.latest_bbox is None or track.missed_frames > 0:
                continue
            left, top, right, bottom = (int(value) for value in track.latest_bbox)
            cv2_module.rectangle(frame, (left, top), (right, bottom), track.colour, 2)
            cv2_module.putText(
                frame,
                f"Selected athlete ({target_player} court)",
                (left, max(20, top - 8)),
                cv2_module.FONT_HERSHEY_SIMPLEX,
                0.55,
                track.colour,
                2,
            )
            recent_points = [
                (int(x), int(y))
                for _frame, x, y in track.image_trajectory[-30:]
            ]
            if len(recent_points) > 1:
                import numpy as np

                cv2_module.polylines(
                    frame,
                    [np.asarray(recent_points, dtype=np.int32)],
                    False,
                    track.colour,
                    2,
                )


# Backwards-compatible name for earlier integration code and documentation.
PrototypeTrackingEngine = YuchenPrototypeTrackingEngine
