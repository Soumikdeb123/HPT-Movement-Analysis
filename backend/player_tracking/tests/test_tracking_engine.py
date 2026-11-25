import numpy as np
import pytest

from hpt_tracking.court_geometry import CourtCalibration
from hpt_tracking.tracking_engine import (
    Detection,
    Track,
    YuchenPrototypeTrackingEngine,
    select_primary_tracks,
)


def _track(track_id, frames):
    track = Track(track_id=track_id, colour=(0, 0, 0))
    track.image_trajectory = [(frame, float(frame), 0.0) for frame in frames]
    return track


def test_only_two_most_persistent_tracks_are_reported():
    tracks = [
        _track(1, range(40)),
        _track(2, range(80)),
        _track(3, range(60)),
        _track(4, range(4)),
    ]

    selected = select_primary_tracks(tracks, minimum_frames=5, maximum_players=2)

    assert [track.track_id for track in selected] == [2, 3]


def test_court_homography_maps_corners_to_standard_dimensions():
    corners = np.asarray(
        [[100, 100], [200, 100], [300, 400], [0, 400]], dtype=np.float32
    )
    target = np.asarray(
        [[0, 0], [10.97, 0], [10.97, 23.77], [0, 23.77]], dtype=np.float32
    )
    import cv2

    calibration = CourtCalibration(
        corners=corners,
        homography=cv2.getPerspectiveTransform(corners, target),
        confidence=0.9,
    )

    x, y = calibration.image_to_court((300, 400))
    assert x == pytest.approx(10.97, abs=0.01)
    assert y == pytest.approx(23.77, abs=0.01)


def test_fixed_camera_fallback_keeps_only_selected_court_side():
    far_player = Detection((100, 200, 150, 300), 0.9)
    near_player = Detection((300, 250, 380, 500), 0.9)

    near = YuchenPrototypeTrackingEngine._select_target_detection(
        [far_player, near_player], "near", None, frame_height=576
    )
    far = YuchenPrototypeTrackingEngine._select_target_detection(
        [far_player, near_player], "far", None, frame_height=576
    )

    assert near == [near_player]
    assert far == [far_player]
