import numpy as np
import pytest
from hpt_tracking.yuchen_motion_adapter import analyse_metric_motion
from hpt_tracking.tracking_engine import Detection, YuchenCentroidTrackManager, YuchenPrototypeTrackingEngine
from hpt_tracking.court_geometry import CourtCalibration


def test_distance_uses_nine_detection_moving_average_not_velocity_integral():
    samples = [(f, f/30, 5.) for f in range(150)]
    result = analyse_metric_motion(samples, 30, 75, .9)
    expected = np.mean([f/30 for f in range(141, 150)])
    assert result['metrics']['totalDistance']['value'] == pytest.approx(expected)
    assert result['metrics']['totalDistance']['samples'][-1]['value'] == pytest.approx(expected)
    fs = result['forceVelocity']['samples']
    assert len(fs) > 0
    for p in fs:
        assert p['estimatedNetForceN'] == pytest.approx(75*p['tangentialAccelerationMps2'])


def test_filter_trims_one_half_window_as_upstream():
    result = analyse_metric_motion([(f, f/30, 5.) for f in range(150)], 30, None, .9)
    samples = result['metrics']['speed']['samples']
    assert samples[0]['timeSeconds'] == pytest.approx(10/30, abs=1e-4)
    assert len(samples) == 130
    assert result['forceVelocity']['status'] == 'unavailable'


def test_does_not_switch_to_opposite_half_when_target_missing():
    calibration = CourtCalibration(np.zeros((4, 2)), np.eye(3), 1.)
    far = Detection((0, 0, 2, 2), .9, (3, 3))
    near = Detection((0, 15, 2, 18), .9, (3, 18))
    select = YuchenPrototypeTrackingEngine._select_target_detection
    assert select([far], 'near', calibration, 720) == []
    assert select([near], 'far', calibration, 720) == []


def test_short_gap_retains_id_long_gap_creates_separate_track():
    tracker = YuchenCentroidTrackManager(3., 30)
    d = Detection((0, 0, 2, 2), .9, (3, 18))
    tracker.update(0, [d])
    tracker.update(3, [d])
    assert len(tracker.tracks) == 1
    tracker.update(40, [d])
    assert len(tracker.tracks) == 2
    assert len(tracker.tracks[0].image_trajectory) == 2
