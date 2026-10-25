import cv2
import numpy as np
from ultralytics import YOLO
from scipy.spatial.distance import euclidean
from typing import List, Dict, Tuple, Optional
import json
from dataclasses import dataclass, field
from collections import deque


@dataclass
class PlayerDetection:
    """One player detection in image and (when calibrated) court coordinates."""
    bbox: List[float]  # [x1, y1, x2, y2]
    ground_point: Tuple[float, float]  # bottom-centre of bbox in video pixels
    confidence: float
    court_point: Optional[Tuple[float, float]] = None  # (x, y) in metres


@dataclass
class PlayerTrack:
    """Tracking history for one player."""
    track_id: int
    color: Tuple[int, int, int]
    total_distance_meters: float = 0.0
    total_distance_pixels: float = 0.0
    is_active: bool = True
    court_positions: deque = field(default_factory=lambda: deque(maxlen=30))
    trajectory_pixels: list = field(default_factory=list)
    trajectory_court: list = field(default_factory=list)
    frame_history: list = field(default_factory=list)
    cumulative_distance_history_m: list = field(default_factory=list)
    cumulative_distance_history_pixels: list = field(default_factory=list)
    bbox_history: list = field(default_factory=list)
    # Filled by PlayerTracker.compute_kinematics(), aligned with frame_history.
    speed_history_mps: list = field(default_factory=list)
    acceleration_history_mps2: list = field(default_factory=list)
    deceleration_efforts: list = field(default_factory=list)
    kinematics_by_frame: dict = field(default_factory=dict)  # frame -> (speed, accel)
    last_frame_number: int = 0
    last_court_frame_number: int = 0
    smoothed_court_point: Optional[Tuple[float, float]] = None
    missed_frames: int = 0
    num_detections_total: int = 0
    metric_calibrated: bool = False

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
        # Speed/acceleration are differentiated from the full trajectory with
        # a Savitzky-Golay filter; differencing frame to frame is pure noise.
        self.kinematics_window_s = 0.7
        self.kinematics_max_gap_frames = 5  # longer gaps split the trajectory
        self.deceleration_threshold_mps2 = 2.0
        self.high_intensity_deceleration_mps2 = 3.0
        self.min_deceleration_duration_s = 0.2
        self.removed_tracks: Dict[int, PlayerTrack] = {}
        self.inference_size = 640  # set per video; never upscale small videos

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
        # Let YOLO filter to the person class (COCO 0) and confidence itself.
        boxes = self.model(frame, verbose=False, classes=[0], conf=confidence_threshold,
                           imgsz=self.inference_size)[0].boxes
        detections: List[PlayerDetection] = []
        for (x1, y1, x2, y2), confidence in zip(boxes.xyxy.cpu().numpy().tolist(),
                                                boxes.conf.cpu().numpy().tolist()):
            ground_point = ((x1 + x2) / 2.0, y2)
            detections.append(PlayerDetection(
                bbox=[x1, y1, x2, y2],
                ground_point=ground_point,
                confidence=confidence,
                court_point=self.pixel_to_court(ground_point),
            ))
        return detections

    def update_tracks(self, detections: List[PlayerDetection], frame_number: int) -> Dict[int, PlayerTrack]:
        """Match detections to tracks, retaining IDs across short missed gaps."""
        frame_number = int(frame_number)

        # Build all plausible track/detection matches, then greedily take the
        # shortest distances first so one detection cannot update two tracks.
        candidate_matches = []
        for track_id, track in self.tracks.items():
            frames_missing = frame_number - track.last_frame_number
            if frames_missing > self.max_disappeared:
                continue
            last_pos = track.trajectory_pixels[-1]
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
            self._update_track(track_id, detections[detection_index], frame_number)
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)

        # Mark unmatched tracks as temporarily inactive; keep them available for
        # matching until their missing-frame limit is exceeded.
        for track_id, track in list(self.tracks.items()):
            if track_id not in matched_tracks:
                track.missed_frames = frame_number - track.last_frame_number
                track.is_active = False
                if track.missed_frames > self.max_disappeared:
                    # Keep it aside: the rendered video still needs its kinematics.
                    self.removed_tracks[track_id] = self.tracks.pop(track_id)

        for detection_index, detection in enumerate(detections):
            if detection_index not in matched_detections:
                self._create_new_track(detection, frame_number)

        return self.tracks

    def _create_new_track(self, detection: PlayerDetection, frame_number: int):
        track_id = self.next_track_id
        self.next_track_id += 1
        track = PlayerTrack(
            track_id=track_id,
            color=self.colors[track_id % len(self.colors)],
            last_frame_number=frame_number,
            metric_calibrated=self.homography_matrix is not None and detection.court_point is not None,
        )
        track.trajectory_pixels.append([float(detection.ground_point[0]), float(detection.ground_point[1])])
        track.trajectory_court.append(list(detection.court_point) if detection.court_point is not None else None)
        track.frame_history.append(frame_number)
        track.bbox_history.append([float(v) for v in detection.bbox])
        track.cumulative_distance_history_m.append(0.0)
        track.cumulative_distance_history_pixels.append(0.0)
        if detection.court_point is not None:
            track.court_positions.append(detection.court_point)
            track.smoothed_court_point = detection.court_point
            track.last_court_frame_number = frame_number
        track.num_detections_total = 1
        self.tracks[track_id] = track

    def _update_track(self, track_id: int, detection: PlayerDetection, frame_number: int):
        track = self.tracks[track_id]
        distance_pixels = euclidean(detection.ground_point, track.trajectory_pixels[-1])
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
                track.total_distance_meters += float(euclidean(smoothed, track.smoothed_court_point))
            track.smoothed_court_point = smoothed
            track.last_court_frame_number = frame_number
            track.metric_calibrated = True

        track.trajectory_pixels.append([float(detection.ground_point[0]), float(detection.ground_point[1])])
        track.trajectory_court.append(list(detection.court_point) if detection.court_point is not None else None)
        track.frame_history.append(frame_number)
        track.bbox_history.append([float(v) for v in detection.bbox])
        track.cumulative_distance_history_m.append(float(track.total_distance_meters))
        track.cumulative_distance_history_pixels.append(float(track.total_distance_pixels))
        track.last_frame_number = frame_number
        track.missed_frames = 0
        track.is_active = True
        track.num_detections_total += 1

    def _kinematic_segments(self, track: PlayerTrack) -> List[Tuple[List[int], List]]:
        """Split a track's valid court points into continuous (frames, points) runs.

        A run ends at a long detection gap or at a jump faster than any player
        can move (an ID switch), so the filter never smooths across either.
        """
        segments = []
        frames: List[int] = []
        points: List = []
        for frame, point in zip(track.frame_history, track.trajectory_court):
            if point is None:
                continue
            if frames:
                gap = frame - frames[-1]
                step_speed = euclidean(point, points[-1]) * self.fps / gap
                if gap > self.kinematics_max_gap_frames or step_speed > self.max_player_speed_mps:
                    segments.append((frames, points))
                    frames, points = [], []
            frames.append(frame)
            points.append(point)
        if frames:
            segments.append((frames, points))
        return segments

    def _find_deceleration_efforts(self, frames: np.ndarray, speed: np.ndarray,
                                   accel: np.ndarray) -> List[Dict]:
        """Runs where acceleration stays at or below -threshold for long enough."""
        min_frames = max(1, int(round(self.min_deceleration_duration_s * self.fps)))
        below = accel <= -self.deceleration_threshold_mps2
        efforts = []
        i = 0
        while i < len(below):
            if not below[i]:
                i += 1
                continue
            j = i
            while j < len(below) and below[j]:
                j += 1
            if j - i >= min_frames:
                peak = float(-accel[i:j].min())
                efforts.append({
                    'start_frame': int(frames[i]),
                    'end_frame': int(frames[j - 1]),
                    'duration_s': float((j - i) / self.fps),
                    'peak_deceleration_mps2': peak,
                    'mean_deceleration_mps2': float(-accel[i:j].mean()),
                    'speed_start_mps': float(speed[i]),
                    'speed_end_mps': float(speed[j - 1]),
                    'high_intensity': bool(peak >= self.high_intensity_deceleration_mps2),
                })
            i = j
        return efforts

    def compute_kinematics(self) -> None:
        """Compute per-frame speed, acceleration and deceleration efforts.

        Runs after tracking so the filter can be centred on each frame (no
        lag). Positions are median-filtered to drop single-frame bbox glitches,
        then a Savitzky-Golay filter gives velocity, and a second one the rate
        of change of speed. Negative acceleration is deceleration.
        """
        from scipy.ndimage import median_filter
        from scipy.signal import savgol_filter

        if self.fps is None or self.homography_matrix is None:
            return
        dt = 1.0 / self.fps
        window = max(5, int(round(self.kinematics_window_s * self.fps)) | 1)
        # Near a segment's ends the filter extrapolates rather than smooths,
        # which shows up as fake deceleration spikes; drop those frames.
        edge = window // 2

        for track in list(self.tracks.values()) + list(self.removed_tracks.values()):
            speed_by_frame: Dict[int, float] = {}
            accel_by_frame: Dict[int, float] = {}
            efforts: List[Dict] = []
            for frames, points in self._kinematic_segments(track):
                if frames[-1] - frames[0] + 1 < window + 2 * edge:
                    continue
                # Fill short missed-detection gaps so sampling is uniform.
                full_frames = np.arange(frames[0], frames[-1] + 1)
                points = np.asarray(points, dtype=np.float64)
                xs = np.interp(full_frames, frames, points[:, 0])
                ys = np.interp(full_frames, frames, points[:, 1])
                xs = median_filter(xs, size=5, mode='nearest')
                ys = median_filter(ys, size=5, mode='nearest')
                vx = savgol_filter(xs, window, 2, deriv=1, delta=dt)
                vy = savgol_filter(ys, window, 2, deriv=1, delta=dt)
                speed = np.hypot(vx, vy)
                accel = savgol_filter(speed, window, 2, deriv=1, delta=dt)
                full_frames, speed, accel = full_frames[edge:-edge], speed[edge:-edge], accel[edge:-edge]
                for frame, s, a in zip(full_frames, speed, accel):
                    speed_by_frame[int(frame)] = float(s)
                    accel_by_frame[int(frame)] = float(a)
                efforts.extend(self._find_deceleration_efforts(full_frames, speed, accel))

            track.speed_history_mps = [speed_by_frame.get(f) for f in track.frame_history]
            track.acceleration_history_mps2 = [accel_by_frame.get(f) for f in track.frame_history]
            track.deceleration_efforts = efforts
            track.kinematics_by_frame = {f: (speed_by_frame[f], accel_by_frame[f]) for f in speed_by_frame}

    def get_track_statistics(self) -> Dict[int, Dict]:
        stats: Dict[int, Dict] = {}
        for track_id, track in self.tracks.items():
            if track.num_detections_total < 2:
                continue

            calibrated = bool(track.metric_calibrated and self.homography_matrix is not None)
            speeds = [s for s in track.speed_history_mps if s is not None]
            accelerations = [a for a in track.acceleration_history_mps2 if a is not None]
            efforts = track.deceleration_efforts
            has_kinematics = calibrated and bool(accelerations)
            stats[track_id] = {
                'total_distance_meters': float(track.total_distance_meters) if calibrated else None,
                'total_distance_pixels': float(track.total_distance_pixels),
                'average_speed_meters_per_second': float(np.mean(speeds)) if has_kinematics else None,
                'average_speed_pixels_per_frame': float(track.total_distance_pixels / max(1, track.num_detections_total - 1)),
                'max_deceleration_mps2': float(max(0.0, -min(accelerations))) if has_kinematics else None,
                'deceleration_efforts': len(efforts) if has_kinematics else None,
                'high_intensity_deceleration_efforts': (
                    sum(1 for e in efforts if e['high_intensity']) if has_kinematics else None),
                'average_peak_deceleration_mps2': (
                    float(np.mean([e['peak_deceleration_mps2'] for e in efforts]))
                    if has_kinematics and efforts else None),
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'color': list(track.color),
                'metric_calibrated': calibrated,
            }
        return stats

    def _build_frame_index(self) -> Dict[int, List[Tuple[PlayerTrack, int]]]:
        """Map each frame number to the (track, history index) pairs seen in it."""
        index: Dict[int, List[Tuple[PlayerTrack, int]]] = {}
        for track in list(self.tracks.values()) + list(self.removed_tracks.values()):
            for i, frame in enumerate(track.frame_history):
                index.setdefault(frame, []).append((track, i))
        return index

    def render_frame(self, frame: np.ndarray, frame_number: int,
                     frame_index: Dict[int, List[Tuple[PlayerTrack, int]]]) -> np.ndarray:
        """Draw tracks as they were at ``frame_number``, plus speed/deceleration."""
        result = frame.copy()
        for track, i in frame_index.get(frame_number, []):
            trail = track.trajectory_pixels[max(0, i - 29):i + 1]
            if len(trail) > 1:
                cv2.polylines(result, [np.asarray(trail, dtype=np.int32)], False, track.color, 2)
            x, y = trail[-1]
            cv2.circle(result, (int(x), int(y)), 5, track.color, -1)

            x1, y1, x2, y2 = track.bbox_history[i]
            cv2.rectangle(result, (int(x1), int(y1)), (int(x2), int(y2)), track.color, 2)
            if track.metric_calibrated:
                label = f"ID: {track.track_id} | Dist: {track.cumulative_distance_history_m[i]:.1f} m"
            else:
                label = f"ID: {track.track_id} | Dist: {track.cumulative_distance_history_pixels[i]:.0f} px"
            self._put_label(result, label, x1, max(20, int(y1) - 10), 0.5, track.color)

            kinematics = track.kinematics_by_frame.get(frame_number)
            if kinematics is not None:
                speed, accel = kinematics
                decelerating = accel <= -self.deceleration_threshold_mps2
                text = f"{speed:.1f} m/s  {accel:+.1f} m/s^2"
                if decelerating:
                    text = "DECEL " + text
                # Below the box, or above the ID label when the box reaches the frame bottom.
                text_y = int(y2) + 15 if int(y2) + 15 <= result.shape[0] - 5 else max(20, int(y1) - 30)
                self._put_label(result, text, x1, text_y, 0.45,
                                (0, 0, 255) if decelerating else track.color)
        return result

    @staticmethod
    def _put_label(image: np.ndarray, text: str, x: float, y: int, scale: float,
                   color: Tuple[int, int, int]) -> None:
        """Draw text at (x, y), shifted left if it would run off the right edge."""
        (text_width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        x = int(max(0, min(x, image.shape[1] - text_width - 2)))
        cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)

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
                'speed_mps': track.speed_history_mps,
                'acceleration_mps2': track.acceleration_history_mps2,
                'deceleration_efforts': track.deceleration_efforts,
                'total_distance_meters': float(track.total_distance_meters) if track.metric_calibrated else None,
                'total_distance_pixels': float(track.total_distance_pixels),
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'metric_calibrated': bool(track.metric_calibrated),
                'color': list(track.color),
            }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def _write_annotated_video(self, video_path: str, output_path: str, width: int, height: int):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        output_fps = self.fps if self.fps is not None else 30.0
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))
        if not out_writer.isOpened():
            cap.release()
            raise ValueError(f"Could not create output video: {output_path}")

        frame_index = self._build_frame_index()
        frame_number = 0
        print("Rendering annotated video...")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            out_writer.write(self.render_frame(frame, frame_number, frame_index))
            frame_number += 1
        cap.release()
        out_writer.release()

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
        # YOLO's default 640 input upscales small videos, costing time for no
        # extra detail; use the native size (rounded up to YOLO's stride of 32).
        self.inference_size = min(640, -(-max(width, height) // 32) * 32) if width and height else 640

        # A tracker instance can be reused without carrying over previous videos.
        self.tracks = {}
        self.removed_tracks = {}
        self.next_track_id = 0

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
                frame_count += 1
                pbar.update(1)
        cap.release()

        # Deceleration needs the whole trajectory, so the annotated video is
        # rendered in a second pass once kinematics are known.
        self.compute_kinematics()
        if output_path:
            self._write_annotated_video(video_path, output_path, width, height)

        stats = self.get_track_statistics()
        return {
            'total_frames': int(frame_count),
            'video_fps': self.fps,
            'court_calibrated': self.homography_matrix is not None,
            'track_statistics': stats,
        }

# Main function removed - use main.py for application entry point
