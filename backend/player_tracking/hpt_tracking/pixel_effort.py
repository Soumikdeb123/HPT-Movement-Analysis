"""Unvalidated image-motion proxy, NOT Floodlight metabolic power or calories."""
from math import hypot, isfinite
from statistics import median


def pixel_effort(samples, fps):
    """Integrate speed-squared and absolute scalar acceleration over valid time.

    Reference values and weight are demonstration choices, not physiological
    thresholds. Gaps longer than 0.25 s are excluded, never interpolated.
    """
    parameters = dict(speedReferencePxPerSecond=100.0,
                      accelerationReferencePxPerSecondSquared=100.0,
                      accelerationWeight=0.5, maximumGapSeconds=0.25,
                      speedDeadbandPxPerSecond=3.0, medianRadiusSamples=2)
    result = dict(status="unavailable", value=None, unit="AU",
                  method="pixel_motion_effort_v1", coordinateSystem="image_pixels",
                  parameters=parameters,
                  formula="sum(dt/1s * ((v/100px/s)^2 + 0.5*abs(a)/100px/s^2))",
                  note="Experimental pixel-motion proxy; not metabolic power, calories, fatigue or a 0-100 score. Client validation pending. Camera, resolution, perspective, tracking noise and duration affect the result.")
    points = list(samples)
    if not isfinite(fps) or fps <= 0 or len(points) < 3:
        return {**result, "note": "Insufficient trajectory or invalid frame rate; effort unavailable."}
    if any(not all(isfinite(v) for v in p) for p in points):
        return {**result, "note": "Non-finite trajectory; effort unavailable."}
    if any(q[0] <= p[0] for p, q in zip(points, points[1:])):
        return {**result, "note": "Frames must be strictly increasing; effort unavailable."}
    segments, current, excluded = [], [], 0.0
    for p, q in zip(points, points[1:]):
        dt = (q[0] - p[0]) / fps
        if dt > parameters['maximumGapSeconds']:
            if current:
                segments.append(current)
            current = []
            excluded += dt
            continue
        speed = hypot(q[1]-p[1], q[2]-p[2]) / dt
        current.append((q[0]/fps, dt, speed))
    if current:
        segments.append(current)
    total = speed_part = acceleration_part = duration = 0.0
    series = []
    for segment in segments:
        # At least two velocity intervals are needed to estimate acceleration.
        if len(segment) < 2:
            excluded += sum(row[1] for row in segment)
            continue
        speeds = [median([s[2] for s in segment[max(0,i-2):i+3]])
                  for i in range(len(segment))]
        speeds = [v if v >= 3.0 else 0.0 for v in speeds]
        for i, (time, dt, _) in enumerate(segment):
            # Speeds belong to interval midpoints; do not differentiate across gaps.
            a = 0.0 if i == 0 else (speeds[i]-speeds[i-1])/((dt+segment[i-1][1])/2)
            v = speeds[i]
            sv = dt * (v/100.0)**2
            av = dt * 0.5 * abs(a)/100.0
            speed_part += sv
            acceleration_part += av
            total += sv + av
            duration += dt
            series.append(dict(timeSeconds=round(time,4), speedPxPerSecond=round(v,4),
                               accelerationPxPerSecondSquared=round(a,4),
                               cumulativeAU=round(total,4)))
    if not series:
        return {**result, "note": "No sufficiently continuous trajectory; effort unavailable.",
                "excludedSeconds": round(excluded,4)}
    return {**result, "status": "experimental", "value": round(total,3),
            "validDurationSeconds": round(duration,4), "excludedSeconds": round(excluded,4),
            "speedContributionAU": round(speed_part,4),
            "accelerationContributionAU": round(acceleration_part,4),
            "samples": series}
