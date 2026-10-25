"""Reliable metric kinematics and estimated Force–Velocity results.

This module keeps all calculations that depend on real-world court coordinates
in one place.  Pixel metrics remain available when the automatic court mapping
is rejected.
"""

from math import hypot
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter

from .metrics import TrajectorySample


MINIMUM_CALIBRATION_CONFIDENCE = 0.70
MAXIMUM_PLAYER_SPEED_MPS = 12.0
MAXIMUM_ACCELERATION_MPS2 = 15.0
MAXIMUM_GAP_FRAMES = 5
KINEMATICS_WINDOW_SECONDS = 0.70
MINIMUM_MASS_KG = 20.0
MAXIMUM_MASS_KG = 250.0


def validate_athlete_mass(mass_kg: float) -> bool:
    """Return whether a supplied mass is plausible for the prototype."""

    return MINIMUM_MASS_KG <= mass_kg <= MAXIMUM_MASS_KG


def assess_metric_trajectory(
    samples: Iterable[TrajectorySample],
    fps: float,
    calibration_confidence: float,
) -> Dict:
    """Reject weak court mappings and trajectories with many impossible jumps.

    This is deliberately conservative: the app can still return pixel results
    when metric output is rejected, but it must not present false Newton values.
    """

    ordered = sorted(samples, key=lambda sample: sample[0])
    reasons: List[str] = []
    if calibration_confidence < MINIMUM_CALIBRATION_CONFIDENCE:
        reasons.append(
            "Court-line detection was not consistent enough across calibration frames."
        )
    if fps <= 0:
        reasons.append("The video frame rate is invalid.")
    if len(ordered) < max(12, round(fps)):
        reasons.append("At least one second of metric player tracking is required.")

    step_speeds = []
    for previous, current in zip(ordered, ordered[1:]):
        frame_gap = current[0] - previous[0]
        if frame_gap <= 0 or frame_gap > MAXIMUM_GAP_FRAMES:
            continue
        distance = hypot(current[1] - previous[1], current[2] - previous[2])
        step_speeds.append(distance * fps / frame_gap)

    impossible_steps = sum(
        speed > MAXIMUM_PLAYER_SPEED_MPS for speed in step_speeds
    )
    impossible_ratio = impossible_steps / len(step_speeds) if step_speeds else 1.0
    if step_speeds and impossible_ratio > 0.25:
        reasons.append(
            "Too many court-coordinate jumps exceeded a plausible player speed."
        )
    elif not step_speeds:
        reasons.append("There are not enough consecutive metric positions.")

    return {
        "status": "accepted" if not reasons else "rejected",
        "calibrationConfidence": round(calibration_confidence, 3),
        "trackedMetricPoints": len(ordered),
        "checkedSteps": len(step_speeds),
        "rejectedStepRatio": round(impossible_ratio, 3),
        "reasons": reasons,
    }


def analyse_force_velocity(
    samples: Iterable[TrajectorySample],
    fps: float,
    athlete_mass_kg: float,
    calibration_confidence: float,
) -> Dict:
    """Estimate tangential net force from a metric player trajectory.

    Yuchen's centred median + Savitzky–Golay approach is retained here. Short
    gaps are interpolated, while long gaps and physically impossible jumps
    split the trajectory so the filter never smooths across an ID switch.
    """

    ordered = sorted(samples, key=lambda sample: sample[0])
    assessment = assess_metric_trajectory(ordered, fps, calibration_confidence)
    if not validate_athlete_mass(athlete_mass_kg):
        return _unavailable_force_velocity(
            athlete_mass_kg,
            "Athlete mass must be between 20 and 250 kg.",
            assessment,
        )
    if assessment["status"] != "accepted":
        return _unavailable_force_velocity(
            athlete_mass_kg,
            "Metric trajectory validation failed: "
            + " ".join(assessment["reasons"]),
            assessment,
        )

    window = max(5, int(round(KINEMATICS_WINDOW_SECONDS * fps)) | 1)
    edge = window // 2
    samples_out: List[Dict] = []
    deceleration_efforts: List[Dict] = []
    excluded_samples = 0

    for segment in _continuous_segments(ordered, fps):
        first_frame, last_frame = segment[0][0], segment[-1][0]
        if last_frame - first_frame + 1 < window + 2 * edge:
            continue

        full_frames = np.arange(first_frame, last_frame + 1)
        points = np.asarray([(sample[1], sample[2]) for sample in segment])
        source_frames = np.asarray([sample[0] for sample in segment])
        x_values = np.interp(full_frames, source_frames, points[:, 0])
        y_values = np.interp(full_frames, source_frames, points[:, 1])

        # The bottom-centre of the bounding box approximates the contact point.
        # Median filtering removes one-frame box jitter before differentiation.
        x_values = median_filter(x_values, size=5, mode="nearest")
        y_values = median_filter(y_values, size=5, mode="nearest")
        delta_seconds = 1.0 / fps
        velocity_x = savgol_filter(
            x_values, window, 2, deriv=1, delta=delta_seconds
        )
        velocity_y = savgol_filter(
            y_values, window, 2, deriv=1, delta=delta_seconds
        )
        speeds = np.hypot(velocity_x, velocity_y)
        accelerations = savgol_filter(
            speeds, window, 2, deriv=1, delta=delta_seconds
        )

        valid_frames = full_frames[edge:-edge]
        valid_speeds = speeds[edge:-edge]
        valid_accelerations = accelerations[edge:-edge]
        deceleration_efforts.extend(
            _find_deceleration_efforts(
                valid_frames, valid_speeds, valid_accelerations, fps
            )
        )

        for frame, speed, acceleration in zip(
            valid_frames, valid_speeds, valid_accelerations
        ):
            if (
                speed > MAXIMUM_PLAYER_SPEED_MPS
                or abs(acceleration) > MAXIMUM_ACCELERATION_MPS2
            ):
                excluded_samples += 1
                continue
            force = athlete_mass_kg * float(acceleration)
            samples_out.append(
                {
                    "frame": int(frame),
                    "timeSeconds": round(float(frame) / fps, 4),
                    "velocityMps": round(float(speed), 3),
                    "tangentialAccelerationMps2": round(float(acceleration), 3),
                    "estimatedNetForceN": round(force, 2),
                    "phase": _movement_phase(float(acceleration)),
                }
            )

    if len(samples_out) < 5:
        return _unavailable_force_velocity(
            athlete_mass_kg,
            "No continuous, physically plausible metric segment was long enough "
            "for centred smoothing.",
            assessment,
        )

    force_values = [sample["estimatedNetForceN"] for sample in samples_out]
    velocity_values = [sample["velocityMps"] for sample in samples_out]
    return {
        "status": "experimental",
        "method": "mass_times_video_derived_tangential_acceleration",
        "massKg": round(athlete_mass_kg, 2),
        "velocityUnit": "m/s",
        "forceUnit": "N",
        "samples": samples_out,
        "maximumVelocityMps": round(max(velocity_values), 3),
        "peakPropulsiveForceN": round(max(0.0, max(force_values)), 2),
        "peakBrakingForceN": round(max(0.0, -min(force_values)), 2),
        "decelerationEfforts": deceleration_efforts,
        "excludedSamples": excluded_samples,
        "metricValidation": assessment,
        "note": (
            "Estimated horizontal net force = entered body mass × video-derived "
            "tangential acceleration. This is not measured ground-reaction force."
        ),
    }


def _continuous_segments(
    samples: Sequence[TrajectorySample], fps: float
) -> List[List[TrajectorySample]]:
    """Split at long detection gaps or implausibly fast position changes."""

    segments: List[List[TrajectorySample]] = []
    current: List[TrajectorySample] = []
    for sample in samples:
        if current:
            previous = current[-1]
            frame_gap = sample[0] - previous[0]
            distance = hypot(sample[1] - previous[1], sample[2] - previous[2])
            step_speed = (
                distance * fps / frame_gap if frame_gap > 0 else float("inf")
            )
            if (
                frame_gap <= 0
                or frame_gap > MAXIMUM_GAP_FRAMES
                or step_speed > MAXIMUM_PLAYER_SPEED_MPS
            ):
                segments.append(current)
                current = []
        current.append(sample)
    if current:
        segments.append(current)
    return segments


def _find_deceleration_efforts(
    frames: np.ndarray,
    speeds: np.ndarray,
    accelerations: np.ndarray,
    fps: float,
) -> List[Dict]:
    """Return runs at or below -2 m/s² lasting at least 0.2 seconds."""

    minimum_frames = max(1, int(round(0.2 * fps)))
    below_threshold = accelerations <= -2.0
    efforts = []
    start = 0
    while start < len(below_threshold):
        if not below_threshold[start]:
            start += 1
            continue
        end = start
        while end < len(below_threshold) and below_threshold[end]:
            end += 1
        if end - start >= minimum_frames:
            peak = float(-accelerations[start:end].min())
            efforts.append(
                {
                    "startFrame": int(frames[start]),
                    "endFrame": int(frames[end - 1]),
                    "durationSeconds": round((end - start) / fps, 3),
                    "peakDecelerationMps2": round(peak, 3),
                    "meanDecelerationMps2": round(
                        float(-accelerations[start:end].mean()), 3
                    ),
                    "speedStartMps": round(float(speeds[start]), 3),
                    "speedEndMps": round(float(speeds[end - 1]), 3),
                    "highIntensity": peak >= 3.0,
                }
            )
        start = end
    return efforts


def _movement_phase(acceleration: float) -> str:
    if acceleration > 0.25:
        return "propulsive"
    if acceleration < -0.25:
        return "braking"
    return "steady"


def _unavailable_force_velocity(
    athlete_mass_kg: float, reason: str, assessment: Dict
) -> Dict:
    return {
        "status": "unavailable",
        "method": "mass_times_video_derived_tangential_acceleration",
        "massKg": round(athlete_mass_kg, 2),
        "velocityUnit": "m/s",
        "forceUnit": "N",
        "samples": [],
        "maximumVelocityMps": None,
        "peakPropulsiveForceN": None,
        "peakBrakingForceN": None,
        "decelerationEfforts": [],
        "excludedSamples": 0,
        "metricValidation": assessment,
        "note": reason,
    }
