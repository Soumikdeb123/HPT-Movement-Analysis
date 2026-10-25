from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from hpt_tracking.video_overlay import frame_values, label_lines, render_video


def test_values_align_to_frames_and_split_signed_acceleration():
    player = {'speed': {'unit': 'm/s', 'samples': [{'timeSeconds': .5, 'value': 2}]},
              'acceleration': {'samples': [{'timeSeconds': .5, 'value': -3}]},
              'totalDistance': {'unit': 'm', 'samples': [{'timeSeconds': .5, 'value': 4}]}}
    values = frame_values(player, 30)
    lines = label_lines(1, values, 15)
    assert 'Distance: 4.00 m' in lines[0]
    assert 'Accel: 0.00 m/s^2 | Decel: 3.00 m/s^2' in lines[2]
    assert 'N/A' in label_lines(1, values, 16)[2]
    player['speed']['unit'] = 'px/s'
    assert frame_values(player, 30)['acceleration'] == {}


def test_video_has_per_frame_annotation_but_no_ghost_box(tmp_path):
    source, output = tmp_path / 'input.mp4', tmp_path / 'output.mp4'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 30, (400, 240))
    assert writer.isOpened()
    for _ in range(3):
        writer.write(np.zeros((240,400,3), dtype=np.uint8))
    writer.release()
    track = SimpleNamespace(track_id=0, colour=(0,255,0), bbox_history={0:(100,100,150,200)})
    player = {'trackId':'0', 'speed':{'unit':'m/s'}, 'totalDistance':{'unit':'m'}}
    render_video(source, output, [track], [player], None, 30, 400, 240, 3,
                 lambda:False, lambda _:None, RuntimeError)
    cap = cv2.VideoCapture(str(output))
    ok, present = cap.read()
    ok2, absent = cap.read()
    assert ok and ok2
    assert present.sum() > absent.sum()+10000
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == 3
    cap.release()


def test_render_respects_cancellation(tmp_path):
    source = tmp_path / 'input.mp4'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 30, (80,80))
    writer.write(np.zeros((80,80,3), dtype=np.uint8))
    writer.release()
    with pytest.raises(RuntimeError, match='cancelled'):
        render_video(source, tmp_path/'output.mp4', [], [], None, 30,80,80,1,
                     lambda:True, lambda _:None, RuntimeError)
