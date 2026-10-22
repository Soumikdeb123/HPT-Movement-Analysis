"""Tennis-court detection and perspective mapping.

This module adapts the Hough-line, corner-validation and homography approach
from the team's Yuchen-supplied ``court_detector.py`` prototype.  The detector
adds perspective-aware sideline selection and multi-frame consensus for the
fixed, blue-court client footage.
"""

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


Point = Tuple[float, float]
Line = Tuple[float, float, float, float]


@dataclass
class CourtCalibration:
    """Estimated image-to-standard-court transformation."""

    corners: np.ndarray
    homography: np.ndarray
    confidence: float
    width_metres: float = 10.97
    length_metres: float = 23.77

    def image_to_court(self, point: Point) -> Point:
        source = np.asarray([[point]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(source, self.homography)[0][0]
        return (float(transformed[0]), float(transformed[1]))

    def contains_player_position(
        self,
        point: Point,
        side_margin_metres: float = 2.0,
        baseline_margin_metres: float = 3.5,
    ) -> bool:
        """Allow normal run-off space while rejecting spectators and officials."""

        x, y = self.image_to_court(point)
        return (
            -side_margin_metres <= x <= self.width_metres + side_margin_metres
            and -baseline_margin_metres
            <= y
            <= self.length_metres + baseline_margin_metres
        )

    def as_dict(self) -> Dict:
        return {
            "status": "estimated",
            "method": "multi_frame_hough_homography",
            "confidence": round(self.confidence, 3),
            "courtType": "doubles",
            "widthMeters": self.width_metres,
            "lengthMeters": self.length_metres,
            "cornersImagePixels": self.corners.round(2).tolist(),
            "homography": self.homography.round(8).tolist(),
        }


class CourtDetector:
    """Detect the outer doubles-court sidelines in a fixed-camera frame."""

    court_dimensions = {
        "singles_width": 8.23,
        "singles_length": 23.77,
        "doubles_width": 10.97,
        "doubles_length": 23.77,
    }

    def detect_court_lines(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Use the prototype's Canny + Hough approach within the court region."""

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        # The client video is a fixed rear-court view. Masking the roof and stands
        # prevents their long structural lines from being mistaken for court lines.
        edges[: int(height * 0.48), :] = 0
        return cv2.HoughLinesP(
            edges,
            1,
            np.pi / 360,
            threshold=60,
            minLineLength=max(50, int(width * 0.12)),
            maxLineGap=25,
        )

    @staticmethod
    def filter_court_lines(
        lines: Optional[np.ndarray],
        frame_shape: Sequence[int],
    ) -> Tuple[List[Line], List[Line]]:
        """Return horizontal baselines and perspective-sloped sidelines."""

        if lines is None:
            return ([], [])

        height, _width = frame_shape[:2]
        horizontal: List[Line] = []
        sidelines: List[Line] = []
        for raw_line in lines:
            x1, y1, x2, y2 = (float(value) for value in raw_line[0])
            if x2 < x1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            length = hypot(x2 - x1, y2 - y1)
            angle = degrees(atan2(y2 - y1, x2 - x1))
            if abs(angle) <= 12 and length >= 0.15 * frame_shape[1]:
                horizontal.append((x1, y1, x2, y2))
            elif (
                22 <= abs(angle) <= 55
                and length >= 0.45 * height
                and max(y1, y2) >= 0.82 * height
            ):
                sidelines.append((x1, y1, x2, y2))
        return (horizontal, sidelines)

    def detect_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Find far-left, far-right, near-right and near-left court corners."""

        _horizontal, sidelines = self.filter_court_lines(
            self.detect_court_lines(frame), frame.shape
        )
        negative = [line for line in sidelines if self._line_angle(line) < 0]
        positive = [line for line in sidelines if self._line_angle(line) > 0]
        if not negative or not positive:
            return None

        # The outer doubles sidelines are the longest converging line on each side.
        left = max(negative, key=self._line_length)
        right = max(positive, key=self._line_length)
        left_top, left_bottom = self._top_and_bottom(left)
        right_top, right_bottom = self._top_and_bottom(right)
        corners = np.asarray(
            [left_top, right_top, right_bottom, left_bottom], dtype=np.float32
        )
        return corners if self.validate_court_geometry(corners, frame.shape) else None

    def detect_from_frames(
        self, frames: Iterable[np.ndarray]
    ) -> Optional[CourtCalibration]:
        """Use median corners from several frames to suppress Hough-line noise."""

        frame_list = [frame for frame in frames if frame is not None]
        detections = [
            corners
            for frame in frame_list
            if (corners := self.detect_corners(frame)) is not None
        ]
        if not detections:
            return None

        median_corners = np.median(np.stack(detections), axis=0).astype(np.float32)
        if not self.validate_court_geometry(median_corners, frame_list[0].shape):
            return None

        matrix = self.get_court_transform_matrix(median_corners)
        if matrix is None:
            return None

        frame_diagonal = hypot(frame_list[0].shape[1], frame_list[0].shape[0])
        deviations = [
            float(np.mean(np.linalg.norm(corners - median_corners, axis=1)))
            for corners in detections
        ]
        consistency = 1.0 - min(1.0, float(np.median(deviations)) / (0.05 * frame_diagonal))
        detection_rate = len(detections) / len(frame_list)
        confidence = max(0.0, min(1.0, 0.55 * detection_rate + 0.45 * consistency))
        return CourtCalibration(
            corners=median_corners,
            homography=matrix,
            confidence=confidence,
        )

    def validate_court_geometry(
        self, corners: Optional[np.ndarray], frame_shape: Sequence[int]
    ) -> bool:
        """Reject crossed, tiny, upside-down or off-frame quadrilaterals."""

        if corners is None or corners.shape != (4, 2):
            return False
        height, width = frame_shape[:2]
        far_left, far_right, near_right, near_left = corners
        far_width = far_right[0] - far_left[0]
        near_width = near_right[0] - near_left[0]
        vertical_span = min(near_left[1], near_right[1]) - max(
            far_left[1], far_right[1]
        )
        polygon_area = abs(float(cv2.contourArea(corners)))
        points_inside_extended_frame = all(
            -0.05 * width <= x <= 1.05 * width
            and 0.35 * height <= y <= 1.05 * height
            for x, y in corners
        )
        return (
            points_inside_extended_frame
            and far_width >= 0.08 * width
            and near_width >= 0.45 * width
            and near_width > far_width * 1.8
            and vertical_span >= 0.2 * height
            and polygon_area >= 0.12 * width * height
        )

    def get_court_transform_matrix(
        self, corners: Optional[np.ndarray]
    ) -> Optional[np.ndarray]:
        """Map image pixels to the standard doubles-court dimensions in metres."""

        if corners is None or corners.shape != (4, 2):
            return None
        target_points = np.asarray(
            [
                [0.0, 0.0],
                [self.court_dimensions["doubles_width"], 0.0],
                [
                    self.court_dimensions["doubles_width"],
                    self.court_dimensions["doubles_length"],
                ],
                [0.0, self.court_dimensions["doubles_length"]],
            ],
            dtype=np.float32,
        )
        return cv2.getPerspectiveTransform(corners.astype(np.float32), target_points)

    @staticmethod
    def _line_angle(line: Line) -> float:
        x1, y1, x2, y2 = line
        return degrees(atan2(y2 - y1, x2 - x1))

    @staticmethod
    def _line_length(line: Line) -> float:
        x1, y1, x2, y2 = line
        return hypot(x2 - x1, y2 - y1)

    @staticmethod
    def _top_and_bottom(line: Line) -> Tuple[Point, Point]:
        x1, y1, x2, y2 = line
        return ((x1, y1), (x2, y2)) if y1 <= y2 else ((x2, y2), (x1, y1))
