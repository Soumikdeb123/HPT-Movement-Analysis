import cv2
import numpy as np
from ultralytics import YOLO
from scipy.spatial.distance import euclidean
from typing import List, Dict, Tuple, Optional
import json
from dataclasses import dataclass, field
from collections import deque
import time


@dataclass
class PlayerDetection:
    """One player detection in image and (when calibrated) court coordinates."""
    bbox: List[float]  # [x1, y1, x2, y2]
    center: Tuple[float, float]
    ground_point: Tuple[float, float]  # bottom-centre of bbox in video pixels
    confidence: float
    court_point: Optional[Tuple[float, float]] = None  # (x, y) in metres
    class_id: int = 0


@dataclass
class PlayerTrack:
    """Tracking history for one player."""
    track_id: int
    detections: deque
    positions: deque  # recent image-pixel positions, used for drawing/matching
    velocities: deque
    last_update: float
    total_distance_meters: float
    total_distance_pixels: float
    is_active: bool
    color: Tuple[int, int, int]
    court_positions: deque = field(default_factory=lambda: deque(maxlen=30))
    speeds_mps: deque = field(default_factory=lambda: deque(maxlen=120))
    trajectory_pixels: list = field(default_factory=list)
    trajectory_court: list = field(default_factory=list)
    frame_history: list = field(default_factory=list)
    cumulative_distance_history_m: list = field(default_factory=list)
    cumulative_distance_history_pixels: list = field(default_factory=list)
    last_frame_number: int = 0
    last_court_frame_number: int = 0
    smoothed_court_point: Optional[Tuple[float, float]] = None
    missed_frames: int = 0
    num_detections_total: int = 0
    metric_calibrated: bool = False

    def __post_init__(self):
        self.detections = deque(maxlen=30)
        self.positions = deque(maxlen=30)
        self.velocities = deque(maxlen=120)
        self.court_positions = deque(maxlen=30)
        self.speeds_mps = deque(maxlen=120)

    @property
    def total_distance(self) -> float:
        """Compatibility property; returns metres when calibrated, pixels otherwise."""
        return self.total_distance_meters if self.metric_calibrated else self.total_distance_pixels


class PlayerTracker:
    def __init__(self, model_path: str = 'yolov8x.pt', max_disappeared: int = 30):
        """Initialize YOLO player detection and short-gap player tracking.

        Args:
            model_path: Path to the YOLO model.
            max_disappeared: Maximum number of frames a track may be missing
                before it is removed.
        """
        self.model = YOLO(model_path)
        self.tracks: Dict[int, PlayerTrack] = {}
        self.next_track_id = 0
        self.max_disappeared = max_disappeared
        self.colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 0), (255, 0, 255), (0, 255, 255),
        ]
        self.homography_matrix: Optional[np.ndarray] = None
        self.court_width_m = 10.97
        self.court_length_m = 23.77
        self.fps: Optional[float] = None
        self.match_distance_threshold_pixels = 100.0
        self.sideline_margin_m = 4.0
        self.baseline_margin_m = 8.0
        # Faster apparent movement than this is a detection jump, not running.
        self.max_player_speed_mps = 12.0
        self.court_smoothing_window = 9  # detections averaged for distance

    def set_calibration(
        self,
        homography_matrix: Optional[np.ndarray],
        court_width_m: float = 10.97,
        court_length_m: float = 23.77,
    ) -> None:
        """Set the pixel-to-metre homography used for movement measurements."""
        if homography_matrix is None:
            self.homography_matrix = None
        else:
            matrix = np.asarray(homography_matrix, dtype=np.float64)
            if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
                raise ValueError("homography_matrix must be a finite 3x3 matrix")
            self.homography_matrix = matrix
        self.court_width_m = float(court_width_m)
        self.court_length_m = float(court_length_m)

    def pixel_to_court(
        self, point: Tuple[float, float], homography_matrix: Optional[np.ndarray] = None
    ) -> Optional[Tuple[float, float]]:
        """Convert one image pixel point to court metres, if calibrated."""
        matrix = homography_matrix if homography_matrix is not None else self.homography_matrix
        if matrix is None:
            return None
        pixel_point = np.asarray([[[float(point[0]), float(point[1])]]], dtype=np.float32)
        try:
            transformed = cv2.perspectiveTransform(pixel_point, matrix)
        except cv2.error:
            return None
        x, y = transformed[0, 0]
        if not np.isfinite(x) or not np.isfinite(y):
            return None
        # Reject obviously implausible points so a bad detection outside the
        # calibrated court does not create an enormous false movement distance.
        # Players routinely stand well behind the baseline and outside the
        # sidelines, so allow for the run-off area around the court.
        if not (-self.sideline_margin_m <= x <= self.court_width_m + self.sideline_margin_m and
                -self.baseline_margin_m <= y <= self.court_length_m + self.baseline_margin_m):
            return None
        return float(x), float(y)

    def detect_players(self, frame: np.ndarray, confidence_threshold: float = 0.5) -> List[PlayerDetection]:
        """Detect people and estimate their ground point from bbox bottom-centre."""
        results = self.model(frame, verbose=False)
        detections: List[PlayerDetection] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0].item())
                if class_id != 0:  # COCO person class
                    continue
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].cpu().numpy()]
                confidence = float(box.conf[0].cpu().numpy())
                if confidence < confidence_threshold:
                    continue

                ground_point = ((x1 + x2) / 2.0, y2)
                detections.append(PlayerDetection(
                    bbox=[x1, y1, x2, y2],
                    center=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
                    ground_point=ground_point,
                    confidence=confidence,
                    court_point=self.pixel_to_court(ground_point),
                    class_id=class_id,
                ))
        return detections

    def update_tracks(self, detections: List[PlayerDetection], frame_number: int) -> Dict[int, PlayerTrack]:
        """Match detections to tracks, retaining IDs across short missed gaps."""
        current_time = time.time()
        frame_number = int(frame_number)

        # Build all plausible track/detection matches, then greedily take the
        # shortest distances first so one detection cannot update two tracks.
        candidate_matches = []
        for track_id, track in self.tracks.items():
            frames_missing = frame_number - track.last_frame_number
            if frames_missing > self.max_disappeared or len(track.positions) == 0:
                continue
            last_pos = track.positions[-1]
            for detection_index, detection in enumerate(detections):
                distance_px = euclidean(last_pos, detection.ground_point)
                if distance_px <= self.match_distance_threshold_pixels:
                    candidate_matches.append((distance_px, track_id, detection_index))

        candidate_matches.sort(key=lambda item: item[0])
        matched_tracks = set()
        matched_detections = set()
        for _, track_id, detection_index in candidate_matches:
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            self._update_track(track_id, detections[detection_index], current_time, frame_number)
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)

        # Mark unmatched tracks as temporarily inactive; keep them available for
        # matching until their missing-frame limit is exceeded.
        for track_id, track in list(self.tracks.items()):
            if track_id not in matched_tracks:
                track.missed_frames = frame_number - track.last_frame_number
                track.is_active = False
                if track.missed_frames > self.max_disappeared:
                    del self.tracks[track_id]

        for detection_index, detection in enumerate(detections):
            if detection_index not in matched_detections:
                self._create_new_track(detection, current_time, frame_number)

        return self.tracks

    def _create_new_track(self, detection: PlayerDetection, current_time: float, frame_number: int):
        track_id = self.next_track_id
        self.next_track_id += 1
        color = self.colors[track_id % len(self.colors)]
        track = PlayerTrack(
            track_id=track_id,
            detections=deque(maxlen=30),
            positions=deque(maxlen=30),
            velocities=deque(maxlen=120),
            last_update=current_time,
            total_distance_meters=0.0,
            total_distance_pixels=0.0,
            is_active=True,
            color=color,
            last_frame_number=frame_number,
            metric_calibrated=self.homography_matrix is not None and detection.court_point is not None,
        )
        track.detections.append(detection)
        track.positions.append(detection.ground_point)
        track.trajectory_pixels.append([float(detection.ground_point[0]), float(detection.ground_point[1])])
        track.trajectory_court.append(list(detection.court_point) if detection.court_point is not None else None)
        track.frame_history.append(frame_number)
        track.cumulative_distance_history_m.append(0.0)
        track.cumulative_distance_history_pixels.append(0.0)
        if detection.court_point is not None:
            track.court_positions.append(detection.court_point)
            track.smoothed_court_point = detection.court_point
            track.last_court_frame_number = frame_number
        track.num_detections_total = 1
        track.velocities.append((0.0, 0.0))
        self.tracks[track_id] = track

    def _update_track(self, track_id: int, detection: PlayerDetection, current_time: float, frame_number: int):
        track = self.tracks[track_id]
        previous_pixel = track.positions[-1] if track.positions else detection.ground_point
        distance_pixels = euclidean(detection.ground_point, previous_pixel)
        track.total_distance_pixels += float(distance_pixels)

        if detection.court_point is not None:
            # Measure from the last valid court position, so a frame whose
            # point was rejected does not drop the movement across it.
            court_gap = max(1, frame_number - track.last_court_frame_number)
            court_time_gap = court_gap / self.fps if self.fps is not None and self.fps > 0 else None
            if track.court_positions and court_time_gap is not None:
                raw_step_m = euclidean(detection.court_point, track.court_positions[-1])
                if raw_step_m / court_time_gap > self.max_player_speed_mps:
                    # Detection jump: restart smoothing instead of counting it.
                    track.court_positions.clear()
                    track.smoothed_court_point = None
            track.court_positions.append(detection.court_point)

            # Bounding-box jitter of a pixel or two is worth tens of
            # centimetres near the far baseline; summing it frame by frame
            # inflates the distance, so measure on a short moving average.
            recent = list(track.court_positions)[-self.court_smoothing_window:]
            smoothed = (float(np.mean([p[0] for p in recent])), float(np.mean([p[1] for p in recent])))
            if track.smoothed_court_point is not None:
                previous_court = track.smoothed_court_point
                distance_m = euclidean(smoothed, previous_court)
                track.total_distance_meters += float(distance_m)
                if court_time_gap is not None:
                    vx = (smoothed[0] - previous_court[0]) / court_time_gap
                    vy = (smoothed[1] - previous_court[1]) / court_time_gap
                    track.velocities.append((float(vx), float(vy)))
                    track.speeds_mps.append(float(distance_m / court_time_gap))
            track.smoothed_court_point = smoothed
            track.last_court_frame_number = frame_number
            track.metric_calibrated = True
        else:
            # Do not mix pixel/frame velocities with metric velocities.
            track.velocities.append((0.0, 0.0))

        track.detections.append(detection)
        track.positions.append(detection.ground_point)
        track.trajectory_pixels.append([float(detection.ground_point[0]), float(detection.ground_point[1])])
        track.trajectory_court.append(list(detection.court_point) if detection.court_point is not None else None)
        track.frame_history.append(frame_number)
        track.cumulative_distance_history_m.append(float(track.total_distance_meters))
        track.cumulative_distance_history_pixels.append(float(track.total_distance_pixels))
        track.last_update = current_time
        track.last_frame_number = frame_number
        track.missed_frames = 0
        track.is_active = True
        track.num_detections_total += 1

    def _remove_old_tracks(self, frame_number: int):
        """Remove tracks that have been missing for too many video frames."""
        for track_id in list(self.tracks):
            track = self.tracks[track_id]
            if frame_number - track.last_frame_number > self.max_disappeared:
                del self.tracks[track_id]

    def get_active_tracks(self) -> Dict[int, PlayerTrack]:
        return {track_id: track for track_id, track in self.tracks.items() if track.is_active}

    def get_track_statistics(self) -> Dict[int, Dict]:
        stats: Dict[int, Dict] = {}
        for track_id, track in self.tracks.items():
            if track.num_detections_total < 2:
                continue

            avg_speed_mps = float(np.mean(track.speeds_mps)) if track.speeds_mps else None
            velocities = list(track.velocities)
            avg_velocity = np.mean(velocities, axis=0).tolist() if velocities else [0.0, 0.0]
            calibrated = bool(track.metric_calibrated and self.homography_matrix is not None)
            stats[track_id] = {
                'total_distance_meters': float(track.total_distance_meters) if calibrated else None,
                'total_distance_pixels': float(track.total_distance_pixels),
                'average_speed_meters_per_second': avg_speed_mps if calibrated else None,
                'average_speed_pixels_per_frame': float(track.total_distance_pixels / max(1, track.num_detections_total - 1)),
                'average_velocity': avg_velocity,
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'color': list(track.color),
                'metric_calibrated': calibrated,
            }
        return stats

    def draw_tracks(self, frame: np.ndarray) -> np.ndarray:
        """Draw current detections and recent pixel-coordinate trails."""
        result = frame.copy()
        for track_id, track in self.tracks.items():
            if not track.is_active or not track.positions:
                continue
            if len(track.positions) > 1:
                points = np.asarray(list(track.positions), dtype=np.int32)
                cv2.polylines(result, [points], False, track.color, 2)
            current_pos = track.positions[-1]
            cv2.circle(result, (int(current_pos[0]), int(current_pos[1])), 5, track.color, -1)

            if track.detections:
                latest = track.detections[-1]
                x1, y1, x2, y2 = latest.bbox
                cv2.rectangle(result, (int(x1), int(y1)), (int(x2), int(y2)), track.color, 2)
                if track.metric_calibrated:
                    label = f"ID: {track_id} | Dist: {track.total_distance_meters:.1f} m"
                else:
                    label = f"ID: {track_id} | Dist: {track.total_distance_pixels:.0f} px"
                cv2.putText(result, label, (int(x1), max(20, int(y1) - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, track.color, 2)
        return result

    def save_tracking_data(self, output_file: str):
        """Save full trajectories and explicit metric/pixel statistics to JSON."""
        data = {
            'video_fps': self.fps,
            'court_calibrated': self.homography_matrix is not None,
            'court_dimensions_m': {'width': self.court_width_m, 'length': self.court_length_m},
            'tracks': {},
        }
        for track_id, track in self.tracks.items():
            data['tracks'][str(track_id)] = {
                'track_id': int(track.track_id),
                'trajectory_pixels': track.trajectory_pixels,
                'trajectory_court_meters': track.trajectory_court,
                'frame_numbers': track.frame_history,
                'cumulative_distance_meters': track.cumulative_distance_history_m,
                'cumulative_distance_pixels': track.cumulative_distance_history_pixels,
                'total_distance_meters': float(track.total_distance_meters) if track.metric_calibrated else None,
                'total_distance_pixels': float(track.total_distance_pixels),
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'metric_calibrated': bool(track.metric_calibrated),
                'color': list(track.color),
            }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def process_video(self, video_path: str, output_path: str = None) -> Dict:
        """Process a video, track players, and calculate calibrated movement metrics."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = float(cap.get(cv2.CAP_PROP_FPS))
        self.fps = fps if np.isfinite(fps) and fps > 0 else None
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # A tracker instance can be reused without carrying over previous videos.
        self.tracks = {}
        self.next_track_id = 0

        out_writer = None
        if output_path:
            output_fps = self.fps if self.fps is not None else 30.0
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out_writer = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))
            if not out_writer.isOpened():
                cap.release()
                raise ValueError(f"Could not create output video: {output_path}")

        frame_count = 0
        print("Processing video for player tracking...")
        from tqdm import tqdm
        with tqdm(total=total_frames if total_frames > 0 else None) as pbar:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                detections = self.detect_players(frame)
                self.update_tracks(detections, frame_count)
                result_frame = self.draw_tracks(frame)
                if out_writer is not None:
                    out_writer.write(result_frame)
                frame_count += 1
                pbar.update(1)

        cap.release()
        if out_writer is not None:
            out_writer.release()

        stats = self.get_track_statistics()
        return {
            'total_frames': int(frame_count),
            'video_fps': self.fps,
            'court_calibrated': self.homography_matrix is not None,
            'track_statistics': stats,
        }

# Main function removed - use main.py for application entry point
