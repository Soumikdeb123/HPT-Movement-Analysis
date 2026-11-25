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
from .yuchen_court_detector import CourtDetector as YuchenCourtDetector


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
    method: str = "automatic_multi_frame"
    limitations: str = (
        "Fixed-camera court mapping. Confidence measures repeatability, not "
        "laboratory-verified metric accuracy."
    )

    def image_to_court(self, point: Point) -> Point:
        source = np.asarray([[point]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(source, self.homography)[0][0]
        return (float(transformed[0]), float(transformed[1]))

    def contains_player_position(
        self,
        point: Point,
        side_margin_metres: float = 4.0,
        baseline_margin_metres: float = 8.0,
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
            "method": self.method,
            "limitations": self.limitations,
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
        """Use Yuchen's physical line intersections, not Hough segment endpoints."""
        corners = YuchenCourtDetector().detect_court_corners_perspective(frame)
        if corners is not None:
            corners = np.asarray(corners, dtype=np.float32)
        return corners if self.validate_automatic_court_geometry(corners, frame.shape) else None

    def detect_from_frames(
        self, frames: Iterable[np.ndarray]
    ) -> Optional[CourtCalibration]:
        """Choose Yuchen's best model-supported fit, retaining geometry checks."""

        frame_list = [frame for frame in frames if frame is not None]
        scored = []
        detector = YuchenCourtDetector()
        for frame_index, frame in enumerate(frame_list):
            for corners, score in detector.detect_court_candidates(frame):
                corners = np.asarray(corners, dtype=np.float32)
                if self.validate_automatic_court_geometry(corners, frame.shape):
                    scored.append((score, corners, frame_index))
        if not scored:
            return None

        # Build geometry clusters across frames.  This prevents a high-scoring
        # one-frame reflection, net or neighbouring court from winning over a
        # slightly weaker court fit that repeats throughout the video.
        frame_diagonal = hypot(frame_list[0].shape[1], frame_list[0].shape[0])
        clusters = []
        for score, corners, frame_index in sorted(scored, key=lambda item: -item[0]):
            for cluster in clusters:
                centre = np.median(
                    np.stack([item[1] for item in cluster]), axis=0
                )
                deviation = float(np.mean(np.linalg.norm(corners - centre, axis=1)))
                # Keep single- and doubles-sideline fits separate.  In an
                # oblique view they can differ by only a few dozen pixels; the
                # previous 5.5% tolerance merged them and then retained the
                # higher raw white-pixel score, even when it was the inner
                # singles court.  A fixed camera should repeat its true corner
                # intersections much more tightly than this.
                if deviation <= 0.025 * frame_diagonal:
                    # Keep at most one candidate per sampled frame in a cluster.
                    previous = next(
                        (item for item in cluster if item[2] == frame_index), None
                    )
                    if previous is None:
                        cluster.append((score, corners, frame_index))
                    elif score > previous[0]:
                        cluster.remove(previous)
                        cluster.append((score, corners, frame_index))
                    break
            else:
                clusters.append([(score, corners, frame_index)])

        minimum_consensus = max(2, int(np.ceil(0.4 * len(frame_list))))
        consensus_clusters = [
            cluster
            for cluster in clusters
            if len({item[2] for item in cluster}) >= minimum_consensus
        ]
        if not consensus_clusters:
            return None

        def cluster_rank(cluster):
            frame_count = len({item[2] for item in cluster})
            median_score = float(np.median([item[0] for item in cluster]))
            detection_rate = frame_count / len(frame_list)
            # One extra noisy frame must not outweigh substantially stronger
            # tennis-line evidence.  This matters for edited match footage,
            # where overlays or a player can hide a real corner in one sample
            # while a neighbouring-court polygon remains visible.  A 40%
            # minimum above still prevents a one-frame high score from winning.
            return median_score * (0.70 + 0.30 * detection_rate)

        winning_cluster = max(consensus_clusters, key=cluster_rank)
        detections = [item[1] for item in winning_cluster]
        median_corners = np.median(np.stack(detections), axis=0).astype(np.float32)
        # The coordinate-wise median is useful for measuring cluster
        # consistency, but it can create a synthetic quadrilateral that never
        # actually aligned with the painted lines in any sampled frame.  That
        # small corner error becomes large when an off-screen corner is
        # extrapolated.  Use the strongest real observation from the stable
        # cluster for the homography instead.
        _best_score, selected_corners, _frame_index = max(
            winning_cluster, key=lambda item: item[0]
        )
        selected_corners = selected_corners.astype(np.float32)
        if not self.validate_automatic_court_geometry(
            selected_corners, frame_list[0].shape
        ):
            return None

        matrix = self.get_court_transform_matrix(selected_corners)
        if matrix is None:
            return None

        deviations = [
            float(np.mean(np.linalg.norm(corners - median_corners, axis=1)))
            for corners in detections
        ]
        consistency = 1.0 - min(1.0, float(np.median(deviations)) / (0.05 * frame_diagonal))
        detection_rate = len({item[2] for item in winning_cluster}) / len(frame_list)
        confidence = max(0.0, min(1.0, 0.55 * detection_rate + 0.45 * consistency))
        return CourtCalibration(
            corners=selected_corners,
            homography=matrix,
            confidence=confidence,
        )

    def validate_court_geometry(
        self, corners: Optional[np.ndarray], frame_shape: Sequence[int]
    ) -> bool:
        """Reject crossed, tiny, upside-down or off-frame quadrilaterals."""

        if corners is None or corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
            return False
        height, width = frame_shape[:2]
        far_left, far_right, near_right, near_left = corners
        far_width = far_right[0] - far_left[0]
        near_width = near_right[0] - near_left[0]
        vertical_span = min(near_left[1], near_right[1]) - max(
            far_left[1], far_right[1]
        )
        polygon_area = abs(float(cv2.contourArea(corners)))
        # An off-centre phone can crop one doubles alley while still showing
        # enough singles/service lines to recover the physical court.  Permit
        # modest extrapolation outside the image; the model-support and
        # multi-frame checks still have to pass before metres are reported.
        points_inside_extended_frame = all(
            -0.25 * width <= x <= 1.25 * width
            and 0.02 * height <= y <= 1.12 * height
            for x, y in corners
        )
        return (
            points_inside_extended_frame
            and far_width >= 0.08 * width
            and near_width >= 0.45 * width
            and near_width > far_width * 1.1
            and vertical_span >= 0.2 * height
            and polygon_area >= 0.12 * width * height
        )

    def validate_automatic_court_geometry(
        self, corners: Optional[np.ndarray], frame_shape: Sequence[int]
    ) -> bool:
        """Fail closed when an automatic fit may use a service line as a baseline.

        The supported capture workflow places a fixed camera behind one end of
        the court.  In that view at least one near doubles-court corner reaches
        the lower portion of the image.  A smaller projected rectangle can
        otherwise score very well by treating advertising/fence markings as
        the far baseline and a service line as the near baseline.  Such a fit
        looks plausible but makes every metre-based result wrong, so it is
        safer to withhold automatic calibration and request four manual court
        points when this depth evidence is absent.

        This restriction is intentionally automatic-only.  A user-confirmed
        manual mapping still uses the general geometry validation above.
        """

        if not self.validate_court_geometry(corners, frame_shape):
            return False
        height = frame_shape[0]
        near_right, near_left = corners[2], corners[3]
        return max(float(near_right[1]), float(near_left[1])) >= 0.685 * height

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
        matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), target_points)
        if not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-12:
            return None
        return matrix

    def calibration_from_normalized_corners(
        self,
        normalized_corners: Sequence[Sequence[float]],
        frame_shape: Sequence[int],
    ) -> CourtCalibration:
        """Build a metric mapping from four user-confirmed doubles corners.

        Points are ordered far-left, far-right, near-right, near-left and are
        normalised to the displayed video size. Geometry checks fail closed so
        an accidental tap order cannot silently create plausible-looking metres.
        """

        values = np.asarray(normalized_corners, dtype=np.float32)
        if values.shape != (4, 2) or not np.all(np.isfinite(values)):
            raise ValueError("Manual court calibration requires exactly four valid points.")
        if np.any(values < 0.0) or np.any(values > 1.0):
            raise ValueError("Manual court points must stay inside the video frame.")
        height, width = frame_shape[:2]
        corners = values * np.asarray([width, height], dtype=np.float32)
        if not self.validate_court_geometry(corners, frame_shape):
            raise ValueError(
                "The selected court corners are not in the expected order or do "
                "not cover enough of the doubles court."
            )
        matrix = self.get_court_transform_matrix(corners)
        if matrix is None:
            raise ValueError("The selected court corners cannot form a stable court map.")
        return CourtCalibration(
            corners=corners,
            homography=matrix,
            confidence=1.0,
            method="manual_user_confirmed_doubles_corners",
            limitations=(
                "Four doubles-court corners were selected by the user. Metric "
                "accuracy depends on placing each point on the painted line "
                "intersection and keeping the camera fixed."
            ),
        )

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
