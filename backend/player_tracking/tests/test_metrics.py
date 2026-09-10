import pytest

from hpt_tracking.metrics import analyse_trajectory


def test_straight_trajectory_uses_pixel_units():
    result = analyse_trajectory(
        [(0, 0.0, 0.0), (10, 3.0, 4.0), (20, 6.0, 8.0)],
        fps=10.0,
    )

    assert result["totalDistance"] == {
        "status": "experimental",
        "value": 10.0,
        "unit": "px",
        "note": "Pixel-space prototype result; not calibrated to real-world units.",
    }
    assert result["speed"]["average"] == pytest.approx(5.0)
    assert result["speed"]["unit"] == "px/s"
    assert result["directionChanges"]["count"] == 0


def test_direction_change_is_reported_as_experimental():
    result = analyse_trajectory(
        [(0, 0.0, 0.0), (1, 5.0, 0.0), (2, 5.0, 5.0)],
        fps=1.0,
        direction_change_degrees=45.0,
    )

    assert result["directionChanges"]["status"] == "experimental"
    assert result["directionChanges"]["count"] == 1
    assert result["directionChanges"]["events"][0]["angleDegrees"] == 90.0


def test_short_trajectory_returns_unavailable_metrics():
    result = analyse_trajectory([(0, 1.0, 2.0)], fps=30.0)

    assert result["totalDistance"]["status"] == "unavailable"
    assert result["speed"]["average"] is None
    assert result["movementPath"]["points"] == []


def test_estimated_court_trajectory_uses_metres():
    result = analyse_trajectory(
        [(0, 0.0, 0.0), (10, 3.0, 4.0)],
        fps=10.0,
        minimum_step=0.08,
        coordinate_system="estimated_court_metres",
        distance_unit="m",
        measurement_note="Automatic experimental mapping.",
    )

    assert result["movementPath"]["coordinateSystem"] == (
        "estimated_court_metres"
    )
    assert result["totalDistance"]["value"] == pytest.approx(5.0)
    assert result["totalDistance"]["unit"] == "m"
    assert result["speed"]["unit"] == "m/s"
