"""API adapter for Yuchen's unmodified private distance/kinematics implementation.

No second smoothing, acceleration clipping or speed integration is applied here.
"""
from math import isfinite
import numpy as np
from .yuchen_player_tracker import PlayerTracker, PlayerDetection
from .metric_motion import metrics_from_series, valid_mass


def analyse_metric_motion(samples, fps, athlete_mass_kg, confidence):
    force = {'status': 'unavailable', 'samples': [], 'massKg': athlete_mass_kg,
             'velocityUnit': 'm/s', 'forceUnit': 'N',
             'note': 'Valid court calibration and continuous metric positions are required.'}
    result = {'metrics': None, 'forceVelocity': force}
    if not isfinite(fps) or fps <= 0 or confidence < .7 or not samples:
        return result
    if any(not all(isfinite(v) for v in p) for p in samples):
        return result
    if any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
        return result
    # Avoid constructing/loading a second YOLO model. These upstream routines
    # operate only on supplied positions and the following explicit settings.
    tracker = PlayerTracker.__new__(PlayerTracker)
    tracker.tracks, tracker.removed_tracks = {}, {}
    tracker.next_track_id = 0
    tracker.colors = [(255, 0, 0)]
    tracker.homography_matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    tracker.fps = fps
    tracker.max_player_speed_mps = 12.0
    tracker.court_smoothing_window = 9
    tracker.kinematics_window_s = .7
    tracker.kinematics_max_gap_frames = 5
    tracker.deceleration_threshold_mps2 = 2.0
    tracker.high_intensity_deceleration_mps2 = 3.0
    tracker.min_deceleration_duration_s = .2
    for i, (frame, x, y) in enumerate(samples):
        detection = PlayerDetection([x, y, x, y], (x, y), 1., (x, y))
        if i == 0:
            tracker._create_new_track(detection, int(frame))
        else:
            tracker._update_track(0, detection, int(frame))
    tracker.compute_kinematics()
    track = tracker.tracks[0]
    positions = {int(f): (x, y) for f, x, y in samples}
    source_array = np.asarray(samples)
    series, sid, previous = [], 0, None
    for frame, (speed, acceleration) in sorted(track.kinematics_by_frame.items()):
        if previous is None or frame != previous+1:
            sid += 1
        # Coordinates only for present observations; upstream kinematics also
        # contains interpolated short gaps, so interpolate for report geometry.
        x, y = positions[frame] if frame in positions else (
            float(np.interp(frame, source_array[:, 0], source_array[:, 1])),
            float(np.interp(frame, source_array[:, 0], source_array[:, 2])))
        vx = vy = 0.
        if series and frame == previous+1:
            vx, vy = (x-series[-1]['x'])*fps, (y-series[-1]['y'])*fps
        series.append(dict(frame=frame, timeSeconds=frame/fps, segmentId=sid,
                           x=x, y=y, vx=vx, vy=vy, speed=float(speed), acceleration=float(acceleration)))
        previous = frame
    if not series:
        force['note'] = 'No segment long enough for the centred kinematic filter.'
        return result
    events = [{'startFrame': e['start_frame'], 'endFrame': e['end_frame'],
               'startTimeSeconds': e['start_frame']/fps, 'endTimeSeconds': e['end_frame']/fps,
               'durationSeconds': e['duration_s'], 'peakDecelerationMps2': e['peak_deceleration_mps2'],
               'meanDecelerationMps2': e['mean_deceleration_mps2'], 'highIntensity': e['high_intensity']}
              for e in track.deceleration_efforts]
    metrics = metrics_from_series(series, fps, events, max(0, len(samples)-len(series)))
    note = ('Cumulative displacement of a 9-detection moving average; '
            '12 m/s jumps reset distance smoothing. Speed/acceleration use median-5 and '
            '0.7 s quadratic Savitzky–Golay filters, splitting gaps >5 frames. '
            'Distance and speed use different smoothing and coverage; not a whole-session guarantee.')
    cumulative, points, sid, previous = [], [], 0, None
    lateral = longitudinal = 0.
    recent, smoothed, last = [], None, None
    for (frame, x, y), distance in zip(samples, track.cumulative_distance_history_m):
        if previous is None or frame-previous > 5:
            sid += 1
        if last and ((x-last[1])**2+(y-last[2])**2)**.5*fps/(frame-last[0]) > 12:
            recent, smoothed = [], None
            sid += 1
        recent.append((x, y))
        recent = recent[-9:]
        current = tuple(sum(p[k] for p in recent)/len(recent) for k in (0, 1))
        if smoothed is not None:
            lateral += abs(current[0]-smoothed[0])
            longitudinal += abs(current[1]-smoothed[1])
        smoothed, last, previous = current, (frame, x, y), frame
        cumulative.append({'timeSeconds': frame/fps, 'value': distance, 'segmentId': sid})
        points.append({'frame': frame, 'timeSeconds': frame/fps, 'x': x, 'y': y, 'segmentId': sid})
    metrics['totalDistance'].update(value=track.total_distance_meters, samples=cumulative, note=note)
    metrics['leftRightDistance'].update(value=lateral, note=note)
    metrics['forwardBackDistance'].update(value=longitudinal, note=note)
    metrics['movementPath'].update(points=points, note=note)
    metrics['speed'].update(average=sum(p['speed'] for p in series)/len(series), note=note)
    for key in ('acceleration', 'deceleration'):
        metrics[key]['note'] = note
    result['metrics'] = metrics
    force['note'] = 'Enter body mass (20–250 kg) to estimate tangential net force.'
    if valid_mass(athlete_mass_kg):
        fs = [dict(frame=p['frame'], segmentId=p['segmentId'], timeSeconds=p['timeSeconds'],
                   velocityMps=p['speed'], tangentialAccelerationMps2=p['acceleration'],
                   estimatedNetForceN=athlete_mass_kg*p['acceleration'],
                   phase='propulsive' if p['acceleration'] > .25 else 'braking' if p['acceleration'] < -.25 else 'steady') for p in series]
        force.update(status='experimental', samples=fs,
                     maximumVelocityMps=max(p['velocityMps'] for p in fs),
                     peakPropulsiveForceN=max(0., max(p['estimatedNetForceN'] for p in fs)),
                     peakBrakingForceN=max(0., -min(p['estimatedNetForceN'] for p in fs)),
                     note='Entered mass × filtered tangential acceleration. Not measured ground-reaction force or fatigue.')
    return result
