"""Shared experimental metric series for movement and tangential net force.

Adapted from Yuchen's median/Savitzky–Golay derivatives and Hanyu's integration.
These are video estimates, not ground-reaction force or a fatigue assessment.
"""
from math import hypot, isfinite
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter
from .metrics import _angle_between

MAX_GAP_SECONDS = 0.20
MAX_SPEED = 12.0
MAX_ACCELERATION = 15.0
WINDOW_SECONDS = 0.70


def valid_mass(mass):
    return isinstance(mass, (int, float)) and isfinite(mass) and 20 <= mass <= 250


def assess(samples, fps, confidence):
    """Reject nonfinite data, nonmonotonic frames and excessive tracking jumps."""
    reasons = []
    valid_fps = isfinite(fps) and fps > 0
    points_ok = all(len(p) == 3 and all(isfinite(v) for v in p)
                    and p[0] >= 0 and p[0] == int(p[0]) for p in samples)
    if not isfinite(confidence) or not .70 <= confidence <= 1:
        reasons.append("Court calibration confidence is insufficient or invalid.")
    if not valid_fps:
        reasons.append("Invalid video frame rate.")
    if not points_ok:
        reasons.append("Coordinates and frame numbers must be finite and valid.")
    if points_ok and any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
        reasons.append("Frame numbers must be strictly increasing; duplicates are rejected.")
    if valid_fps and (len(samples) < 12 or (points_ok and samples and
                             (samples[-1][0]-samples[0][0])/fps < .9)):
        reasons.append("At least about one second of metric tracking is required.")
    speeds = []
    if points_ok and valid_fps:
        for a, b in zip(samples, samples[1:]):
            dt = (b[0]-a[0])/fps
            if 0 < dt <= MAX_GAP_SECONDS:
                speeds.append(hypot(b[1]-a[1], b[2]-a[2])/dt)
    ratio = sum(v > MAX_SPEED for v in speeds)/len(speeds) if speeds else 1.0
    if not speeds:
        reasons.append("Not enough consecutive metric positions.")
    elif ratio > .25:
        reasons.append("Too many position jumps exceeded the prototype speed limit.")
    return {"status": "rejected" if reasons else "accepted", "reasons": reasons,
            "calibrationConfidence": round(confidence, 3) if isfinite(confidence) else None,
            "trackedMetricPoints": len(samples), "checkedSteps": len(speeds),
            "rejectedStepRatio": round(ratio, 3)}


def continuous_segments(samples, fps):
    """Split BEFORE filtering so gaps and ID switches do not create false motion."""
    segments, current = [], []
    for p in samples:
        if current:
            a = current[-1]
            dt = (p[0]-a[0])/fps
            if dt <= 0 or dt > MAX_GAP_SECONDS or hypot(p[1]-a[1], p[2]-a[2])/dt > MAX_SPEED:
                segments.append(current)
                current = []
        current.append(p)
    if current:
        segments.append(current)
    return segments


def screened_series(samples, fps):
    """Interpolate short gaps, filter positions, derive speed then signed dv/dt.

    Two half-windows are trimmed because acceleration uses a second filter.
    Rejected points split the outputs; there is NO per-frame distance deadband.
    """
    window = max(5, int(round(WINDOW_SECONDS*fps)) | 1)
    edge = 2*(window//2)
    result, excluded, sid = [], 0, 0
    for segment in continuous_segments(samples, fps):
        frames = np.arange(segment[0][0], segment[-1][0]+1, dtype=int)
        if len(frames) < 2*edge+5:
            excluded += len(frames)
            continue
        source = np.asarray(segment, dtype=float)
        xy = np.column_stack([np.interp(frames, source[:, 0], source[:, k]) for k in (1, 2)])
        xy = median_filter(xy, size=(5, 1), mode="nearest")
        position = savgol_filter(xy, window, 2, axis=0)
        velocity = savgol_filter(xy, window, 2, deriv=1, delta=1/fps, axis=0)
        speed = np.hypot(velocity[:, 0], velocity[:, 1])
        acceleration = savgol_filter(speed, window, 2, deriv=1, delta=1/fps)
        sid += 1
        excluded += 2*edge
        for i in range(edge, len(frames)-edge):
            v, a = float(speed[i]), float(acceleration[i])
            if not (isfinite(v) and isfinite(a)) or v > MAX_SPEED or abs(a) > MAX_ACCELERATION:
                excluded += 1
                sid += 1
                continue
            result.append({"frame": int(frames[i]), "timeSeconds": float(frames[i]/fps),
                           "segmentId": sid, "x": float(position[i, 0]), "y": float(position[i, 1]),
                           "vx": float(velocity[i, 0]), "vy": float(velocity[i, 1]),
                           "speed": v, "acceleration": a})
    return result, excluded


def deceleration_events(series, fps):
    """Prototype: <= -2 m/s² for >=0.2 s, after quality filtering, within one run."""
    groups, current = [], []
    for p in series:
        if current and (p["segmentId"] != current[-1]["segmentId"] or p["frame"] != current[-1]["frame"]+1):
            groups.append(current)
            current = []
        if p["acceleration"] <= -2:
            current.append(p)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    events = []
    for run in groups:
        duration = (run[-1]["frame"]-run[0]["frame"])/fps
        if duration+1e-9 < .2:
            continue
        peak = max(-p["acceleration"] for p in run)
        events.append({"startFrame": run[0]["frame"], "endFrame": run[-1]["frame"],
                       "startTimeSeconds": round(run[0]["timeSeconds"], 4),
                       "endTimeSeconds": round(run[-1]["timeSeconds"], 4), "durationSeconds": round(duration, 3),
                       "peakDecelerationMps2": round(peak, 3),
                       "meanDecelerationMps2": round(sum(-p["acceleration"] for p in run)/len(run), 3),
                       "speedStartMps": round(run[0]["speed"], 3), "speedEndMps": round(run[-1]["speed"], 3),
                       "highIntensity": peak >= 3-1e-6})
    return events


def metrics_from_series(series, fps, events, excluded):
    """Time-integrate velocity ONLY over adjacent retained frames, not gaps."""
    distance = lateral = longitudinal = duration = 0.0
    turns, last_turn = [], -float("inf")
    cumulative = []
    lag = max(1, round(.2*fps))
    for i, p in enumerate(series):
        if i:
            a = series[i-1]
            if a["segmentId"] == p["segmentId"] and p["frame"] == a["frame"]+1:
                dt = p["timeSeconds"]-a["timeSeconds"]
                duration += dt
                distance += (a["speed"]+p["speed"])*.5*dt
                lateral += (abs(a["vx"])+abs(p["vx"]))*.5*dt
                longitudinal += (abs(a["vy"])+abs(p["vy"]))*.5*dt
        cumulative.append({"timeSeconds": round(p["timeSeconds"], 4), "value": round(distance, 3), "segmentId": p["segmentId"]})
        if i >= lag:
            a = series[i-lag]
            if a["segmentId"] == p["segmentId"] and min(a["speed"], p["speed"]) >= .5:
                angle = _angle_between((a["vx"], a["vy"]), (p["vx"], p["vy"]))
                if angle >= 45 and p["timeSeconds"]-last_turn >= .3:
                    turns.append({"timeSeconds": round(p["timeSeconds"], 4), "angleDegrees": round(angle, 2)})
                    last_turn = p["timeSeconds"]
    note = ("Experimental court-mapped estimate over screened intervals only. "
            "Smoothing edges and tracking gaps are excluded; not a full-session total.")
    def metric(value, unit):
        return {"status": "experimental", "value": round(value, 3), "unit": unit, "note": note}
    def samples(key):
        return [{"timeSeconds": round(p["timeSeconds"], 4), "value": round(p[key], 3),
                 "segmentId": p["segmentId"]} for p in series]
    return {"movementPath": {"status": "experimental", "coordinateSystem": "estimated_court_metres",
                             "points": [{k: (round(p[k], 4) if isinstance(p[k], float) else p[k])
                                         for k in ("frame", "timeSeconds", "x", "y", "segmentId")} for p in series], "note": note},
            "totalDistance": {**metric(distance, "m"), "samples": cumulative}, "leftRightDistance": metric(lateral, "m"),
            "forwardBackDistance": metric(longitudinal, "m"),
            "speed": {"status": "experimental", "average": round(distance/duration, 3) if duration else None,
                      "peak": round(max(p["speed"] for p in series), 3), "unit": "m/s", "samples": samples("speed"), "note": note},
            "acceleration": {**metric(max(0.0, max(p["acceleration"] for p in series)), "m/s²"), "samples": samples("acceleration")},
            "deceleration": {**metric(max(0.0, -min(p["acceleration"] for p in series)), "m/s²"),
                             "events": events, "samples": [p for p in samples("acceleration") if p["value"] < 0]},
            "directionChanges": {"status": "experimental", "count": len(turns), "events": turns,
                                 "note": "Prototype: 45° over 0.2 s, speed >=0.5 m/s, debounce 0.3 s. Not validated."},
            "overallEffort": {"status": "unavailable", "value": None, "unit": None,
                              "note": "Overall effort and fatigue definitions await client agreement; force is not an effort score."},
            "coverage": {"validDurationSeconds": round(duration, 3), "retainedSamples": len(series),
                         "excludedSamples": excluded, "note": note}}


def analyse_metric_motion(samples, fps, athlete_mass_kg, calibration_confidence):
    """Return the shared metrics plus optional mass-dependent force estimates."""
    ordered = list(samples)
    assessment = assess(ordered, fps, calibration_confidence)
    force = {"status": "unavailable", "method": "mass_times_video_derived_tangential_acceleration",
             "massKg": round(athlete_mass_kg, 2) if valid_mass(athlete_mass_kg) else None,
             "velocityUnit": "m/s", "forceUnit": "N", "samples": [], "maximumVelocityMps": None,
             "peakPropulsiveForceN": None, "peakBrakingForceN": None, "decelerationEfforts": [],
             "excludedSamples": 0, "metricValidation": assessment,
             "note": "Metric trajectory validation failed: " + " ".join(assessment["reasons"])}
    result = {"metrics": None, "forceVelocity": force, "assessment": assessment}
    if assessment["status"] != "accepted":
        return result
    series, excluded = screened_series(ordered, fps)
    force["excludedSamples"] = excluded
    if len(series) < 5:
        force["note"] = "No continuous metric segment remained after centred smoothing (typically >1.5 seconds required)."
        return result
    events = deceleration_events(series, fps)
    result["metrics"] = metrics_from_series(series, fps, events, excluded)
    force["decelerationEfforts"] = events
    if not valid_mass(athlete_mass_kg):
        force["note"] = "Body mass is optional. Enter 20–250 kg for estimated force; movement metrics remain available."
        return result
    force_samples = [{"frame": p["frame"], "segmentId": p["segmentId"], "timeSeconds": round(p["timeSeconds"], 4),
                      "velocityMps": round(p["speed"], 3), "tangentialAccelerationMps2": round(p["acceleration"], 3),
                      "estimatedNetForceN": round(athlete_mass_kg*p["acceleration"], 2),
                      "phase": "propulsive" if p["acceleration"] > .25 else "braking" if p["acceleration"] < -.25 else "steady"}
                     for p in series]
    force.update(status="experimental", samples=force_samples,
                 maximumVelocityMps=max(p["velocityMps"] for p in force_samples),
                 peakPropulsiveForceN=max(0.0, max(p["estimatedNetForceN"] for p in force_samples)),
                 peakBrakingForceN=max(0.0, -min(p["estimatedNetForceN"] for p in force_samples)),
                 note="Estimated tangential net force = mass × rate of change of speed. Not ground-reaction force, a validated force–velocity profile, overall effort or a fatigue score.")
    return result
