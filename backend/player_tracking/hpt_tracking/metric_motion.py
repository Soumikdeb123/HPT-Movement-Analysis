"""Shared experimental metric series for movement and tangential net force.

Adapted from Yuchen's median/Savitzky–Golay derivatives and Hanyu's integration.
These are video estimates, not ground-reaction force or a fatigue assessment.
"""
from math import hypot, isfinite
import numpy as np
from scipy.ndimage import median_filter
from scipy.optimize import least_squares
from scipy.signal import savgol_filter
from .metrics import _angle_between

MAX_GAP_SECONDS = 0.20
MAX_SPEED = 12.0
MAX_ACCELERATION = 15.0
WINDOW_SECONDS = 0.70
FORCE_VELOCITY_METHOD = "observed_movement_fv_v5"
FORCE_VELOCITY_ALGORITHM_VERSION = "5.0.0"
CURVE_POINT_COUNT = 40
MIN_PROFILE_SPEED_MPS = 0.15
MIN_PROFILE_ACCELERATION_MPS2 = 0.12
MOVEMENT_MOMENT_SECONDS = 0.70
MOVEMENT_MOMENT_LEAD_SECONDS = 0.50
MOVEMENT_SPEED_WINDOW_SECONDS = 0.20
MOVEMENT_ENDPOINT_SECONDS = 0.15
MOVEMENT_MERGE_SECONDS = 0.75
MOVEMENT_DIRECTION_CHANGE_DEGREES = 80.0
MOVEMENT_DIRECTION_MIN_SPEED = 0.35
MOVEMENT_POSITIVE_ACCELERATION_RATIO = 0.70
MOVEMENT_MAX_BRAKING_MPS2 = -0.75


def _hill_model(parameters, values):
    """Evaluate the smooth session Force–Velocity relationship."""
    scale, half, shape = parameters
    values = np.asarray(values, dtype=float)
    return scale/(1.0+(values/half)**shape)


def force_velocity_curve_parameters(profile):
    """Return stored Hill parameters, or recover them from an older curve.

    Older completed analyses predate persisted model coefficients. Refitting
    their already-generated smooth curve lets those sessions participate in a
    new personal baseline without rerunning video tracking.
    """
    fit = profile.get("fit") or {}
    names = ("scaleNPerKg", "halfVelocityMps", "shape")
    if all(isinstance(fit.get(name), (int, float)) and
           isfinite(float(fit[name])) for name in names):
        return np.asarray([float(fit[name]) for name in names], dtype=float)
    curve = profile.get("currentCurve") or []
    points = [
        (float(point["velocityMps"]), float(point["forceNPerKg"]))
        for point in curve
        if isinstance(point.get("velocityMps"), (int, float))
        and isinstance(point.get("forceNPerKg"), (int, float))
        and isfinite(float(point["velocityMps"]))
        and isfinite(float(point["forceNPerKg"]))
    ]
    if len(points) < 2:
        return None
    x = np.asarray([point[0] for point in points], dtype=float)
    y = np.asarray([point[1] for point in points], dtype=float)
    minimum, maximum = float(np.min(x)), float(np.max(x))
    amplitude = max(.05, float(np.max(y)))
    half_speed = max(.08, float(np.median(x)))
    solved = least_squares(
        lambda parameters: _hill_model(parameters, x)-y,
        x0=np.asarray([min(MAX_ACCELERATION-.001, max(.011, amplitude*1.5)),
                       half_speed, 1.2]),
        bounds=([.01, max(.03, minimum*.1), .40],
                [MAX_ACCELERATION, max(1.0, maximum*6.0), 4.5]),
        loss="soft_l1",
    )
    return solved.x


def evaluate_force_velocity_profile(profile, velocities):
    """Evaluate one completed session at requested speeds."""
    parameters = force_velocity_curve_parameters(profile)
    if parameters is None:
        return None
    return _hill_model(parameters, np.asarray(velocities, dtype=float))


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


def movement_moments(series, fps, athlete_mass_kg=None):
    """Select the three fixed coach-reviewable movement windows.

    Player direction is not used to exclude lateral, diagonal or post-turn
    movement.  A major reversal is used only as a boundary so one review
    window does not mix braking, turning and re-acceleration.  Each category
    has its own candidate pool: propulsion requires sustained acceleration,
    speed gain uses robust endpoint averages, and highest speed scans every
    continuous valid movement window without an acceleration gate.

    When categories describe the same movement, they are merged into one
    multi-label moment instead of presenting duplicate clips.
    Baseline-difference moments are attached later, once the player's
    personal baseline is available.
    """
    if not series or not isfinite(fps) or fps <= 0:
        return []

    def continuous(run):
        return not any(
            b["segmentId"] != a["segmentId"] or
            b["frame"] != a["frame"]+1
            for a, b in zip(run, run[1:])
        )

    def robust_mean(values):
        values = np.asarray(values, dtype=float)
        if len(values) >= 5:
            low, high = np.percentile(values, [10, 90])
            values = np.clip(values, low, high)
        return float(np.mean(values))

    def crosses_major_turn(run):
        edge_count = max(2, int(round(len(run)*.20)))
        start_vector = (
            robust_mean([point["vx"] for point in run[:edge_count]]),
            robust_mean([point["vy"] for point in run[:edge_count]]),
        )
        end_vector = (
            robust_mean([point["vx"] for point in run[-edge_count:]]),
            robust_mean([point["vy"] for point in run[-edge_count:]]),
        )
        if min(hypot(*start_vector), hypot(*end_vector)) < MOVEMENT_DIRECTION_MIN_SPEED:
            return False
        return _angle_between(start_vector, end_vector) >= MOVEMENT_DIRECTION_CHANGE_DEGREES

    def describe(run, endpoint_count):
        accelerations = [float(point["acceleration"]) for point in run]
        speeds = [float(point["speed"]) for point in run]
        # Endpoint medians make speed gain insensitive to one noisy frame.
        start_speed = float(np.median(speeds[:endpoint_count]))
        end_speed = float(np.median(speeds[-endpoint_count:]))
        return {
            "run": run,
            "meanForce": max(0.0, robust_mean(accelerations)),
            "speedGain": end_speed-start_speed,
            "peakSpeed": max(speeds),
            "stableSpeed": robust_mean(speeds),
            "positiveRatio": sum(value > 0 for value in accelerations)/len(accelerations),
            "strongestBraking": min(accelerations),
        }

    long_window = max(5, int(round(MOVEMENT_MOMENT_SECONDS*fps)))
    endpoint_count = max(2, min(
        long_window//3,
        int(round(MOVEMENT_ENDPOINT_SECONDS*fps)),
    ))
    propulsion_candidates, gain_candidates = [], []
    for start in range(0, max(0, len(series)-long_window+1)):
        run = series[start:start+long_window]
        if not continuous(run) or crosses_major_turn(run):
            continue
        candidate = describe(run, endpoint_count)
        if (
            candidate["positiveRatio"] >= MOVEMENT_POSITIVE_ACCELERATION_RATIO and
            candidate["strongestBraking"] >= MOVEMENT_MAX_BRAKING_MPS2 and
            candidate["meanForce"] >= MIN_PROFILE_ACCELERATION_MPS2 and
            candidate["speedGain"] > .03
        ):
            propulsion_candidates.append(candidate)
        if candidate["speedGain"] >= .12:
            gain_candidates.append(candidate)

    speed_window = max(3, int(round(MOVEMENT_SPEED_WINDOW_SECONDS*fps)))
    speed_candidates = []
    for start in range(0, max(0, len(series)-speed_window+1)):
        run = series[start:start+speed_window]
        if not continuous(run):
            continue
        candidate = describe(run, max(1, speed_window//3))
        if candidate["stableSpeed"] >= MIN_PROFILE_SPEED_MPS:
            speed_candidates.append(candidate)

    chosen = []
    selectors = (
        ("Strongest propulsion", propulsion_candidates,
         lambda item: item["meanForce"]),
        ("Largest speed gain", gain_candidates,
         lambda item: item["speedGain"]),
        ("Highest movement speed", speed_candidates,
         lambda item: item["stableSpeed"]),
    )

    def same_movement(first_run, second_run):
        first_start, first_end = first_run[0]["frame"], first_run[-1]["frame"]
        second_start, second_end = second_run[0]["frame"], second_run[-1]["frame"]
        overlaps = not (first_end < second_start or second_end < first_start)
        first_centre = (
            float(first_run[0]["timeSeconds"])+
            float(first_run[-1]["timeSeconds"])
        )/2
        second_centre = (
            float(second_run[0]["timeSeconds"])+
            float(second_run[-1]["timeSeconds"])
        )/2
        return overlaps or abs(first_centre-second_centre) <= MOVEMENT_MERGE_SECONDS

    for label, candidates, key in selectors:
        if not candidates:
            continue
        winner = max(candidates, key=key)
        existing = next(
            (item for item in chosen
             if same_movement(item["run"], winner["run"])),
            None,
        )
        if existing is not None:
            existing["labels"].append(label)
        else:
            item = dict(winner)
            item["labels"] = [label]
            chosen.append(item)

    events = []
    for item in sorted(chosen, key=lambda value: value["run"][0]["frame"]):
        run = item["run"]
        peak = max(run, key=lambda point: point["acceleration"])
        mean_force = item["meanForce"]
        event_id = f"movement-{run[0]['frame']}-{run[-1]['frame']}"
        events.append({
            "eventId": event_id,
            "label": " · ".join(item["labels"]),
            "startFrame": run[0]["frame"],
            "peakFrame": peak["frame"],
            "endFrame": run[-1]["frame"],
            "startTimeSeconds": round(run[0]["timeSeconds"], 4),
            "peakTimeSeconds": round(peak["timeSeconds"], 4),
            "endTimeSeconds": round(run[-1]["timeSeconds"], 4),
            "videoSeekStartSeconds": round(
                max(0.0, run[0]["timeSeconds"]-MOVEMENT_MOMENT_LEAD_SECONDS), 4
            ),
            "videoSeekEndSeconds": round(run[-1]["timeSeconds"]+2.0, 4),
            "durationSeconds": round((run[-1]["frame"]-run[0]["frame"])/fps, 3),
            "startSpeedMps": round(float(run[0]["speed"]), 3),
            "peakSpeedMps": round(item["peakSpeed"], 3),
            "deltaSpeedMps": round(item["speedGain"], 3),
            "meanAccelerationMps2": round(mean_force, 3),
            "peakAccelerationMps2": round(float(peak["acceleration"]), 3),
            "meanForceNPerKg": round(mean_force, 3),
            "estimatedMeanForceN": (
                round(mean_force*athlete_mass_kg, 2)
                if valid_mass(athlete_mass_kg) else None
            ),
            "startX": round(float(run[0]["x"]), 3),
            "startY": round(float(run[0]["y"]), 3),
            "endX": round(float(run[-1]["x"]), 3),
            "endY": round(float(run[-1]["y"]), 3),
            "excluded": False,
            "quality": "accepted",
        })
    return events


def force_velocity_profile(series, tracking_coverage, calibration_confidence,
                           excluded_ranges=()):
    """Fit one smooth session-average propulsion curve from valid movement.

    All retained positive-propulsion samples contribute.  Similar speeds are
    summarised with robust medians and a constrained reciprocal model produces
    the familiar smooth Force–Velocity shape over the observed speed range.
    Global tracking coverage is reported but is deliberately not a gate.
    """
    reasons = []
    if calibration_confidence < .70:
        reasons.append("Reliable court coordinates are required.")

    ranges = [
        (float(start), float(end)) for start, end in excluded_ranges
        if isfinite(float(start)) and isfinite(float(end))
    ]
    pairs = []
    for point in series:
        speed = point.get("speed", point.get("velocityMps"))
        force = point.get("acceleration", point.get("tangentialAccelerationMps2"))
        time = point.get("timeSeconds", 0.0)
        if speed is None or force is None:
            continue
        speed, force, time = float(speed), float(force), float(time)
        if not all(isfinite(value) for value in (speed, force, time)):
            continue
        if any(start <= time <= end for start, end in ranges):
            continue
        if speed >= MIN_PROFILE_SPEED_MPS and force >= MIN_PROFILE_ACCELERATION_MPS2:
            pairs.append((speed, force))

    fit, curve = None, []
    if calibration_confidence >= .70 and pairs:
        speeds = np.asarray([item[0] for item in pairs], dtype=float)
        forces = np.asarray([item[1] for item in pairs], dtype=float)
        low, high = np.percentile(speeds, [2, 98]) if len(speeds) >= 20 else (
            float(np.min(speeds)), float(np.max(speeds)))
        keep = (speeds >= low) & (speeds <= high)
        speeds, forces = speeds[keep], forces[keep]
        speed_min, speed_max = float(np.min(speeds)), float(np.max(speeds))
        if speed_max-speed_min < .12:
            reasons.append("More movement across different speeds is required.")
        else:
            bin_count = min(9, max(3, int(round(np.sqrt(len(speeds))))))
            boundaries = np.linspace(speed_min, speed_max, bin_count+1)
            centres, summaries, supports = [], [], []
            for index, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
                mask = ((speeds >= left) & (speeds <= right)) if index == bin_count-1 \
                    else ((speeds >= left) & (speeds < right))
                if not np.any(mask):
                    continue
                selected_speed, selected_force = speeds[mask], forces[mask]
                centres.append(float(np.median(selected_speed)))
                summaries.append(float(np.median(selected_force)))
                supports.append(int(np.sum(mask)))
            if len(centres) >= 2:
                x = np.asarray(centres, dtype=float)
                y = np.asarray(summaries, dtype=float)
                weights = np.sqrt(np.asarray(supports, dtype=float))
                # A Hill-style curve expresses the average inverse relationship
                # requested for the coach view. The amplitude and curvature are
                # estimated from every retained propulsive sample; the curve is
                # drawn only across speeds actually observed in this video.
                amplitude = max(.05, float(np.percentile(y, 85)))
                half_speed = max(.15, float(np.median(x)))

                def residual(parameters):
                    return (_hill_model(parameters, x)-y)*weights

                solved = least_squares(
                    residual,
                    x0=np.asarray([
                        min(MAX_ACCELERATION-.001, max(.011, amplitude*1.5)),
                        half_speed,
                        1.2,
                    ]),
                    bounds=(
                        [.01, max(.08, speed_min*.35), .65],
                        [MAX_ACCELERATION, max(speed_min+.05, speed_max*1.15), 3.5],
                    ),
                    loss="soft_l1",
                )
                curve_x = np.linspace(speed_min, speed_max, CURVE_POINT_COUNT)
                curve_y = _hill_model(solved.x, curve_x)
                curve = [
                    {"velocityMps": round(float(velocity), 4),
                     "forceNPerKg": round(max(0.0, float(force)), 4)}
                    for velocity, force in zip(curve_x, curve_y)
                ]
                fit = {
                    "model": "robust_session_hill",
                    "scaleNPerKg": round(float(solved.x[0]), 6),
                    "halfVelocityMps": round(float(solved.x[1]), 6),
                    "shape": round(float(solved.x[2]), 6),
                    "minVelocityMps": round(speed_min, 4),
                    "maxVelocityMps": round(speed_max, 4),
                    "sampleCount": len(pairs),
                    "binPoints": [
                        {"velocityMps": round(value, 4),
                         "forceNPerKg": round(force, 4),
                         "sampleCount": support}
                        for value, force, support in zip(centres, summaries, supports)
                    ],
                }
            else:
                reasons.append("More movement across different speeds is required.")
    elif not pairs:
        reasons.append("No usable propulsive movement was found.")

    unavailable = calibration_confidence < .70 or fit is None
    return {
        "status": "unavailable" if unavailable else "available",
        "trackingCoverage": round(tracking_coverage, 3),
        "calibrationConfidence": round(calibration_confidence, 3),
        "validEventCount": 0,
        "validSampleCount": len(pairs),
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
             "peakEstimatedPropulsionN": None,
             "peakPropulsiveForceN": None, "peakBrakingForceN": None, "decelerationEfforts": [],
             "excludedSamples": 0, "metricValidation": assessment,
             "note": "Metric trajectory validation failed: " + " ".join(assessment["reasons"])}
    result = {"metrics": None, "forceVelocity": force, "assessment": assessment}
    if assessment["status"] != "accepted":
        return result
    series, excluded = screened_series(ordered, fps)
    profile_series = series
    force["excludedSamples"] = excluded
    if len(series) >= 5:
        events = deceleration_events(series, fps)
        result["metrics"] = metrics_from_series(series, fps, events, excluded)
        force["decelerationEfforts"] = events
    if len(profile_series) < 5:
        force["note"] = "No continuous metric movement remained after quality screening."
        return result
    force_samples = [{"frame": p["frame"], "segmentId": p["segmentId"], "timeSeconds": round(p["timeSeconds"], 4),
                      "velocityMps": round(p["speed"], 3), "tangentialAccelerationMps2": round(p["acceleration"], 3),
                      "estimatedForceNPerKg": round(p["acceleration"], 3),
                      "estimatedNetForceN": round(athlete_mass_kg*p["acceleration"], 2)
                      if valid_mass(athlete_mass_kg) else None,
                      "phase": "propulsive" if p["acceleration"] > .25 else "braking" if p["acceleration"] < -.25 else "steady"}
                     for p in (series or profile_series)]
    fv_events = movement_moments(profile_series, fps, athlete_mass_kg)
    quality, fit, current_curve = force_velocity_profile(
        profile_series, max(0.0, min(1.0, float(tracking_coverage))),
        calibration_confidence
    )
    public_events = []
    for event in fv_events:
        public = {key: value for key, value in event.items() if key != "_samples"}
        public_events.append(public)
    absolute_forces = [p["estimatedNetForceN"] for p in force_samples
                       if p["estimatedNetForceN"] is not None]
    # Keep the raw metric force samples available to the existing result modules.
    # The dedicated match profile is independently withheld when currentCurve is empty.
    force.update(status="available" if current_curve else "unavailable",
                 samples=force_samples, events=public_events, speedBins=[], quality=quality,
                 fit=fit, currentCurve=current_curve, baselineCurve=[],
                 baselineAnalysisCount=0,
                 comparisonSummary=("Personal baseline is being built (3 analyses required)"
                                    if current_curve else None),
                 recommendedEventIds=[],
                 maximumVelocityMps=max(p["velocityMps"] for p in force_samples),
                 peakEstimatedPropulsionN=(
                     round(max(point["forceNPerKg"] for point in current_curve) * athlete_mass_kg, 1)
                     if current_curve and valid_mass(athlete_mass_kg) else None
                 ),
                 peakPropulsiveForceN=max(0.0, max(absolute_forces)) if absolute_forces else None,
                 peakBrakingForceN=max(0.0, -min(absolute_forces)) if absolute_forces else None,
                 note="Session-average propulsion from court-mapped movement.")
    return result
