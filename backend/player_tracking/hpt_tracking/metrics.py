"""Movement metrics for pixel or estimated court-coordinate trajectories."""

from math import acos, degrees, hypot
from statistics import median
from typing import Dict, Iterable, List, Sequence, Tuple


TrajectorySample = Tuple[int, float, float]


def _unavailable_metric(reason: str) -> Dict:
    return {
        "status": "unavailable",
        "value": None,
        "unit": None,
        "note": reason,
    }


def _moving_median(values: Sequence[float], radius: int = 2) -> List[float]:
    return [
        median(values[max(0, index - radius) : index + radius + 1])
        for index in range(len(values))
    ]


def _angle_between(first: Tuple[float, float], second: Tuple[float, float]) -> float:
    first_length = hypot(*first)
    second_length = hypot(*second)
    if first_length == 0 or second_length == 0:
        return 0.0

    cosine = (first[0] * second[0] + first[1] * second[1]) / (
        first_length * second_length
    )
    return degrees(acos(max(-1.0, min(1.0, cosine))))


def analyse_trajectory(
    samples: Iterable[TrajectorySample],
    fps: float,
    direction_change_degrees: float = 45.0,
    minimum_step: float = 2.0,
    coordinate_system: str = "image_pixels",
    distance_unit: str = "px",
    measurement_note: str = (
        "Pixel-space prototype result; not calibrated to real-world units."
    ),
) -> Dict:
    """Calculate movement metrics without overstating measurement accuracy.

    When a court homography is available, callers pass estimated court points and
    metre-based units. Those values remain experimental because the automatically
    detected court corners have not been manually validated.
    """

    ordered_samples = sorted(samples, key=lambda sample: sample[0])
    if len(ordered_samples) < 2 or fps <= 0:
        reason = "At least two tracked frames and a valid frame rate are required."
        return {
            "movementPath": {
                "status": "unavailable",
                "coordinateSystem": coordinate_system,
                "points": [],
                "note": reason,
            },
            "totalDistance": _unavailable_metric(reason),
            "speed": {
                "status": "unavailable",
                "average": None,
                "peak": None,
                "unit": None,
                "samples": [],
                "note": reason,
            },
            "acceleration": _unavailable_metric(reason),
            "deceleration": _unavailable_metric(reason),
            "directionChanges": {
                "status": "unavailable",
                "count": None,
                "events": [],
                "note": reason,
            },
        }

    points = [
        {
            "frame": frame,
            "timeSeconds": round(frame / fps, 4),
            "x": round(x, 3),
            "y": round(y, 3),
        }
        for frame, x, y in ordered_samples
    ]

    distances: List[float] = []
    speeds: List[float] = []
    vectors: List[Tuple[float, float]] = []
    sample_times: List[float] = []

    for previous, current in zip(ordered_samples, ordered_samples[1:]):
        previous_frame, previous_x, previous_y = previous
        current_frame, current_x, current_y = current
        frame_delta = current_frame - previous_frame
        if frame_delta <= 0:
            continue

        delta_x = current_x - previous_x
        delta_y = current_y - previous_y
        distance = hypot(delta_x, delta_y)
        if distance < minimum_step:
            # Bounding-box feet jitter even when a player is standing still.
            # Treat sub-threshold movement as zero rather than accumulating it.
            delta_x = 0.0
            delta_y = 0.0
            distance = 0.0
        elapsed_seconds = frame_delta / fps

        distances.append(distance)
        speeds.append(distance / elapsed_seconds)
        vectors.append((delta_x, delta_y))
        sample_times.append(current_frame / fps)

    if not speeds:
        return analyse_trajectory(
            [],
            fps,
            direction_change_degrees=direction_change_degrees,
            minimum_step=minimum_step,
            coordinate_system=coordinate_system,
            distance_unit=distance_unit,
            measurement_note=measurement_note,
        )

    smoothed_speeds = _moving_median(speeds)
    acceleration_samples: List[Dict] = []
    positive_accelerations: List[float] = []
    decelerations: List[float] = []

    for index in range(1, len(smoothed_speeds)):
        time_delta = sample_times[index] - sample_times[index - 1]
        if time_delta <= 0:
            continue
        acceleration = (smoothed_speeds[index] - smoothed_speeds[index - 1]) / time_delta
        acceleration_samples.append(
            {
                "timeSeconds": round(sample_times[index], 4),
                "value": round(acceleration, 3),
            }
        )
        if acceleration > 0:
            positive_accelerations.append(acceleration)
        elif acceleration < 0:
            decelerations.append(abs(acceleration))

    direction_events: List[Dict] = []
    last_direction_event_index = -3
    for index in range(1, len(vectors)):
        if hypot(*vectors[index - 1]) < minimum_step:
            continue
        if hypot(*vectors[index]) < minimum_step:
            continue
        angle = _angle_between(vectors[index - 1], vectors[index])
        if angle >= direction_change_degrees and index - last_direction_event_index >= 3:
            direction_events.append(
                {
                    "timeSeconds": round(sample_times[index], 4),
                    "angleDegrees": round(angle, 2),
                }
            )
            last_direction_event_index = index

    speed_unit = f"{distance_unit}/s"
    acceleration_unit = f"{distance_unit}/s²"

    return {
        "movementPath": {
            "status": "experimental",
            "coordinateSystem": coordinate_system,
            "points": points,
            "note": measurement_note,
        },
        "totalDistance": {
            "status": "experimental",
            "value": round(sum(distances), 3),
            "unit": distance_unit,
            "note": measurement_note,
        },
        "speed": {
            "status": "experimental",
            "average": round(sum(smoothed_speeds) / len(smoothed_speeds), 3),
            "peak": round(max(smoothed_speeds), 3),
            "unit": speed_unit,
            "samples": [
                {
                    "timeSeconds": round(time_value, 4),
                    "value": round(speed_value, 3),
                }
                for time_value, speed_value in zip(sample_times, smoothed_speeds)
            ],
            "note": measurement_note,
        },
        "acceleration": {
            "status": "experimental" if acceleration_samples else "unavailable",
            "value": round(max(positive_accelerations), 3)
            if positive_accelerations
            else None,
            "unit": acceleration_unit if acceleration_samples else None,
            "samples": acceleration_samples,
            "note": measurement_note
            if acceleration_samples
            else "Insufficient speed samples.",
        },
        "deceleration": {
            "status": "experimental" if acceleration_samples else "unavailable",
            "value": round(max(decelerations), 3) if decelerations else 0.0,
            "unit": acceleration_unit if acceleration_samples else None,
            "samples": [sample for sample in acceleration_samples if sample["value"] < 0],
            "note": measurement_note
            if acceleration_samples
            else "Insufficient speed samples.",
        },
        "directionChanges": {
            "status": "experimental",
            "count": len(direction_events),
            "events": direction_events,
            "note": (
                f"Prototype count using a {direction_change_degrees:.0f}° threshold; "
                "not yet validated."
            ),
        },
    }
