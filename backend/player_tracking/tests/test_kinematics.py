from statistics import median

import pytest

from hpt_tracking.kinematics import (
    analyse_force_velocity,
    assess_metric_trajectory,
)
from hpt_tracking.metric_motion import force_velocity_profile


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

    assert result["status"] == "experimental"
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

    assert result["status"] == "experimental"
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

    assert result["status"] == "experimental"
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


def test_sustained_acceleration_creates_reviewable_video_events_without_faking_curve():
    # Constant acceleration creates events, but not the descending evidence
    # required for a genuine match Force–Velocity relationship.
    fps = 30
    samples = []
    frame = 0
    x = 0.0
    for _ in range(8):
        for step in range(30):
            t = step / fps
            x += (0.4 + 2.0*t) / fps
            samples.append((frame, x, 5.0))
            frame += 1
        frame += 10  # tracking gap intentionally separates events
    result = analyse_force_velocity(samples, fps, None, .95)
    assert result["method"] == "estimated_match_fv_v3"
    assert result["forceUnit"] == "N/kg"
    assert result["events"]
    assert all(event["videoSeekStartSeconds"] <= event["startTimeSeconds"]
               for event in result["events"])
    assert result["fit"] is None
    assert result["currentCurve"] == []
    assert result["quality"]["reasons"]
    assert result["speedBins"] == []


def test_event_balanced_match_profile_draws_only_observed_descending_curve():
    events = []
    for event_index in range(6):
        samples = []
        for sample_index in range(8):
            speed = .6 + sample_index * .25
            samples.append({
                "speed": speed,
                "acceleration": 2.4 - .55 * speed + event_index * .01,
            })
        events.append({"_samples": samples})

    quality, fit, curve = force_velocity_profile(events, .9, .95)

    assert quality["status"] in {"limited", "good"}
    assert fit["slopeNPerKgPerMps"] < 0
    assert len(curve) == 24
    assert curve[0]["velocityMps"] == pytest.approx(.6)
    assert curve[-1]["velocityMps"] == pytest.approx(2.35)
    assert curve[0]["forceNPerKg"] > curve[-1]["forceNPerKg"]
