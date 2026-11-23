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
SPRINT_WINDOW_SECONDS = 0.35
MIN_ACCELERATION_EVENT_SECONDS = 0.25
MIN_ACCELERATION_EVENT_DELTA_SPEED = 0.40
MIN_ACCELERATION_MPS2 = 0.50
MIN_EVENT_SPEED_MPS = 0.30
MAX_EVENT_HEADING_CHANGE_DEGREES = 30.0
FORCE_VELOCITY_METHOD = "estimated_match_fv_v3"
FORCE_VELOCITY_ALGORITHM_VERSION = "3.0.0"
MIN_PROFILE_EVENTS = 1
MIN_PROFILE_SAMPLES = 8
MIN_PROFILE_SPEED_RANGE_MPS = 0.35
GOOD_PROFILE_EVENTS = 4
GOOD_PROFILE_SPEED_RANGE_MPS = 0.80
CURVE_POINT_COUNT = 24


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


def screened_series(samples, fps, window_seconds=WINDOW_SECONDS):
    """Interpolate short gaps, filter positions, derive speed then signed dv/dt.

    Two half-windows are trimmed because acceleration uses a second filter.
    Rejected points split the outputs; there is NO per-frame distance deadband.
    """
    window = max(5, int(round(window_seconds*fps)) | 1)
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


def _finish_acceleration_event(run, fps, athlete_mass_kg):
    """Convert one continuous positive-acceleration run into a reviewable event."""
    if len(run) < 2:
        return None
    duration = (run[-1]["frame"] - run[0]["frame"]) / fps
    delta_speed = run[-1]["speed"] - run[0]["speed"]
    if duration + 1e-9 < MIN_ACCELERATION_EVENT_SECONDS:
        return None
    if delta_speed + 1e-9 < MIN_ACCELERATION_EVENT_DELTA_SPEED:
        return None
    peak = max(run, key=lambda point: point["acceleration"])
    mean_acceleration = sum(point["acceleration"] for point in run) / len(run)
    event_id = f"fv-{run[0]['frame']}-{run[-1]['frame']}"
    return {
        "eventId": event_id,
        "startFrame": run[0]["frame"],
        "peakFrame": peak["frame"],
        "endFrame": run[-1]["frame"],
        "startTimeSeconds": round(run[0]["timeSeconds"], 4),
        "peakTimeSeconds": round(peak["timeSeconds"], 4),
        "endTimeSeconds": round(run[-1]["timeSeconds"], 4),
        "videoSeekStartSeconds": round(max(0.0, run[0]["timeSeconds"] - 1.5), 4),
        "videoSeekEndSeconds": round(run[-1]["timeSeconds"] + 1.5, 4),
        "durationSeconds": round(duration, 3),
        "startSpeedMps": round(run[0]["speed"], 3),
        "peakSpeedMps": round(max(point["speed"] for point in run), 3),
        "deltaSpeedMps": round(delta_speed, 3),
        "meanAccelerationMps2": round(mean_acceleration, 3),
        "peakAccelerationMps2": round(peak["acceleration"], 3),
        "meanForceNPerKg": round(mean_acceleration, 3),
        "estimatedMeanForceN": (
            round(mean_acceleration * athlete_mass_kg, 2)
            if valid_mass(athlete_mass_kg) else None
        ),
        "startX": round(run[0]["x"], 3),
        "startY": round(run[0]["y"], 3),
        "endX": round(run[-1]["x"], 3),
        "endY": round(run[-1]["y"], 3),
        "quality": "accepted",
        # Kept internally until the event-balanced match relationship is fitted.
        "_samples": run,
    }


def acceleration_events(series, fps, athlete_mass_kg=None):
    """Extract sustained, directionally stable acceleration evidence.

    This intentionally reports observed match events.  It does not infer a
    maximal sprint capacity and does not mix braking samples into the profile.
    """
    events, current = [], []

    def flush():
        nonlocal current
        event = _finish_acceleration_event(current, fps, athlete_mass_kg)
        if event is not None:
            events.append(event)
        current = []

    for point in series:
        eligible = (
            point["acceleration"] >= MIN_ACCELERATION_MPS2
            and point["speed"] >= MIN_EVENT_SPEED_MPS
        )
        if not eligible:
            flush()
            continue
        if current:
            previous = current[-1]
            adjacent = (
                point["segmentId"] == previous["segmentId"]
                and point["frame"] == previous["frame"] + 1
            )
            heading_change = _angle_between(
                (current[0]["vx"], current[0]["vy"]),
                (point["vx"], point["vy"]),
            )
            if not adjacent or heading_change > MAX_EVENT_HEADING_CHANGE_DEGREES:
                flush()
        current.append(point)
    flush()
    return events


def force_velocity_profile(events, tracking_coverage, calibration_confidence):
    """Fit one event-balanced match sprint Force–Velocity relationship."""
    reasons = []
    if calibration_confidence < .70:
        reasons.append("Court calibration confidence was too low for a reliable sprint profile.")
    if len(events) < MIN_PROFILE_EVENTS:
        reasons.append("No valid directionally stable sprint acceleration was identified.")

    # Each event contributes a total weight of one, regardless of its length.
    x_values, y_values, weights = [], [], []
    for event in events:
        samples = event.get("_samples") or []
        if not samples:
            continue
        event_weight = 1.0 / len(samples)
        for point in samples:
            x_values.append(float(point["speed"]))
            y_values.append(float(point["acceleration"]))
            weights.append(event_weight)

    fit, curve = None, []
    if x_values:
        x = np.asarray(x_values, dtype=float)
        y = np.asarray(y_values, dtype=float)
        w = np.asarray(weights, dtype=float)
        speed_min, speed_max = float(np.min(x)), float(np.max(x))
        speed_range = speed_max-speed_min
        if len(x) < MIN_PROFILE_SAMPLES:
            reasons.append("The valid sprint evidence was too short for a stable profile.")
        elif speed_range + 1e-9 < MIN_PROFILE_SPEED_RANGE_MPS:
            reasons.append("Valid sprint accelerations did not cover enough movement speed.")
        else:
            keep = np.ones(len(x), dtype=bool)
            slope = intercept = 0.0
            # Two-pass robust fit removes isolated tracking derivatives without
            # forcing the expected negative slope.
            for _ in range(2):
                slope, intercept = np.polyfit(
                    x[keep], y[keep], 1, w=np.sqrt(w[keep])
                )
                residual = y-(intercept+slope*x)
                centre = float(np.median(residual[keep]))
                mad = float(np.median(np.abs(residual[keep]-centre)))
                if mad <= 1e-9:
                    break
                candidate = np.abs(residual-centre) <= 3.5*1.4826*mad
                if int(candidate.sum()) < max(8, int(.6*len(x))):
                    break
                keep = candidate
            prediction = intercept+slope*x[keep]
            mean = float(np.average(y[keep], weights=w[keep]))
            ss_res = float(np.sum(w[keep]*(y[keep]-prediction)**2))
            ss_tot = float(np.sum(w[keep]*(y[keep]-mean)**2))
            r_squared = 1.0-ss_res/ss_tot if ss_tot > 1e-12 else 0.0
            if slope >= -0.02:
                reasons.append(
                    "The valid sprint evidence did not form a stable descending Force–Velocity relationship."
                )
            else:
                fit = {
                    "interceptNPerKg": round(float(intercept), 6),
                    "slopeNPerKgPerMps": round(float(slope), 6),
                    "minVelocityMps": round(speed_min, 4),
                    "maxVelocityMps": round(speed_max, 4),
                    "rSquared": round(r_squared, 4),
                    "eventCount": len(events),
                }
                for velocity in np.linspace(speed_min, speed_max, CURVE_POINT_COUNT):
                    curve.append({
                        "velocityMps": round(float(velocity), 4),
                        "forceNPerKg": round(
                            max(0.0, float(intercept+slope*velocity)), 4
                        ),
                    })

    speed_range = (
        float(fit["maxVelocityMps"]) - float(fit["minVelocityMps"])
        if fit is not None else 0.0
    )
    unavailable = calibration_confidence < .70 or fit is None
    quality = "unavailable" if unavailable else (
        "good" if tracking_coverage >= .70
        and len(events) >= GOOD_PROFILE_EVENTS
        and speed_range >= GOOD_PROFILE_SPEED_RANGE_MPS else "limited"
    )
    return {
        "status": quality,
        "trackingCoverage": round(tracking_coverage, 3),
        "calibrationConfidence": round(calibration_confidence, 3),
        "validEventCount": len(events),
        "reasons": reasons if unavailable else [],
    }, fit, curve


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


def analyse_metric_motion(samples, fps, athlete_mass_kg, calibration_confidence,
                          tracking_coverage=1.0):
    """Return the shared metrics plus optional mass-dependent force estimates."""
    ordered = list(samples)
    assessment = assess(ordered, fps, calibration_confidence)
    force = {"status": "unavailable", "method": FORCE_VELOCITY_METHOD,
             "algorithmVersion": FORCE_VELOCITY_ALGORITHM_VERSION,
             "massKg": round(athlete_mass_kg, 2) if valid_mass(athlete_mass_kg) else None,
             "velocityUnit": "m/s", "forceUnit": "N/kg", "samples": [], "events": [],
             "speedBins": [], "currentCurve": [], "baselineCurve": [], "fit": None,
             "baselineAnalysisCount": 0, "comparisonSummary": None,
             "recommendedEventIds": [],
             "quality": {"status": "unavailable", "reasons": assessment["reasons"]},
             "maximumVelocityMps": None,
             "peakPropulsiveForceN": None, "peakBrakingForceN": None, "decelerationEfforts": [],
             "excludedSamples": 0, "metricValidation": assessment,
             "note": "Metric trajectory validation failed: " + " ".join(assessment["reasons"])}
    result = {"metrics": None, "forceVelocity": force, "assessment": assessment}
    if assessment["status"] != "accepted":
        return result
    series, excluded = screened_series(ordered, fps)
    profile_series, profile_excluded = screened_series(
        ordered, fps, SPRINT_WINDOW_SECONDS
    )
    force["excludedSamples"] = profile_excluded
    if len(series) >= 5:
        events = deceleration_events(series, fps)
        result["metrics"] = metrics_from_series(series, fps, events, excluded)
        force["decelerationEfforts"] = events
    if len(profile_series) < 5:
        force["note"] = "No continuous sprint segment remained after quality screening."
        return result
    force_samples = [{"frame": p["frame"], "segmentId": p["segmentId"], "timeSeconds": round(p["timeSeconds"], 4),
                      "velocityMps": round(p["speed"], 3), "tangentialAccelerationMps2": round(p["acceleration"], 3),
                      "estimatedForceNPerKg": round(p["acceleration"], 3),
                      "estimatedNetForceN": round(athlete_mass_kg*p["acceleration"], 2)
                      if valid_mass(athlete_mass_kg) else None,
                      "phase": "propulsive" if p["acceleration"] > .25 else "braking" if p["acceleration"] < -.25 else "steady"}
                     for p in (series or profile_series)]
    fv_events = acceleration_events(profile_series, fps, athlete_mass_kg)
    quality, fit, current_curve = force_velocity_profile(
        fv_events, max(0.0, min(1.0, float(tracking_coverage))), calibration_confidence
    )
    public_events = [{key: value for key, value in event.items() if key != "_samples"}
                     for event in fv_events]
    absolute_forces = [p["estimatedNetForceN"] for p in force_samples
                       if p["estimatedNetForceN"] is not None]
    # Keep the raw metric force samples available to the existing result modules.
    # The dedicated match profile is independently withheld when currentCurve is empty.
    force.update(status="experimental",
                 samples=force_samples, events=public_events, speedBins=[], quality=quality,
                 fit=fit, currentCurve=current_curve, baselineCurve=[],
                 baselineAnalysisCount=0,
                 comparisonSummary=(
                     f"This match identified {len(public_events)} valid sprint accelerations. "
                     "Complete at least three comparable analyses to establish a personal baseline."
                     if current_curve else None
                 ),
                 recommendedEventIds=[],
                 maximumVelocityMps=max(p["velocityMps"] for p in force_samples),
                 peakPropulsiveForceN=max(0.0, max(absolute_forces)) if absolute_forces else None,
                 peakBrakingForceN=max(0.0, -min(absolute_forces)) if absolute_forces else None,
                 note=("Observed match acceleration profile derived from court-mapped video. "
                       "N/kg is estimated horizontal net force per kilogram; entered mass only adds "
                       "an absolute-N estimate. This is not measured ground-reaction force, a maximal "
                       "sprint test, fatigue or a training prescription."))
    return result
