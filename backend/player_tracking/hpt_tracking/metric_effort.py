"""Project-defined external movement load. Input: one filtered metric track."""
from math import isfinite


def metric_effort(series):
    method = "metric_motion_load_v1"
    parts = [0., 0., 0.]
    duration = 0.
    prev = None
    for p in series:
        t, v, a = p['timeSeconds'], p['speed'], p['acceleration']
        if not all(map(isfinite, (t, v, a))) or v < 0:
            prev = None
            continue
        rates = ((v / 2.) ** 2, .5 * max(a, 0.) / 2., .5 * max(-a, 0.) / 2.)
        if prev is not None:
            q, old = prev
            dt = t - q['timeSeconds']
            if p['segmentId'] == q['segmentId'] and p['frame'] == q['frame'] + 1 and dt > 0:
                duration += dt
                for k in range(3):
                    parts[k] += dt * (old[k] + rates[k]) / 2.
        prev = p, rates
    return dict(method=method, status='experimental' if duration else 'unavailable',
                unit='AU', value=sum(parts) if duration else None,
                validSeconds=duration, auPerValidMinute=sum(parts)*60/duration if duration else None,
                speedAU=parts[0], accelerationAU=parts[1], brakingAU=parts[2],
                note=(f'Based on {duration:.1f} s of filtered metric motion for this track. '
                      'External movement only; not fatigue or calories.'))
