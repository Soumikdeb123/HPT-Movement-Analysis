from statistics import median

import pytest

from hpt_tracking.kinematics import (
    analyse_force_velocity,
    assess_metric_trajectory,
)
from hpt_tracking.metric_motion import force_velocity_profile, movement_moments


def _trajectory(position_at_time, seconds=4.0, fps=30.0):
    return [
        (frame, float(position_at_time(frame / fps)), 5.0)
        for frame in range(round(seconds * fps))
    ]


def test_constant_speed_has_near_zero_estimated_force():
    result = analyse_force_velocity(
        _trajectory(lambda time: 2.0 * time),
        fps=30.0,
        athlete_mass_kg=70.0,
        calibration_confidence=0.95,
    )

    # Constant speed still exposes the underlying force samples, but there is
    # no positive propulsion relationship from which to draw an F-V curve.
    assert result["status"] == "unavailable"
    forces = [sample["estimatedNetForceN"] for sample in result["samples"]]
    assert median(forces) == pytest.approx(0.0, abs=1.0)


def test_entered_mass_scales_force_from_known_acceleration():
    # x(t) = 1t + 1t² gives a constant 2 m/s² acceleration.
    trajectory = _trajectory(lambda time: time + time * time, seconds=5.0)
    result = analyse_force_velocity(
        trajectory,
        fps=30.0,
        athlete_mass_kg=70.0,
        calibration_confidence=0.95,
    )

    assert result["status"] == "available"
    forces = [sample["estimatedNetForceN"] for sample in result["samples"]]
    assert median(forces) == pytest.approx(140.0, abs=2.0)
    assert result["peakPropulsiveForceN"] == pytest.approx(140.0, abs=3.0)


def test_sustained_braking_is_reported_as_a_deceleration_effort():
    # Speed falls from 6 m/s at a constant -3 m/s² without reversing direction.
    trajectory = _trajectory(lambda time: 6.0 * time - 1.5 * time * time, seconds=1.8)
    result = analyse_force_velocity(
        trajectory,
        fps=30.0,
        athlete_mass_kg=70.0,
        calibration_confidence=0.95,
    )

    assert result["status"] == "unavailable"
    assert result["peakBrakingForceN"] == pytest.approx(210.0, abs=5.0)
    assert result["decelerationEfforts"]
    assert result["decelerationEfforts"][0]["highIntensity"] is True


def test_low_confidence_mapping_is_withheld_instead_of_returning_newtons():
    result = analyse_force_velocity(
        _trajectory(lambda time: 2.0 * time),
        fps=30.0,
        athlete_mass_kg=70.0,
        calibration_confidence=0.55,
    )

    assert result["status"] == "unavailable"
    assert result["samples"] == []
    assert "validation failed" in result["note"]


def test_many_impossible_jumps_reject_the_metric_trajectory():
    samples = [(frame, float(frame * 2), 0.0) for frame in range(60)]
    assessment = assess_metric_trajectory(samples, fps=30.0, calibration_confidence=0.95)

    assert assessment["status"] == "rejected"
    assert assessment["rejectedStepRatio"] > 0.25


def test_sustained_acceleration_creates_reviewable_movement_moments():
    fps = 30
    samples = []
    frame = 0
    x = 0.0
    for _ in range(3):
        for step in range(90):
            t = step / fps
            x += (0.4 + 2.0*t) / fps
            samples.append((frame, x, 5.0))
            frame += 1
        frame += 10  # tracking gap intentionally separates events
    result = analyse_force_velocity(samples, fps, None, .95)
    assert result["method"] == "observed_movement_fv_v5"
    assert result["forceUnit"] == "N/kg"
    assert result["events"]
    assert all(event["videoSeekStartSeconds"] <= event["startTimeSeconds"]
               for event in result["events"])
    assert all(
        event["startTimeSeconds"]-event["videoSeekStartSeconds"] <= .5001
        for event in result["events"]
    )
    assert all(event["label"] != "Key movement" for event in result["events"])
    combined_labels = " · ".join(event["label"] for event in result["events"])
    assert "Strongest propulsion" in combined_labels
    assert "Largest speed gain" in combined_labels
    assert "Highest movement speed" in combined_labels
    assert 1 <= len(result["events"]) <= 3
    assert any(" · " in event["label"] for event in result["events"])
    assert len({int(event["startTimeSeconds"]) for event in result["events"]}) == len(
        result["events"]
    )
    assert result["quality"]["status"] in {"available", "unavailable"}
    assert result["speedBins"] == []


def test_session_profile_draws_only_observed_smooth_descending_curve():
    series = []
    for repeat in range(6):
        for sample_index in range(12):
            speed = .4 + sample_index * .2
            series.append({
                "timeSeconds": len(series)/30,
                "speed": speed,
                "acceleration": 2.8/(1+(speed/1.4)**1.5) + repeat*.005,
            })

    quality, fit, curve = force_velocity_profile(series, .02, .95)

    assert quality["status"] == "available"
    assert fit["model"] == "robust_session_hill"
    assert len(curve) == 40
    assert .4 <= curve[0]["velocityMps"] < curve[-1]["velocityMps"] <= 2.7
    assert curve[0]["forceNPerKg"] > curve[-1]["forceNPerKg"]
    # The requested coach-facing profile is genuinely curved, not a straight
    # line joined between two endpoints.
    midpoint = curve[len(curve)//2]["forceNPerKg"]
    linear_midpoint = (curve[0]["forceNPerKg"]+curve[-1]["forceNPerKg"])/2
    assert abs(midpoint-linear_midpoint) > .03


def test_profile_has_no_global_coverage_or_event_count_gate():
    samples = [{
        "timeSeconds": index/30,
        "speed": .3 + index*.2,
        "acceleration": 2.6/(1+((.3+index*.2)/1.2)**1.4),
    } for index in range(10)]
    quality, fit, curve = force_velocity_profile(
        samples, .03, .95
    )

    assert quality["status"] == "available"
    assert quality["validSampleCount"] == len(samples)
    assert fit["sampleCount"] == len(samples)
    assert len(curve) == 40


def _movement_series(segment_id, start_frame, speeds, accelerations):
    return [{
        "frame": start_frame+index,
        "segmentId": segment_id,
        "timeSeconds": (start_frame+index)/30,
        "x": index/30,
        "y": 0.0,
        "vx": speed,
        "vy": 0.0,
        "speed": speed,
        "acceleration": acceleration,
    } for index, (speed, acceleration) in enumerate(zip(speeds, accelerations))]


def test_highest_speed_scans_steady_movement_without_acceleration_gate():
    series = _movement_series(1, 0, [4.0]*30, [0.0]*30)

    events = movement_moments(series, 30)

    assert len(events) == 1
    assert events[0]["label"] == "Highest movement speed"
    assert events[0]["peakSpeedMps"] == 4.0


def test_strongest_propulsion_rejects_window_that_contains_hard_braking():
    mixed = _movement_series(
        1, 0,
        [1.0+index*.04 for index in range(21)],
        [2.0]*15+[-3.0]*6,
    )
    sustained = _movement_series(
        2, 100,
        [1.0+index*.02 for index in range(21)],
        [.6]*21,
    )

    events = movement_moments(mixed+sustained, 30)
    propulsion = next(event for event in events
                      if "Strongest propulsion" in event["label"])

    assert propulsion["startFrame"] >= 100


def test_largest_speed_gain_uses_endpoint_medians_not_one_frame_spike():
    noisy = _movement_series(
        1, 0,
        [1.0]*20+[8.0],
        [0.2]*21,
    )
    sustained_speeds = [1.0]*5+[1.0+index*.06 for index in range(16)]
    sustained = _movement_series(2, 100, sustained_speeds, [.7]*21)

    events = movement_moments(noisy+sustained, 30)
    gain = next(event for event in events
                if "Largest speed gain" in event["label"])

    assert gain["startFrame"] >= 100
