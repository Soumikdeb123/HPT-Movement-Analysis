import pytest
from hpt_tracking.metric_effort import metric_effort
from hpt_tracking.yuchen_motion_adapter import analyse_metric_motion


def run(v, a, hz=20):
    return [dict(frame=i, segmentId=1, timeSeconds=i/hz, speed=v, acceleration=a)
            for i in range(hz+1)]


@pytest.mark.parametrize('hz', [20, 30, 60])
def test_one_second_reference_speed(hz):
    r = metric_effort(run(2, 0, hz))
    assert r['value'] == pytest.approx(1)
    assert r['validSeconds'] == pytest.approx(1)


def test_signs_rest_and_gaps():
    assert metric_effort(run(0, 0))['value'] == 0
    for sign, key in [(1, 'accelerationAU'), (-1, 'brakingAU')]:
        assert metric_effort(run(2, sign*2))[key] == pytest.approx(.5)
    p, q = run(2, 0)[:2]
    for change in [dict(segmentId=2), dict(frame=50), dict(speed=float('nan'))]:
        assert metric_effort([p, dict(q, **change)])['value'] is None


def test_adapter_on_calibrated_track_without_mass():
    samples = [(i, 2*i/30, 5.) for i in range(180)]
    r = analyse_metric_motion(samples, 30, None, .9)['metrics']['overallEffort']
    assert r['method'] == 'metric_motion_load_v1'
    assert r['value'] == pytest.approx(r['validSeconds'], rel=.02)
    assert analyse_metric_motion(samples, 30, None, .4)['metrics'] is None
