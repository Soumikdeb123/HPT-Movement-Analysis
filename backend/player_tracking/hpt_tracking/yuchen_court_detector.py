import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict
import math

class CourtDetector:
    def __init__(self):
        """
        Initialize the tennis court detector
        """
        self.court_dimensions = {
            'singles_width': 8.23,  # meters
            'singles_length': 23.77,  # meters
            'doubles_width': 10.97,  # meters
            'doubles_length': 23.77   # meters
        }
        
    def line_intersection(self, line1: np.ndarray, line2: np.ndarray) -> Optional[Tuple[float, float]]:
        """
        Calculate intersection point of two lines
        """
        x1, y1, x2, y2 = line1
        x3, y3, x4, y4 = line2
        
        denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        
        if abs(denominator) < 1e-10:  # Lines are parallel
            return None
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
        
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        
        return (x, y)

    @staticmethod
    def _white_line_mask(frame: np.ndarray) -> np.ndarray:
        """Binary mask of court-line pixels.

        Court lines are thin structures that are clearly whiter than the
        surface around them. "Whiteness" is brightness minus saturation, and
        only its contrast with the surroundings (morphological top-hat) is
        used, so it works on dark and light courts alike. A line next to a
        light-blue apron is barely brighter than it, but far less saturated.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        saturation, value = hsv[..., 1], hsv[..., 2]
        whiteness = np.clip(value.astype(np.int16) - saturation.astype(np.int16), 0, 255).astype(np.uint8)
        kernel_size = max(7, (frame.shape[0] // 40) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        tophat = cv2.morphologyEx(whiteness, cv2.MORPH_TOPHAT, kernel)
        return ((tophat > 25) & (saturation < 100)).astype(np.uint8) * 255

    @staticmethod
    def _x_at_y(line: Tuple[float, float, float, float], y: float) -> float:
        x1, y1, x2, y2 = line
        return x1 + (y - y1) * (x2 - x1) / (y2 - y1)

    def _sideline_candidates(self, mask: np.ndarray, max_per_side: int = 18):
        """Slanted line candidates for the left/right sidelines, strongest first.

        Each entry is (x1, y1, x2, y2). Segments lying on the same line are
        grouped and the groups ranked by total length: sidelines are long,
        continuous lines, while seats, boards and roof beams tend to be
        broken into short pieces.
        """
        height, width = mask.shape[:2]
        min_length = max(30, int(0.15 * height))
        lines = cv2.HoughLinesP(mask, 1, np.pi / 360, threshold=34,
                                minLineLength=min_length, maxLineGap=24)
        if lines is None:
            return [], []

        left_candidates, right_candidates = [], []
        for x1, y1, x2, y2 in lines[:, 0].astype(np.float64):
            if y1 == y2:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
            # In a behind-the-baseline view the sidelines slant towards a
            # vanishing point above the court. Near-vertical lines (overlay
            # borders, posts) and near-horizontal lines are not sidelines.
            if 8 <= angle <= 88:
                right_candidates.append((x1, y1, x2, y2))
            elif 92 <= angle <= 172:
                left_candidates.append((x1, y1, x2, y2))

        reference_y = height - 1

        def strongest_lines(candidates):
            groups = []  # [x at reference_y, angle, total length, longest segment]
            for line in candidates:
                x1, y1, x2, y2 = line
                x = self._x_at_y(line, reference_y)
                angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
                length = math.hypot(x2 - x1, y2 - y1)
                for group in groups:
                    if abs(group[0] - x) <= 0.02 * width and abs(group[1] - angle) <= 3:
                        group[2] += length
                        if length > math.hypot(group[3][2] - group[3][0], group[3][3] - group[3][1]):
                            group[3] = line
                        break
                else:
                    groups.append([x, angle, length, line])
            groups.sort(key=lambda g: -g[2])
            return [g[3] for g in groups[:max_per_side]]

        return strongest_lines(left_candidates), strongest_lines(right_candidates)

    @staticmethod
    def _line_y_at_x(line, x: float) -> float:
        x1, y1, x2, y2 = line
        if abs(x2 - x1) < 1e-9:
            return (y1 + y2) / 2.0
        return y1 + (x - x1) * (y2 - y1) / (x2 - x1)

    def _cross_line_candidates(self, mask: np.ndarray, max_candidates: int = 24):
        """Return long baseline/service-line candidates, including broken lines.

        The earlier detector searched for rows that were almost completely
        white.  A player, watermark or worn clay line can easily break that
        assumption.  Hough segments are grouped by image slope and vertical
        position, then refitted through all their pixels so an interrupted
        court line remains a usable candidate.
        """

        height, width = mask.shape[:2]
        lines = cv2.HoughLinesP(
            mask,
            1,
            np.pi / 360,
            threshold=28,
            minLineLength=max(45, int(width * 0.08)),
            maxLineGap=max(18, int(width * 0.035)),
        )
        if lines is None:
            return []

        groups = []
        centre_x = width / 2.0
        for x1, y1, x2, y2 in lines[:, 0].astype(np.float64):
            if x2 < x1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            length = math.hypot(x2 - x1, y2 - y1)
            # Rear-court cameras can be visibly rolled or mounted well to one
            # side, hence a wider range than the old +/-12 degree filter.
            if abs(angle) > 24 or length < 0.08 * width:
                continue
            centre_y = self._line_y_at_x((x1, y1, x2, y2), centre_x)
            if not (0.12 * height <= centre_y <= 1.03 * height):
                continue
            for group in groups:
                if (
                    abs(group["centre_y"] - centre_y) <= 0.018 * height
                    and abs(group["angle"] - angle) <= 3.5
                ):
                    group["segments"].append((x1, y1, x2, y2))
                    group["support"] += length
                    total = group["support"]
                    weight = length / total
                    group["centre_y"] = (1.0 - weight) * group["centre_y"] + weight * centre_y
                    group["angle"] = (1.0 - weight) * group["angle"] + weight * angle
                    break
            else:
                groups.append({
                    "centre_y": centre_y,
                    "angle": angle,
                    "support": length,
                    "segments": [(x1, y1, x2, y2)],
                })

        candidates = []
        for group in groups:
            points = []
            for x1, y1, x2, y2 in group["segments"]:
                points.extend(((x1, y1), (x2, y2)))
            if len(points) < 2:
                continue
            vx, vy, cx, cy = cv2.fitLine(
                np.asarray(points, dtype=np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01
            ).ravel()
            line = (
                float(cx - vx * width),
                float(cy - vy * width),
                float(cx + vx * width),
                float(cy + vy * width),
            )
            candidates.append((line, float(group["support"])))
        candidates.sort(key=lambda item: -item[1])
        return candidates[:max_candidates]

    def detect_court_corners_perspective(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Detect the four doubles-court corners in a behind-the-baseline view.

        1. Hough lines on a white-pixel mask give the outermost slanted lines,
           which are the doubles sidelines.
        2. Scanning rows between those sidelines upwards from the bottom, the
           first almost fully white row is the near baseline and the next
           mostly white row is the near service line.
        3. Those four line intersections fix a homography; the far corners
           are extrapolated from it. The far baseline itself is often too
           small and blurry to detect directly.
        Other slanted lines (a roof frame, advertising boards, a neighbouring
        court) can look like sidelines, so every candidate pair is tried and
        each resulting court is scored by how well the full court-line model
        projected through it lines up with the detected line pixels.
        Returns corners ordered top-left, top-right, bottom-right, bottom-left,
        or None if no plausible court is found.
        """
        return self.detect_court_with_score(frame)[0]

    def detect_court_with_score(self, frame: np.ndarray) -> Tuple[Optional[np.ndarray], int]:
        """Like detect_court_corners_perspective, also returning the model score.

        The score is the number of court-line pixels the fit explains; use it
        to compare detections of the same video, e.g. across frames.
        """
        candidates = self.detect_court_candidates(frame, limit=1)
        return candidates[0] if candidates else (None, 0)

    def detect_court_candidates(
        self, frame: np.ndarray, limit: int = 24
    ) -> List[Tuple[np.ndarray, int]]:
        """Return multiple model-supported fits, best first.

        The integration layer applies stricter physical geometry checks and
        multi-frame consensus.  Returning alternatives is important: the
        highest raw white-pixel score can belong to a net, fence or adjacent
        court even though a slightly lower-scoring valid court is present.
        """

        mask = self._white_line_mask(frame)
        support = cv2.dilate(mask, np.ones((3, 3), np.uint8))
        left_candidates, right_candidates = self._sideline_candidates(mask)
        cross_candidates = self._cross_line_candidates(mask)
        scored = []
        for left in left_candidates:
            for right in right_candidates:
                candidates = []
                row_candidate = self._corners_from_sidelines(mask, left, right)
                if row_candidate is not None:
                    candidates.append(row_candidate)
                candidates.extend(
                    self._corners_from_cross_candidates(
                        support, left, right, cross_candidates
                    )
                )
                for corners in candidates:
                    matched, fraction = self._court_model_score(support, corners)
                    # Occlusion and worn lines make 50% unnecessarily strict.
                    # Geometry validation and multi-frame consensus provide the
                    # other safeguards; this threshold rejects random clutter.
                    if fraction < 0.28:
                        continue
                    segment_fractions = self._court_model_segment_fractions(
                        support, corners
                    )
                    # A tennis court has four long parallel lines: two doubles
                    # sidelines and two singles sidelines.  Requiring support
                    # from several of them stops an asymmetric fit that uses a
                    # singles line on one side and a doubles line on the other.
                    longitudinal = segment_fractions[2:6]
                    cross_court = (
                        segment_fractions[0:2] + segment_fractions[6:8]
                    )
                    if (
                        sorted(longitudinal, reverse=True)[2] < 0.16
                        or sorted(cross_court, reverse=True)[1] < 0.15
                    ):
                        continue
                    height, width = mask.shape[:2]
                    area = abs(float(cv2.contourArea(corners.astype(np.float32))))
                    # Once line structure is plausible, favour the outer court
                    # boundary.  A singles sideline can otherwise be mistaken
                    # for a doubles sideline and produce a convincing but
                    # horizontally compressed metric map.  The cap prevents a
                    # very large neighbouring-court polygon from dominating on
                    # area alone.
                    area_bonus = int(
                        1000 * min(1.0, area / (0.45 * width * height))
                    )
                    structure_bonus = int(
                        600 * float(np.mean(longitudinal))
                        + 300 * float(np.mean(sorted(cross_court, reverse=True)[:3]))
                    )
                    score = matched + area_bonus + structure_bonus
                    scored.append((corners.astype(np.float32), score))

        # Suppress nearly identical fits created by duplicate Hough segments.
        scored.sort(key=lambda item: -item[1])
        distinct = []
        diagonal = math.hypot(frame.shape[1], frame.shape[0])
        for corners, score in scored:
            if any(
                float(np.mean(np.linalg.norm(corners - kept, axis=1)))
                < 0.015 * diagonal
                for kept, _kept_score in distinct
            ):
                continue
            distinct.append((corners, score))
            if len(distinct) >= limit:
                break
        return distinct

    def _corners_from_cross_candidates(
        self, support: np.ndarray, left, right, cross_candidates
    ) -> List[np.ndarray]:
        """Infer the court from detected sidelines plus baseline/service line.

        Trying actual cross-court line candidates avoids the fragile requirement
        that 85% of one image row must be white.  It also supports moderately
        rolled and off-centre cameras because each cross line keeps its slope.
        """

        height, width = support.shape[:2]
        results = []
        left_bottom = self._x_at_y(left, height - 1)
        right_bottom = self._x_at_y(right, height - 1)
        if left_bottom >= right_bottom or right_bottom - left_bottom < 0.25 * width:
            return results

        usable = []
        for line, hough_support in cross_candidates:
            left_point = self.line_intersection(line, left)
            right_point = self.line_intersection(line, right)
            if left_point is None or right_point is None:
                continue
            lx, ly = left_point
            rx, ry = right_point
            span = rx - lx
            centre_y = (ly + ry) / 2.0
            if (
                span < 0.12 * width
                or lx < -0.18 * width
                or rx > 1.18 * width
                or not (0.12 * height <= centre_y <= 1.05 * height)
            ):
                continue
            sample_count = max(30, int(abs(span)))
            xs = np.linspace(lx, rx, sample_count)
            ys = np.linspace(ly, ry, sample_count)
            xi = np.clip(np.rint(xs).astype(int), 0, width - 1)
            yi = np.clip(np.rint(ys).astype(int), 0, height - 1)
            line_fraction = float(np.count_nonzero(support[yi, xi])) / sample_count
            if line_fraction < 0.22:
                continue
            usable.append((line, centre_y, line_fraction, hough_support))

        # Lower line is the near baseline; the nearest substantial line above
        # it can be the near service line.  The full court-model score decides
        # between baseline, service, net and neighbouring-court alternatives.
        usable.sort(key=lambda item: item[1], reverse=True)
        for near_line, near_y, near_fraction, _near_support in usable[:12]:
            if near_y < 0.42 * height or near_fraction < 0.30:
                continue
            for service_line, service_y, service_fraction, _service_support in usable:
                separation = near_y - service_y
                if separation < 0.055 * height or separation > 0.48 * height:
                    continue
                if service_fraction < 0.22:
                    continue
                corners = self._corners_from_known_cross_lines(
                    left, right, near_line, service_line
                )
                if corners is not None:
                    results.append(corners)
                if len(results) >= 36:
                    return results
        return results

    def _corners_from_known_cross_lines(
        self, left, right, near_line, service_line
    ) -> Optional[np.ndarray]:
        image_points = []
        for cross_line, sideline in (
            (service_line, left),
            (service_line, right),
            (near_line, right),
            (near_line, left),
        ):
            point = self.line_intersection(cross_line, sideline)
            if point is None:
                return None
            image_points.append(point)

        court_width = float(self.court_dimensions['doubles_width'])
        court_length = float(self.court_dimensions['doubles_length'])
        service_y = court_length / 2.0 + 6.40
        court_points = np.asarray(
            [
                [0.0, service_y],
                [court_width, service_y],
                [court_width, court_length],
                [0.0, court_length],
            ],
            dtype=np.float32,
        )
        try:
            image_to_court = cv2.getPerspectiveTransform(
                np.asarray(image_points, dtype=np.float32), court_points
            )
            court_to_image = np.linalg.inv(image_to_court)
            far_corners = cv2.perspectiveTransform(
                np.asarray([[[0.0, 0.0], [court_width, 0.0]]], dtype=np.float64),
                court_to_image,
            )[0]
        except (cv2.error, np.linalg.LinAlgError):
            return None

        corners = np.asarray(
            [far_corners[0], far_corners[1], image_points[2], image_points[3]],
            dtype=np.float32,
        )
        if not np.all(np.isfinite(corners)):
            return None
        return corners

    def _court_model_segments(self):
        """Physical endpoints for the nine painted lines used by the model."""
        width = float(self.court_dimensions['doubles_width'])
        length = float(self.court_dimensions['doubles_length'])
        alley = (width - float(self.court_dimensions['singles_width'])) / 2.0
        service_far = length / 2.0 - 6.40
        service_near = length / 2.0 + 6.40
        return [
            ((0, 0), (width, 0)), ((0, length), (width, length)),                    # baselines
            ((0, 0), (0, length)), ((width, 0), (width, length)),                    # doubles sidelines
            ((alley, 0), (alley, length)), ((width - alley, 0), (width - alley, length)),  # singles sidelines
            ((alley, service_far), (width - alley, service_far)),                    # service lines
            ((alley, service_near), (width - alley, service_near)),
            ((width / 2, service_far), (width / 2, service_near)),                   # centre service line
        ]

    def _court_model_points(self, step_m: float = 0.1) -> np.ndarray:
        """Points (metres) sampled along every line of a tennis court."""
        points = []
        for (x1, y1), (x2, y2) in self._court_model_segments():
            n = max(2, int(np.hypot(x2 - x1, y2 - y1) / step_m))
            points.append(np.column_stack([np.linspace(x1, x2, n), np.linspace(y1, y2, n)]))
        return np.vstack(points)

    def _court_model_segment_fractions(
        self, support: np.ndarray, corners: np.ndarray, step_m: float = 0.06
    ) -> List[float]:
        """Return image support for each individual painted court line."""

        width = float(self.court_dimensions['doubles_width'])
        length = float(self.court_dimensions['doubles_length'])
        court_rect = np.asarray(
            [[0, 0], [width, 0], [width, length], [0, length]],
            dtype=np.float32,
        )
        court_to_image = cv2.getPerspectiveTransform(
            court_rect, corners.astype(np.float32)
        )
        image_height, image_width = support.shape[:2]
        fractions = []
        for (x1, y1), (x2, y2) in self._court_model_segments():
            n = max(24, int(math.hypot(x2 - x1, y2 - y1) / step_m))
            model_points = np.column_stack(
                [np.linspace(x1, x2, n), np.linspace(y1, y2, n)]
            ).astype(np.float32)
            projected = cv2.perspectiveTransform(
                model_points.reshape(-1, 1, 2), court_to_image
            ).reshape(-1, 2)
            xs = np.rint(projected[:, 0]).astype(int)
            ys = np.rint(projected[:, 1]).astype(int)
            inside = (
                (xs >= 0)
                & (xs < image_width)
                & (ys >= 0)
                & (ys < image_height)
            )
            if np.count_nonzero(inside) < max(8, int(0.45 * n)):
                fractions.append(0.0)
                continue
            pixels = np.unique(ys[inside] * image_width + xs[inside])
            fractions.append(
                float(np.count_nonzero(support.reshape(-1)[pixels])) / len(pixels)
            )
        return fractions

    def _court_model_score(self, support: np.ndarray, corners: np.ndarray) -> Tuple[int, float]:
        """How well the projected court-line model lands on detected line pixels.

        Returns (matched, fraction): the number of distinct image pixels of the
        projected model that fall on line pixels, and the fraction that do.
        The count is what ranks candidates: a fit squeezed into a small,
        cluttered area (net, back wall) can hit a high fraction while
        covering only a few pixels.
        """
        width = float(self.court_dimensions['doubles_width'])
        length = float(self.court_dimensions['doubles_length'])
        court_rect = np.array([[0, 0], [width, 0], [width, length], [0, length]], dtype=np.float32)
        court_to_image = cv2.getPerspectiveTransform(court_rect, corners.astype(np.float32))
        projected = cv2.perspectiveTransform(
            self._court_model_points().reshape(-1, 1, 2), court_to_image).reshape(-1, 2)
        height, image_width = support.shape[:2]
        xs, ys = np.round(projected[:, 0]).astype(int), np.round(projected[:, 1]).astype(int)
        inside = (xs >= 0) & (xs < image_width) & (ys >= 0) & (ys < height)
        # Most of the court must be in view.
        if inside.mean() < 0.6:
            return 0, 0.0
        pixels = np.unique(ys[inside] * image_width + xs[inside])
        matched = int(np.count_nonzero(support.reshape(-1)[pixels]))
        return matched, matched / len(pixels)

    def _corners_from_sidelines(self, mask: np.ndarray, left, right) -> Optional[np.ndarray]:
        """Find the baselines between two candidate sidelines and return the court corners."""
        height, width = mask.shape[:2]

        # Vanishing point of the two sidelines; baselines must lie below it.
        def as_homogeneous(line):
            x1, y1, x2, y2 = line
            return np.cross([x1, y1, 1.0], [x2, y2, 1.0])

        vanishing = np.cross(as_homogeneous(left), as_homogeneous(right))
        if abs(vanishing[2]) < 1e-9:
            return None
        vanishing_y = vanishing[1] / vanishing[2]
        if vanishing_y >= height:
            return None

        # A column "hits" a row when it has a white pixel within +/-band rows,
        # which tolerates slightly tilted baselines.
        band = 3
        dilated = cv2.dilate(mask, np.ones((2 * band + 1, 1), np.uint8))
        start_y = max(0, int(math.ceil(vanishing_y)) + 5)
        row_fill = {}
        for y in range(start_y, height):
            x0 = max(0, int(round(self._x_at_y(left, y) + 3)))
            x1 = min(width, int(round(self._x_at_y(right, y) - 3)) + 1)
            if x1 - x0 < 20:
                continue
            row_fill[y] = np.count_nonzero(dilated[y, x0:x1]) / float(x1 - x0)
        if not row_fill:
            return None

        def first_band_upwards(below_y: int, threshold: float):
            """Rows of the first white band above ``below_y`` with fill >= threshold."""
            rows = []
            for y in range(below_y - 1, start_y - 1, -1):
                if row_fill.get(y, 0.0) >= threshold:
                    rows.append(y)
                elif rows:
                    break
            return rows

        # The baseline spans the full doubles width; the service line spans
        # only the singles court (~75% of it), hence the lower threshold.
        near_rows = first_band_upwards(height, 0.85)
        if not near_rows:
            return None
        # Step past the blurred upper edge of the baseline before searching.
        above_baseline = min(near_rows)
        while above_baseline > start_y and row_fill.get(above_baseline, 0.0) >= 0.3:
            above_baseline -= 1
        service_rows = first_band_upwards(above_baseline, 0.5)
        if not service_rows:
            return None

        def refine_line(row: int):
            """Fit a line through the white pixels of the horizontal line near ``row``."""
            ys, xs = [], []
            for y in range(max(0, row - band - 2), min(height, row + band + 3)):
                x0 = max(0, int(round(self._x_at_y(left, y) + 3)))
                x1 = min(width, int(round(self._x_at_y(right, y) - 2)))
                cols = np.nonzero(mask[y, x0:x1])[0]
                xs.extend((cols + x0).tolist())
                ys.extend([y] * len(cols))
            if len(xs) < 10:
                return (0.0, float(row), float(width), float(row))
            vx, vy, cx, cy = cv2.fitLine(np.column_stack([xs, ys]).astype(np.float32),
                                         cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            return (float(cx - vx * width), float(cy - vy * width),
                    float(cx + vx * width), float(cy + vy * width))

        near_line = refine_line(int(np.mean(near_rows)))
        service_line = refine_line(int(np.mean(service_rows)))

        image_points = []
        for cross_line, sideline in ((service_line, left), (service_line, right),
                                     (near_line, right), (near_line, left)):
            point = self.line_intersection(cross_line, sideline)
            if point is None:
                return None
            image_points.append(point)

        court_width = float(self.court_dimensions['doubles_width'])
        court_length = float(self.court_dimensions['doubles_length'])
        service_y = court_length / 2.0 + 6.40  # net to service line is 6.40 m
        court_points = np.array([
            [0.0, service_y], [court_width, service_y],
            [court_width, court_length], [0.0, court_length],
        ], dtype=np.float32)
        try:
            image_to_court = cv2.getPerspectiveTransform(
                np.array(image_points, dtype=np.float32), court_points)
            court_to_image = np.linalg.inv(image_to_court)
        except (cv2.error, np.linalg.LinAlgError):
            return None

        far_corners = cv2.perspectiveTransform(
            np.array([[[0.0, 0.0], [court_width, 0.0]]], dtype=np.float64), court_to_image)[0]
        corners = np.array([far_corners[0], far_corners[1],
                            image_points[2], image_points[3]], dtype=np.float32)
        if not np.all(np.isfinite(corners)):
            return None

        top_width = corners[1, 0] - corners[0, 0]
        bottom_width = corners[2, 0] - corners[3, 0]
        if corners[3, 1] - corners[0, 1] < 0.1 * height or top_width <= 0 or bottom_width < top_width:
            return None
        return np.round(corners).astype(np.int32)
    
    def draw_court_analysis(self, frame: np.ndarray, corners: np.ndarray, 
                           lines: np.ndarray = None) -> np.ndarray:
        """
        Draw court analysis visualization
        """
        result = frame.copy()
        
        # Draw detected corners
        if corners is not None:
            for i, corner in enumerate(corners):
                cv2.circle(result, tuple(corner), 10, (0, 255, 0), -1)
                cv2.putText(result, f"C{i}", tuple(corner), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Draw court outline
            cv2.polylines(result, [corners], True, (0, 255, 0), 3)
        
        # Draw detected lines
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(result, (x1, y1), (x2, y2), (255, 0, 0), 2)
        
        return result
    
    def order_court_corners(self, corners: np.ndarray) -> np.ndarray:
        """
        Order four court corners as:
        0: top left
        1: top right
        2: bottom right
        3: bottom left
        """

        if corners is None or len(corners) != 4:
            raise ValueError("Exactly 4 court corners are required.")

        points = np.asarray(corners, dtype=np.float32).reshape(4, 2)

        # Split into the far (top) and near (bottom) pair by y, then order each
        # pair by x. Sorting by x+y / y-x breaks for wide perspective
        # trapezoids, where a near corner can have a smaller x+y than a far one.
        by_y = points[np.argsort(points[:, 1], kind='stable')]
        top = by_y[:2][np.argsort(by_y[:2, 0], kind='stable')]
        bottom = by_y[2:][np.argsort(by_y[2:, 0], kind='stable')]

        ordered = np.array([top[0], top[1], bottom[1], bottom[0]], dtype=np.float32)

        return ordered
    def get_court_transform_matrix(self, corners: np.ndarray) -> Optional[np.ndarray]:
        """Return a homography mapping video pixels to real court coordinates (metres).

        The source corners are ordered as top-left, top-right, bottom-right,
        bottom-left. The target origin is the top-left corner of the doubles court.
        This matrix is for transforming points, NOT for warping an image canvas.
        """
        if corners is None or len(corners) != 4:
            return None

        ordered_corners = self.order_court_corners(corners)
        width = float(self.court_dimensions['doubles_width'])
        length = float(self.court_dimensions['doubles_length'])
        real_court_points = np.array([
            [0.0, 0.0],
            [width, 0.0],
            [width, length],
            [0.0, length],
        ], dtype=np.float32)

        try:
            H_metric = cv2.getPerspectiveTransform(
                ordered_corners.astype(np.float32), real_court_points
            )
        except cv2.error:
            return None

        if H_metric is None or not np.all(np.isfinite(H_metric)):
            return None
        return H_metric

    def get_birds_eye_transform_matrix(
        self,
        corners: np.ndarray,
        target_size: Tuple[int, int] = (600, 1300),
    ) -> Optional[np.ndarray]:
        """Return a separate pixel-to-pixel homography for a bird's-eye image.

        ``target_size`` is (width, height). The default is approximately the
        real doubles-court aspect ratio, unlike the metric homography above.
        """
        if corners is None or len(corners) != 4:
            return None

        target_width, target_height = target_size
        if target_width <= 1 or target_height <= 1:
            raise ValueError("target_size width and height must both be > 1")

        ordered_corners = self.order_court_corners(corners)
        target_points = np.array([
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ], dtype=np.float32)

        try:
            H_visual = cv2.getPerspectiveTransform(
                ordered_corners.astype(np.float32), target_points
            )
        except cv2.error:
            return None

        if H_visual is None or not np.all(np.isfinite(H_visual)):
            return None
        return H_visual

# Main function removed - use main.py for application entry point
