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
        
    def detect_court_lines(self, frame: np.ndarray) -> np.ndarray:
        """
        Detect tennis court lines using edge detection and Hough line transform
        """
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Apply Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)
        
        # Apply morphological operations to connect broken lines
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        
        # Detect lines using Hough transform
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                               minLineLength=50, maxLineGap=10)
        
        return lines
    
    def filter_court_lines(self, lines: np.ndarray, frame_shape: Tuple[int, int]) -> List[np.ndarray]:
        """
        Filter lines to identify potential court boundaries
        """
        if lines is None:
            return []
        
        height, width = frame_shape[:2]
        horizontal_lines = []
        vertical_lines = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            
            # Calculate line angle
            angle = math.atan2(y2 - y1, x2 - x1) * 180 / np.pi
            angle = abs(angle)
            
            # Classify lines as horizontal or vertical
            if angle < 30 or angle > 150:  # Horizontal lines
                horizontal_lines.append(line[0])
            elif 60 < angle < 120:  # Vertical lines
                vertical_lines.append(line[0])
        
        return horizontal_lines, vertical_lines
    
    def find_court_corners(self, horizontal_lines: List, vertical_lines: List, 
                          frame_shape: Tuple[int, int]) -> Optional[np.ndarray]:
        """
        Find court corners by intersecting horizontal and vertical lines
        """
        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            return None
        
        height, width = frame_shape[:2]
        intersections = []
        
        # Find intersections between horizontal and vertical lines
        for h_line in horizontal_lines:
            for v_line in vertical_lines:
                intersection = self.line_intersection(h_line, v_line)
                if intersection is not None:
                    x, y = intersection
                    # Check if intersection is within frame bounds
                    if 0 <= x <= width and 0 <= y <= height:
                        intersections.append(intersection)
        
        if len(intersections) < 4:
            return None
        
        # Find the 4 corners that form the largest rectangle
        corners = self.find_best_rectangle(intersections)
        
        return np.array(corners, dtype=np.int32) if corners else None
    
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
    
    def find_best_rectangle(self, points: List[Tuple[float, float]]) -> Optional[List[Tuple[int, int]]]:
        """
        Find the best rectangle from intersection points
        """
        if len(points) < 4:
            return None

        # Convert to OpenCV-compatible type
        points = np.asarray(points, dtype=np.float32)

        if len(points) < 4:
            return None

        # Find the convex hull
        hull = cv2.convexHull(points)

        # Approximate the hull to get corners
        epsilon = 0.02 * cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, epsilon, True)

        # If we have exactly 4 points, return them
        if len(approx) == 4:
            return [tuple(map(int, point[0])) for point in approx]

        # If we have more than 4 points, try to find the best 4
        if len(approx) > 4:
            best_area = 0
            best_corners = None

            for i in range(len(approx) - 3):
                for j in range(i + 1, len(approx) - 2):
                    for k in range(j + 1, len(approx) - 1):
                        for l in range(k + 1, len(approx)):
                            corners = [
                                approx[i][0],
                                approx[j][0],
                                approx[k][0],
                                approx[l][0]
                            ]

                            contour = np.asarray(corners, dtype=np.float32)
                            area = cv2.contourArea(contour)

                            if area > best_area:
                                best_area = area
                                best_corners = corners

            if best_corners is not None:
                return [tuple(map(int, corner)) for corner in best_corners]

        return None
    
    def detect_court_keypoints_advanced(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Advanced court detection using line detection and geometry
        """
        # Prefer the perspective-aware detector: it finds the slanted doubles
        # sidelines and the baselines between them, so overlays such as a
        # minimap or scoreboard are not mistaken for the court.
        corners = self.detect_court_corners_perspective(frame)
        if corners is not None:
            return corners

        # Detect lines
        lines = self.detect_court_lines(frame)

        if lines is None:
            return None

        # Filter lines
        horizontal_lines, vertical_lines = self.filter_court_lines(lines, frame.shape)

        # Find court corners
        corners = self.find_court_corners(horizontal_lines, vertical_lines, frame.shape)

        return corners

    @staticmethod
    def _white_line_mask(frame: np.ndarray) -> np.ndarray:
        """Binary mask of court-line pixels.

        Combines plainly white pixels with thin structures that are clearly
        brighter than their surroundings (morphological top-hat), because
        distant or blurred lines are often too dim for a fixed white threshold.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        saturation, value = hsv[..., 1], hsv[..., 2]
        kernel_size = max(7, (frame.shape[0] // 40) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        tophat = cv2.morphologyEx(value, cv2.MORPH_TOPHAT, kernel)
        white = (value > 170) & (saturation < 70)
        thin_bright = (tophat > 25) & (saturation < 100)
        return (white | thin_bright).astype(np.uint8) * 255

    @staticmethod
    def _x_at_y(line: Tuple[float, float, float, float], y: float) -> float:
        x1, y1, x2, y2 = line
        return x1 + (y - y1) * (x2 - x1) / (y2 - y1)

    def _find_doubles_sidelines(self, mask: np.ndarray):
        """Return the outermost left/right slanted court lines as (x1, y1, x2, y2)."""
        height, width = mask.shape[:2]
        min_length = max(30, int(0.15 * height))
        lines = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=40,
                                minLineLength=min_length, maxLineGap=10)
        if lines is None:
            return None, None

        left_candidates, right_candidates = [], []
        for x1, y1, x2, y2 in lines[:, 0].astype(np.float64):
            if y1 == y2:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
            # In a behind-the-baseline view the sidelines slant towards a
            # vanishing point above the court. Near-vertical lines (overlay
            # borders, posts) and near-horizontal lines are not sidelines.
            if 15 <= angle <= 75:
                right_candidates.append((x1, y1, x2, y2))
            elif 105 <= angle <= 165:
                left_candidates.append((x1, y1, x2, y2))

        if not left_candidates or not right_candidates:
            return None, None

        reference_y = height - 1
        left = min(left_candidates, key=lambda l: self._x_at_y(l, reference_y))
        right = max(right_candidates, key=lambda l: self._x_at_y(l, reference_y))
        return left, right

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
        Returns corners ordered top-left, top-right, bottom-right, bottom-left,
        or None if no plausible court is found.
        """
        mask = self._white_line_mask(frame)
        height, width = mask.shape[:2]
        left, right = self._find_doubles_sidelines(mask)
        if left is None or right is None:
            return None

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
    
    def validate_court_geometry(self, corners: np.ndarray) -> bool:
        """Validate that four detected corners have a plausible court shape.

        This is a coarse sanity check only; it cannot guarantee that the detected
        points are the true court corners.
        """
        if corners is None or len(corners) != 4:
            return False

        try:
            ordered = self.order_court_corners(corners)
        except (ValueError, IndexError):
            return False

        top_width = np.linalg.norm(ordered[1] - ordered[0])
        bottom_width = np.linalg.norm(ordered[2] - ordered[3])
        left_length = np.linalg.norm(ordered[3] - ordered[0])
        right_length = np.linalg.norm(ordered[2] - ordered[1])
        width = (top_width + bottom_width) / 2.0
        length = (left_length + right_length) / 2.0

        if width <= 0 or length <= 0:
            return False

        aspect_ratio = length / width
        # A doubles court has a real length/width ratio of about 2.17;
        # perspective distortion means the image-space ratio can differ.
        return 1.5 < aspect_ratio < 4.5

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
    '''
    def get_court_transform_matrix(self, corners: np.ndarray, 
                                 target_size: Tuple[int, int] = (800, 600)) -> Optional[np.ndarray]:
        """
        Calculate transformation matrix for bird's eye view
        """
        if corners is None or len(corners) != 4:
            return None
        
        # Define target points for bird's eye view
        target_width, target_height = target_size
        target_points = np.array([
            [0, 0],
            [target_width, 0],
            [target_width, target_height],
            [0, target_height]
        ], dtype=np.float32)
        
        # Calculate homography matrix
        H = cv2.findHomography(corners.astype(np.float32), target_points)
        
        return H[0] if H is not None else None
    '''
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