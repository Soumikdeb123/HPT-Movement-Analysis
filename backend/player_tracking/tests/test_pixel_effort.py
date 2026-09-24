import pytest
from hpt_tracking.pixel_effort import pixel_effort


def trajectory(speed=100, seconds=1, fps=10):
    return [(i, speed*i/fps, 0) for i in range(int(seconds*fps)+1)]


def test_constant_speed_hand_calculation():
    r = pixel_effort(trajectory(), 10)
    assert r['value'] == pytest.approx(1)
    assert r['accelerationContributionAU'] == 0
    assert r['unit'] == 'AU'


def test_stationary():
    assert pixel_effort(trajectory(0),10)['value'] == 0


def test_duration_and_speed_scaling():
    assert pixel_effort(trajectory(seconds=2),10)['value'] == pytest.approx(2)
    assert pixel_effort(trajectory(speed=200),10)['value'] == pytest.approx(4)


def test_frame_rate_constant_speed():
    assert pixel_effort(trajectory(fps=30),30)['value'] == pytest.approx(1)


@pytest.mark.parametrize('points,fps', [([],30), ([(0,0,0)],30), (trajectory(),0),
    ([(0,0,0),(0,1,0),(1,2,0)],10), ([(0,0,0),(1,float('nan'),0),(2,2,0)],10)])
def test_invalid_is_not_zero(points,fps):
    r=pixel_effort(points,fps)
    assert r['status']=='unavailable' and r['value'] is None


def test_gap_not_counted_as_sprint():
    points=trajectory()+[(i+30,x+10000,y) for i,x,y in trajectory()]
    r=pixel_effort(points,10)
    assert r['value']==pytest.approx(2)
    assert r['excludedSeconds']==2


def test_acceleration_contributes_and_is_exported():
    points=[(i, 5*i*i, 0) for i in range(11)]
    r=pixel_effort(points,10)
    assert r['accelerationContributionAU'] > 0
    assert r['value'] == pytest.approx(r['speedContributionAU']+r['accelerationContributionAU'],abs=.001)
    assert r['samples'][-1]['cumulativeAU'] == pytest.approx(r['value'],abs=.001)
