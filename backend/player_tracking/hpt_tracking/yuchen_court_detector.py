import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict
import itertools
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
        # How many of the strongest image lines are tried as lines across the
        # court and along it. The net tape and fences also produce strong
        # horizontal lines, so the real service lines can rank well down.
        self.max_cross_lines = 20
        self.max_length_lines = 12

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
    def _white_line_mask(frame: np.ndarray, contrast: int = 12) -> np.ndarray:
        """Binary mask of court-line pixels.

        Court lines are thin structures that are clearly whiter than the
        surface around them. "Whiteness" is brightness minus saturation, and
        only its contrast with the surroundings (morphological top-hat) is
        used, so it works on dark and light courts alike. A line next to a
        light-blue apron is barely brighter than it, but far less saturated.
        ``contrast`` is kept low so faint lines in night footage still show;
        the clutter this lets through is rejected by the court-model fit.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        saturation, value = hsv[..., 1], hsv[..., 2]
        whiteness = np.clip(value.astype(np.int16) - saturation.astype(np.int16), 0, 255).astype(np.uint8)
        kernel_size = max(7, (frame.shape[0] // 40) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        tophat = cv2.morphologyEx(whiteness, cv2.MORPH_TOPHAT, kernel)
        return ((tophat > contrast) & (saturation < 100)).astype(np.uint8) * 255

    # Painted court lines a hypothesis can name, in metres. Lines across the
    # court (constant y): far baseline, far service line, near service line,
    # near baseline. Lines along it (constant x): doubles and singles
    # sidelines. The centre service line (only spans the service boxes) and
    # the net (raised off the ground) are not used to fix a hypothesis.
    CROSS_LINES_M = (0.0, 5.485, 18.285, 23.77)
    LENGTH_LINES_M = (0.0, 1.37, 9.6, 10.97)

    @staticmethod
    def _line_from_points(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
        """Normalised (a, b, c) with a*x + b*y + c = 0."""
        a, b = y1 - y2, x2 - x1
        norm = math.hypot(a, b)
        return np.array([a, b, x1 * y2 - x2 * y1]) / norm

    @staticmethod
    def _intersect(l1: np.ndarray, l2: np.ndarray) -> Optional[Tuple[float, float]]:
        p = np.cross(l1, l2)
        if abs(p[2]) < 1e-9:
            return None
        return p[0] / p[2], p[1] / p[2]

    def _line_candidates(self, mask: np.ndarray, max_lines: int = 24) -> List[Dict]:
        """Long straight lines in the mask, strongest (most supporting length) first.

        Hough segments lying on the same line are merged; each merged line is
        refitted through all its segments. Every entry has ``line`` (a, b, c),
        ``tilt`` (degrees from horizontal) and ``length`` (total segment length).
        """
        height, width = mask.shape[:2]
        segments = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=30,
                                   minLineLength=max(25, int(0.08 * height)), maxLineGap=8)
        if segments is None:
            return []
        segments = np.asarray(segments, dtype=np.float64).reshape(-1, 4)
        lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
        tolerance = 0.006 * math.hypot(width, height) + 2.0

        groups = []
        for (x1, y1, x2, y2), length in sorted(zip(segments, lengths), key=lambda s: -s[1]):
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            for group in groups:
                difference = abs(group['angle'] - angle)
                a, b, c = group['seed']
                if min(difference, 180 - difference) <= 2.0 and abs(a * mx + b * my + c) <= tolerance:
                    group['length'] += length
                    group['segments'].append((x1, y1, x2, y2))
                    break
            else:
                groups.append({'angle': angle, 'seed': self._line_from_points(x1, y1, x2, y2),
                               'length': length, 'segments': [(x1, y1, x2, y2)]})

        groups.sort(key=lambda g: -g['length'])
        candidates = []
        for group in groups[:max_lines]:
            points = []
            for x1, y1, x2, y2 in group['segments']:
                n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 3))
                points.append(np.column_stack([np.linspace(x1, x2, n), np.linspace(y1, y2, n)]))
            vx, vy, x0, y0 = cv2.fitLine(np.vstack(points).astype(np.float32),
                                         cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
            line = np.array([-vy, vx, vy * x0 - vx * y0], dtype=np.float64)
            angle = math.degrees(math.atan2(vy, vx)) % 180
            candidates.append({'line': line, 'tilt': min(angle, 180 - angle), 'length': group['length']})
        return candidates

    def detect_court_corners_perspective(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Detect the four doubles-court corners in a view from behind a baseline.

        Returns corners ordered far-left, far-right, near-right, near-left
        (image coordinates; corners outside the frame are allowed), or None.
        """
        return self.detect_court_with_score(frame)[0]

    def detect_court_with_score(self, frame: np.ndarray) -> Tuple[Optional[np.ndarray], int]:
        """Fit a tennis-court model to the white lines in ``frame``.

        1. Long straight lines are found in a white-pixel mask.
        2. Every choice of two flatter lines (across the court) and two
           steeper lines (along it) is a candidate; each such quadrilateral is
           tried as every pairing of named court lines (baseline/service line,
           doubles/singles sideline). That covers cameras off to one side and
           views where the near baseline or a sideline is out of frame.
        3. Each hypothesis projects the full court-line model into the image;
           the one whose lines land best on the white pixels wins.
        The score is the number of court-line pixels the fit explains, so it
        can be compared across frames of the same video.
        """
        height, width = frame.shape[:2]
        mask = self._white_line_mask(frame)
        support = cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0
        lines = self._line_candidates(mask)
        flat = [l for l in lines if l['tilt'] <= 30][:self.max_cross_lines]
        steep = [l for l in lines if l['tilt'] >= 10][:self.max_length_lines]
        if len(flat) < 2 or len(steep) < 2:
            return None, 0

        # Every (upper, lower) cross-line pair times every (left, right) length-line pair.
        names = [(ya, yb, xa, xb)
                 for i, ya in enumerate(self.CROSS_LINES_M) for yb in self.CROSS_LINES_M[i + 1:]
                 for j, xa in enumerate(self.LENGTH_LINES_M) for xb in self.LENGTH_LINES_M[j + 1:]]
        names_arr = np.array(names)
        coarse = self._court_model_points(step_m=0.3)
        # Model points in each hypothesis' unit square (0..1 between its four lines).
        U = (coarse[None, :, 0] - names_arr[:, 2:3]) / (names_arr[:, 3:4] - names_arr[:, 2:3])
        V = (coarse[None, :, 1] - names_arr[:, 0:1]) / (names_arr[:, 1:2] - names_arr[:, 0:1])
        # The two near corners of the doubles court, same parametrisation.
        near = np.array([[0.0, self.court_dimensions['doubles_length']],
                         [self.court_dimensions['doubles_width'], self.court_dimensions['doubles_length']]])
        NU = (near[None, :, 0] - names_arr[:, 2:3]) / (names_arr[:, 3:4] - names_arr[:, 2:3])
        NV = (near[None, :, 1] - names_arr[:, 0:1]) / (names_arr[:, 1:2] - names_arr[:, 0:1])
        unit = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        centre_x = width / 2.0

        def y_at_centre(line):
            a, b, c = line
            return -(a * centre_x + c) / b if abs(b) > 1e-9 else float('inf')

        shortlist = []  # (coarse score, unit-square homography, hypothesis index)
        for h1, h2 in itertools.combinations(flat, 2):
            upper, lower = (h1, h2) if y_at_centre(h1['line']) < y_at_centre(h2['line']) else (h2, h1)
            for v1, v2 in itertools.combinations(steep, 2):
                if max(h1['tilt'], h2['tilt']) >= min(v1['tilt'], v2['tilt']):
                    continue
                points = [self._intersect(upper['line'], v1['line']), self._intersect(upper['line'], v2['line']),
                          self._intersect(lower['line'], v2['line']), self._intersect(lower['line'], v1['line'])]
                if any(p is None for p in points):
                    continue
                ul, ur, lr, ll = points
                if ul[0] > ur[0]:
                    ul, ur, lr, ll = ur, ul, ll, lr
                if not (ur[0] - ul[0] > 2 and lr[0] - ll[0] > 2 and ll[1] > ul[1] and lr[1] > ur[1]):
                    continue
                # Seen from behind a baseline the far end looks narrower.
                if lr[0] - ll[0] < 0.9 * (ur[0] - ul[0]):
                    continue
                quad = np.array([ul, ur, lr, ll], dtype=np.float64)
                if (quad[:, 0].min() < -2 * width or quad[:, 0].max() > 3 * width or
                        quad[:, 1].min() < -2 * height or quad[:, 1].max() > 3 * height):
                    continue
                try:
                    Hq = cv2.getPerspectiveTransform(unit, quad.astype(np.float32))
                except cv2.error:
                    continue
                Z = Hq[2, 0] * U + Hq[2, 1] * V + Hq[2, 2]
                # The whole court must be in front of the camera.
                valid = np.all(Z > 1e-9, axis=1) | np.all(Z < -1e-9, axis=1)
                if not valid.any():
                    continue
                with np.errstate(divide='ignore', invalid='ignore'):
                    X = (Hq[0, 0] * U + Hq[0, 1] * V + Hq[0, 2]) / Z
                    Y = (Hq[1, 0] * U + Hq[1, 1] * V + Hq[1, 2]) / Z
                inside = valid[:, None] & (X >= 0) & (X < width) & (Y >= 0) & (Y < height)
                xs = np.where(inside, X, 0).astype(np.int64)
                ys = np.where(inside, Y, 0).astype(np.int64)
                hits = inside & support[ys, xs]
                n_inside, n_hits = inside.sum(axis=1), hits.sum(axis=1)
                # The camera stands behind the near baseline, so that baseline is
                # wide in the image and in its lower half (or below the frame).
                # This rules out small fits on stands, fences and the net.
                with np.errstate(divide='ignore', invalid='ignore'):
                    Zn = Hq[2, 0] * NU + Hq[2, 1] * NV + Hq[2, 2]
                    Xn = (Hq[0, 0] * NU + Hq[0, 1] * NV + Hq[0, 2]) / Zn
                    Yn = (Hq[1, 0] * NU + Hq[1, 1] * NV + Hq[1, 2]) / Zn
                plausible = (Yn.mean(axis=1) >= 0.6 * height) & (np.abs(Xn[:, 1] - Xn[:, 0]) >= 0.4 * width)
                ok = (n_inside >= 0.3 * coarse.shape[0]) & (n_hits >= 0.5 * n_inside) & plausible
                for k in np.nonzero(ok)[0]:
                    shortlist.append((n_hits[k] - 0.5 * (n_inside[k] - n_hits[k]), Hq, k))

        if not shortlist:
            return None, 0
        shortlist.sort(key=lambda s: -s[0])
        best, best_score, best_value = None, 0, -np.inf
        for _, Hq, k in shortlist[:300]:
            ya, yb, xa, xb = names[k]
            to_unit = np.array([[1 / (xb - xa), 0, -xa / (xb - xa)],
                                [0, 1 / (yb - ya), -ya / (yb - ya)],
                                [0, 0, 1]])
            court_to_image = Hq @ to_unit
            matched, total = self._court_model_score(support, court_to_image)
            value = matched - 0.5 * (total - matched)
            if total and matched >= 0.5 * total and value > best_value:
                best, best_score, best_value = court_to_image, matched, value
        if best is None:
            return None, 0

        refined = self._refine_fit(mask, best)
        if refined is not None:
            matched, total = self._court_model_score(support, refined)
            if total and matched >= best_score:
                best, best_score = refined, matched

        court = np.array([[0, 0], [self.court_dimensions['doubles_width'], 0],
                          [self.court_dimensions['doubles_width'], self.court_dimensions['doubles_length']],
                          [0, self.court_dimensions['doubles_length']]], dtype=np.float64)
        corners = cv2.perspectiveTransform(court.reshape(-1, 1, 2), best).reshape(-1, 2)
        if not np.all(np.isfinite(corners)):
            return None, 0
        return np.round(corners).astype(np.int32), int(best_score)

    def _refine_fit(self, mask: np.ndarray, court_to_image: np.ndarray) -> Optional[np.ndarray]:
        """Pull the projected court lines onto the nearest white-line pixels.

        The hypothesis is fixed by only four lines, so the other lines can sit
        a few pixels off. Each pass pairs every projected model point with the
        nearest line pixel within a shrinking radius and re-solves the
        homography robustly from all those pairs.
        """
        height, width = mask.shape[:2]
        if not mask.any():
            return None
        # Distance to, and position of, the nearest line pixel for every pixel.
        not_line = (mask == 0).astype(np.uint8)
        distance, labels = cv2.distanceTransformWithLabels(
            not_line, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        line_ys, line_xs = np.nonzero(not_line == 0)  # label k is the k-th line pixel in row order
        model = self._court_model_points(step_m=0.1)
        H = court_to_image
        for radius in (8.0, 6.0, 4.0, 3.0):
            projected = cv2.perspectiveTransform(model.reshape(-1, 1, 2), H).reshape(-1, 2)
            xs, ys = np.round(projected[:, 0]), np.round(projected[:, 1])
            inside = np.isfinite(xs) & np.isfinite(ys) & (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
            xi, yi = xs[inside].astype(int), ys[inside].astype(int)
            near = distance[yi, xi] <= radius
            if near.sum() < 50:
                return None
            label = labels[yi[near], xi[near]] - 1
            targets = np.column_stack([line_xs[label], line_ys[label]]).astype(np.float64)
            H_new, _ = cv2.findHomography(model[inside][near], targets, cv2.RANSAC, 2.0)
            if H_new is None or not np.all(np.isfinite(H_new)):
                return None
            H = H_new
        return H

    def _court_model_points(self, step_m: float = 0.1) -> np.ndarray:
        """Points (metres) sampled along every line of a tennis court."""
        width = float(self.court_dimensions['doubles_width'])
        length = float(self.court_dimensions['doubles_length'])
        alley = (width - float(self.court_dimensions['singles_width'])) / 2.0
        service_far = length / 2.0 - 6.40
        service_near = length / 2.0 + 6.40
        segments = [
            ((0, 0), (width, 0)), ((0, length), (width, length)),                    # baselines
            ((0, 0), (0, length)), ((width, 0), (width, length)),                    # doubles sidelines
            ((alley, 0), (alley, length)), ((width - alley, 0), (width - alley, length)),  # singles sidelines
            ((alley, service_far), (width - alley, service_far)),                    # service lines
            ((alley, service_near), (width - alley, service_near)),
            ((width / 2, service_far), (width / 2, service_near)),                   # centre service line
        ]
        points = []
        for (x1, y1), (x2, y2) in segments:
            n = max(2, int(np.hypot(x2 - x1, y2 - y1) / step_m))
            points.append(np.column_stack([np.linspace(x1, x2, n), np.linspace(y1, y2, n)]))
        return np.vstack(points)

    def _court_model_score(self, support: np.ndarray, court_to_image: np.ndarray) -> Tuple[int, int]:
        """Distinct in-frame pixels of the projected court-line model: (on a white line, total)."""
        projected = cv2.perspectiveTransform(
            self._court_model_points().reshape(-1, 1, 2), court_to_image).reshape(-1, 2)
        height, width = support.shape[:2]
        finite = np.all(np.isfinite(projected), axis=1)
        projected = projected[finite]
        xs, ys = np.round(projected[:, 0]), np.round(projected[:, 1])
        inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        if inside.sum() < 0.3 * len(finite):
            return 0, 0
        pixels = np.unique(ys[inside].astype(np.int64) * width + xs[inside].astype(np.int64))
        return int(np.count_nonzero(support.reshape(-1)[pixels])), int(len(pixels))
    
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