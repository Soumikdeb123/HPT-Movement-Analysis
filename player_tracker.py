import csv
import math

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
    direction_changes: list = field(default_factory=list)
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
        # A direction change compares the mean heading over the window before
        # a frame with the mean heading over the window after it.
        self.cod_min_angle_deg = 45.0
        # Below this the heading is meaningless (a near-still player's
        # direction swings with every small wobble).
        self.cod_min_speed_mps = 1.0
        self.cod_window_s = 0.3
        # A plant-and-reverse turn may pause this long between moving in and out.
        self.cod_max_pause_s = 1.0
        self.cod_min_interval_s = 0.5  # one turn is not counted twice
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
            segments: List[Dict] = []
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
                trimmed = slice(edge, -edge)
                full_frames, speed, accel = full_frames[trimmed], speed[trimmed], accel[trimmed]
                for frame, s, a in zip(full_frames, speed, accel):
                    speed_by_frame[int(frame)] = float(s)
                    accel_by_frame[int(frame)] = float(a)
                efforts.extend(self._find_deceleration_efforts(full_frames, speed, accel))
                segments.append({
                    'frames': full_frames, 'xs': xs[trimmed], 'ys': ys[trimmed],
                    'vx': vx[trimmed], 'vy': vy[trimmed], 'speed': speed,
                    'measured': set(int(f) for f in frames),
                })

            track.speed_history_mps = [speed_by_frame.get(f) for f in track.frame_history]
            track.acceleration_history_mps2 = [accel_by_frame.get(f) for f in track.frame_history]
            track.deceleration_efforts = efforts
            track.kinematics_by_frame = {f: (speed_by_frame[f], accel_by_frame[f]) for f in speed_by_frame}
            # Turns are found after all efforts, so each can point at the one it overlaps.
            changes: List[Dict] = []
            for segment in segments:
                changes.extend(self._find_direction_changes(segment, efforts))
            for event_id, change in enumerate(changes):
                change['event_id'] = event_id
                change['player_id'] = int(track.track_id)
            track.direction_changes = changes

    def _court_zone(self, x: float, y: float) -> str:
        """Name the court area at (x, y), from the player's own view facing the net.

        Depth is measured from the player's own baseline: behind it, between
        it and the service line (backcourt), or between the service line and
        the net (forecourt). Left/centre/right are thirds of the doubles width.
        """
        length, width = self.court_length_m, self.court_width_m
        near_half = y >= length / 2.0
        depth = (length - y) if near_half else y
        if depth < 0:
            band = 'behind_baseline'
        elif depth < length / 2.0 - 6.40:
            band = 'backcourt'
        else:
            band = 'forecourt'
        # The near player faces away from the camera, so their left is the
        # image's left; the far player faces the camera, so it is reversed.
        if x < width / 3.0:
            side = 'left' if near_half else 'right'
        elif x > 2.0 * width / 3.0:
            side = 'right' if near_half else 'left'
        else:
            side = 'centre'
        return f'{band}_{side}'

    def _find_direction_changes(self, segment: Dict, efforts: List[Dict]) -> List[Dict]:
        """Turns of at least cod_min_angle_deg within one continuous trajectory segment.

        For every frame, the heading the player had when last moving before it
        (mean velocity over a window) is compared with the heading when they
        next move after it. Using the last/next *moving* moment matters for
        plant-and-reverse turns: at the pivot the player is nearly still, so
        the frames right around it carry no usable direction. The pause in
        between may last up to cod_max_pause_s. Each run of frames above the
        angle threshold becomes one event, placed at its sharpest, slowest
        frame.
        """
        frames, vx, vy, speed = segment['frames'], segment['vx'], segment['vy'], segment['speed']
        w = max(1, int(round(self.cod_window_s * self.fps)))
        max_pause = int(round(self.cod_max_pause_s * self.fps))
        n = len(frames)
        if n < 2 * w + 1:
            return []

        moving = speed >= self.cod_min_speed_mps
        last_moving = np.full(n, -1)   # latest moving index at or before i
        next_moving = np.full(n, n)    # earliest moving index at or after i
        for i in range(n):
            last_moving[i] = i if moving[i] else (last_moving[i - 1] if i else -1)
        for i in range(n - 1, -1, -1):
            next_moving[i] = i if moving[i] else (next_moving[i + 1] if i < n - 1 else n)

        angles = np.full(n, np.nan)
        cross = np.zeros(n)
        windows = np.zeros((n, 4), dtype=int)  # before start/end, after start/end (inclusive)
        for i in range(n):
            entry, exit_ = last_moving[i], next_moving[i]
            if entry < 0 or exit_ >= n or exit_ - entry > max_pause:
                continue
            before_start, before_end = entry - w + 1, entry
            after_start, after_end = (exit_ + 1, exit_ + w) if exit_ == entry else (exit_, exit_ + w - 1)
            if before_start < 0 or after_end >= n:
                continue
            before = np.array([vx[before_start:before_end + 1].mean(), vy[before_start:before_end + 1].mean()])
            after = np.array([vx[after_start:after_end + 1].mean(), vy[after_start:after_end + 1].mean()])
            before_norm, after_norm = np.hypot(*before), np.hypot(*after)
            if before_norm < self.cod_min_speed_mps or after_norm < self.cod_min_speed_mps:
                continue
            cosine = np.clip(np.dot(before, after) / (before_norm * after_norm), -1.0, 1.0)
            angles[i] = math.degrees(math.acos(cosine))
            cross[i] = before[0] * after[1] - before[1] * after[0]
            windows[i] = (before_start, before_end, after_start, after_end)

        # One event per run of above-threshold frames: the sharpest frame, and
        # among equally sharp frames (a pause shares one entry/exit) the slowest.
        above = np.nan_to_num(angles, nan=0.0) >= self.cod_min_angle_deg
        turns: List[int] = []
        i = 0
        while i < n:
            if not above[i]:
                i += 1
                continue
            j = i
            while j < n and above[j]:
                j += 1
            sharpest = np.nanmax(angles[i:j])
            candidates = [k for k in range(i, j) if angles[k] >= sharpest - 1.0]
            turns.append(min(candidates, key=lambda k: speed[k]))
            i = j
        # Turns closer together than cod_min_interval_s are one movement:
        # keep the sharper of the two.
        min_gap = int(round(self.cod_min_interval_s * self.fps))
        kept: List[int] = []
        for t in turns:
            if kept and frames[t] - frames[kept[-1]] < min_gap:
                if angles[t] > angles[kept[-1]]:
                    kept[-1] = t
            else:
                kept.append(t)

        changes = []
        for t in kept:
            before_start, before_end, after_start, after_end = windows[t]
            start, end = before_start, after_end
            start_frame, end_frame = int(frames[start]), int(frames[end])
            angle = float(angles[t])
            x, y = float(segment['xs'][t]), float(segment['ys'][t])

            # Court y grows towards the camera, so on this top-down view a
            # positive cross product is a clockwise, i.e. right-hand, turn.
            direction = 'right' if cross[t] > 0 else 'left'
            if angle < 90:
                turn_type = 'cut'
            elif angle < 135:
                turn_type = 'wide'
            else:
                turn_type = 'reversal'

            overlapping = [(k, e) for k, e in enumerate(efforts)
                           if e['start_frame'] <= end_frame and e['end_frame'] >= start_frame]
            effort_index, effort = (max(overlapping, key=lambda item: item[1]['peak_deceleration_mps2'])
                                    if overlapping else (None, None))

            if any(f not in segment['measured'] for f in range(start_frame, end_frame + 1)):
                quality = 'gap'  # part of the window was filled by interpolation
            elif y < self.court_length_m / 2.0:
                quality = 'far_court'  # far side: each pixel spans more court
            else:
                quality = 'good'

            changes.append({
                'start_frame': start_frame,
                'turn_frame': int(frames[t]),
                'end_frame': end_frame,
                'time_s': float(frames[t] / self.fps),
                'court_position_m': [x, y],
                'court_zone': self._court_zone(x, y),
                'turn_angle_deg': angle,
                'turn_direction': direction,
                'turn_type': turn_type,
                'speed_before_mps': float(speed[before_start:before_end + 1].mean()),
                'speed_min_mps': float(speed[start:end + 1].min()),
                'speed_after_mps': float(speed[after_start:after_end + 1].mean()),
                'with_deceleration': effort is not None,
                'deceleration_effort_index': effort_index,
                'peak_deceleration_mps2': float(effort['peak_deceleration_mps2']) if effort else None,
                'data_quality': quality,
            })
        return changes

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
                **self._direction_change_statistics(track.direction_changes, has_kinematics),
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'color': list(track.color),
                'metric_calibrated': calibrated,
            }
        return stats

    @staticmethod
    def _direction_change_statistics(changes: List[Dict], available: bool) -> Dict:
        """Summary counts of one player's direction changes (None when not computable)."""
        if not available:
            return {key: None for key in (
                'direction_changes', 'direction_changes_by_type', 'direction_changes_left',
                'direction_changes_right', 'direction_changes_with_deceleration',
                'average_turn_angle_deg')}
        return {
            'direction_changes': len(changes),
            'direction_changes_by_type': {
                turn_type: sum(1 for c in changes if c['turn_type'] == turn_type)
                for turn_type in ('cut', 'wide', 'reversal')},
            'direction_changes_left': sum(1 for c in changes if c['turn_direction'] == 'left'),
            'direction_changes_right': sum(1 for c in changes if c['turn_direction'] == 'right'),
            'direction_changes_with_deceleration': sum(1 for c in changes if c['with_deceleration']),
            'average_turn_angle_deg': (float(np.mean([c['turn_angle_deg'] for c in changes]))
                                       if changes else None),
        }

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

            # Labels stack upwards above the ID label when there is no room below the box.
            above_y = int(y1) - 30
            kinematics = track.kinematics_by_frame.get(frame_number)
            if kinematics is not None:
                speed, accel = kinematics
                decelerating = accel <= -self.deceleration_threshold_mps2
                text = f"{speed:.1f} m/s  {accel:+.1f} m/s^2"
                if decelerating:
                    text = "DECEL " + text
                if int(y2) + 15 <= result.shape[0] - 5:
                    text_y = int(y2) + 15
                else:
                    text_y, above_y = max(20, above_y), above_y - 20
                self._put_label(result, text, x1, text_y, 0.45,
                                (0, 0, 255) if decelerating else track.color)

            for change in track.direction_changes:
                if change['start_frame'] <= frame_number <= change['end_frame']:
                    text = f"COD {change['turn_angle_deg']:.0f}deg {change['turn_direction'][0].upper()}"
                    self._put_label(result, text, x1, max(20, above_y), 0.5, (0, 165, 255))
                    break
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
                'direction_changes': track.direction_changes,
                'total_distance_meters': float(track.total_distance_meters) if track.metric_calibrated else None,
                'total_distance_pixels': float(track.total_distance_pixels),
                'num_detections': int(track.num_detections_total),
                'is_active': bool(track.is_active),
                'metric_calibrated': bool(track.metric_calibrated),
                'color': list(track.color),
            }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def save_direction_changes_csv(self, output_file: str):
        """One row per direction change, for spreadsheets."""
        columns = ['player_id', 'event_id', 'time_s', 'start_frame', 'turn_frame', 'end_frame',
                   'court_x_m', 'court_y_m', 'court_zone', 'turn_angle_deg', 'turn_direction',
                   'turn_type', 'speed_before_mps', 'speed_min_mps', 'speed_after_mps',
                   'with_deceleration', 'deceleration_effort_index', 'peak_deceleration_mps2',
                   'data_quality']
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for track in self.tracks.values():
                for change in track.direction_changes:
                    row = {key: change.get(key) for key in columns}
                    row['court_x_m'], row['court_y_m'] = change['court_position_m']
                    writer.writerow(row)

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
