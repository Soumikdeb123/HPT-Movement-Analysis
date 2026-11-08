"""Known-motion regression checks; these do not establish real-video accuracy."""
import math
import cv2
import numpy as np
import pytest
from hpt_tracking.metric_motion import analyse_metric_motion, assess, deceleration_events
from hpt_tracking.court_geometry import CourtDetector


def trajectory(fps, function=lambda t: 2*t, seconds=5):
    return [(i, function(i/fps), 5.0) for i in range(round(seconds*fps))]


@pytest.mark.parametrize('fps', [15, 30, 60])
def test_constant_speed_survives_all_frame_rates(fps):
    bundle = analyse_metric_motion(trajectory(fps), fps, 70, .95)
    m, f = bundle['metrics'], bundle['forceVelocity']
    assert m['speed']['average'] == pytest.approx(2, abs=.005)
    assert m['totalDistance']['value'] == pytest.approx(2*m['coverage']['validDurationSeconds'], abs=.005)
    assert m['totalDistance']['value'] > 5
    assert m['speed']['peak'] == f['maximumVelocityMps']
    assert max(abs(p['value']) for p in m['acceleration']['samples']) < .01


def test_optional_mass_never_changes_movement_metrics():
    a = analyse_metric_motion(trajectory(30), 30, None, .95)
    b = analyse_metric_motion(trajectory(30), 30, 75, .95)
    assert a['metrics'] == b['metrics']
    assert a['forceVelocity']['status'] == 'unavailable'
    assert b['forceVelocity']['status'] == 'experimental'


@pytest.mark.parametrize('invalid', [float('nan'), float('inf')])
def test_nonfinite_values_fail_closed(invalid):
    samples = trajectory(30)
    samples[10] = (10, invalid, 2)
    assert assess(samples, 30, .95)['status'] == 'rejected'
    assert assess(trajectory(30), invalid, .95)['status'] == 'rejected'
    assert assess(trajectory(30), 30, invalid)['status'] == 'rejected'


def test_duplicate_frames_rejected():
    samples = trajectory(30)
    samples[11] = samples[10]
    assert assess(samples, 30, .95)['status'] == 'rejected'


def test_gap_does_not_add_distance_or_false_braking():
    # Each section is stationary; 1-second gap must not become a 5 m sprint.
    samples = [(i, 0., 0.) for i in range(90)] + [(i, 5., 0.) for i in range(120, 210)]
    b = analyse_metric_motion(samples, 30, 75, .95)
    assert b['metrics']['totalDistance']['value'] == 0
    assert b['metrics']['deceleration']['events'] == []
    assert len({p['segmentId'] for p in b['metrics']['speed']['samples']}) == 2


def test_force_and_acceleration_have_matching_timestamps_and_values():
    b = analyse_metric_motion(trajectory(30, lambda t: t+t*t, 4), 30, 70, .95)
    for a, f in zip(b['metrics']['acceleration']['samples'], b['forceVelocity']['samples']):
        assert a['timeSeconds'] == f['timeSeconds']
        assert a['value'] == f['tangentialAccelerationMps2']
        assert f['estimatedNetForceN'] == pytest.approx(a['value']*70, abs=.05)


def test_braking_event_does_not_bridge_rejected_sample():
    samples = [{'frame': i, 'timeSeconds': i/30, 'speed': 4., 'acceleration': -3.,
                'segmentId': 0 if i < 5 else 1} for i in list(range(5))+list(range(6, 11))]
    assert deceleration_events(samples, 30) == []


def synthetic_court():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:] = (115, 60, 25)
    world = np.float32([[0, 0], [10.97, 0], [10.97, 23.77], [0, 23.77]])
    image = np.float32([[490, 190], [790, 190], [1180, 660], [100, 660]])
    h = cv2.getPerspectiveTransform(world, image)
    lines = [((0, 0), (10.97, 0)), ((0, 23.77), (10.97, 23.77)),
             ((0, 0), (0, 23.77)), ((10.97, 0), (10.97, 23.77)),
             ((1.37, 0), (1.37, 23.77)), ((9.60, 0), (9.60, 23.77)),
             ((1.37, 18.285), (9.60, 18.285)), ((1.37, 5.485), (9.60, 5.485))]
    for a, b in lines:
        p = cv2.perspectiveTransform(np.float32([[a, b]]), h)[0]
        cv2.line(frame, tuple(p[0].astype(int)), tuple(p[1].astype(int)), (255, 255, 255), 3)
    return frame, h


def test_detected_line_intersections_recover_known_court():
    frame, h = synthetic_court()
    calibration = CourtDetector().detect_from_frames([frame]*3)
    assert calibration is not None
    assert calibration.confidence >= .7
    for point in [(2., 20.), (8., 20.), (5., 10.)]:
        pixel = cv2.perspectiveTransform(np.float32([[point]]), h)[0][0]
        measured = calibration.image_to_court(tuple(pixel))
        assert measured == pytest.approx(point, abs=.4)


def test_blank_frame_is_not_calibrated():
    assert CourtDetector().detect_from_frames([np.zeros((720, 1280, 3), np.uint8)]*3) is None


@pytest.mark.parametrize('mass', [None, 70.0])
def test_real_video_loop_uses_shared_series_and_preserves_video_export(tmp_path, monkeypatch, mass):
    """Real OpenCV I/O and tracker; fake detections isolate numerical integration."""
    from types import SimpleNamespace
    from hpt_tracking.court_geometry import CourtCalibration
    from hpt_tracking.tracking_engine import YuchenPrototypeTrackingEngine
    corners = np.float32([[100, 30], [220, 30], [300, 220], [20, 220]])
    world = np.float32([[0, 0], [10.97, 0], [10.97, 23.77], [0, 23.77]])
    h = cv2.getPerspectiveTransform(corners, world)
    inverse = np.linalg.inv(h)
    calibration = CourtCalibration(corners, h, .95)
    monkeypatch.setattr(CourtDetector, 'detect_from_frames', lambda self, frames: calibration)
    video = tmp_path / 'input.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 30, (320, 240))
    assert writer.isOpened()
    for _ in range(90):
        writer.write(np.zeros((240, 320, 3), np.uint8))
    writer.release()

    class BoxCoordinates:
        def __init__(self, values): self.values = values
        def cpu(self): return self
        def tolist(self): return self.values
    class Model:
        frame = 0
        def predict(self, *args, **kwargs):
            t = self.frame / 30
            self.frame += 1
            x, y = cv2.perspectiveTransform(np.float32([[[1+2*t, 20]]]), inverse)[0][0]
            box = SimpleNamespace(conf=np.array([.95]), xyxy=[BoxCoordinates([x-8, y-25, x+8, y])])
            return [SimpleNamespace(boxes=[box])]
    engine = YuchenPrototypeTrackingEngine()
    engine._model = Model()
    result = engine.analyse(video, tmp_path/'out', lambda _: None, lambda: False, 'near', mass)
    player = result['players'][0]
    assert player['speed']['unit'] == 'm/s'
    assert player['speed']['average'] == pytest.approx(2, abs=.02)
    assert player['forceVelocity']['status'] == ('experimental' if mass else 'unavailable')
    assert (tmp_path/'out'/result['annotatedVideoFilename']).stat().st_size > 0
    assert result['athleteMassKg'] == mass
