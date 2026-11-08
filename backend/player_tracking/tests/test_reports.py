import json
from zipfile import ZipFile

import pytest

from hpt_tracking.metric_motion import analyse_metric_motion
from hpt_tracking.reports import save_reports, runs, REPORT_FILES


def test_metric_reports_match_integrated_distance(tmp_path):
    motion = analyse_metric_motion([(f, f/30, 10) for f in range(150)], 30, 75, .9)
    metrics = motion['metrics']
    assert metrics is not None
    assert metrics['totalDistance']['samples'][-1]['value'] == pytest.approx(metrics['totalDistance']['value'])
    result = {'players': [{'trackId': '0', **metrics, 'forceVelocity': motion['forceVelocity']}]}
    save_reports(result, tmp_path)
    assert result['reportStatus'] == 'metric'
    for filename in REPORT_FILES:
        assert (tmp_path / filename).stat().st_size > 0
    with ZipFile(tmp_path / 'reports.zip') as archive:
        assert set(archive.namelist()) == REPORT_FILES - {'reports.zip'}
    assert json.loads((tmp_path / 'analysis.json').read_text(encoding='utf-8'))['reportStatus'] == 'metric'


def test_pixels_produce_unavailable_reports_not_metric_curves(tmp_path):
    result = {'players': [{'speed': {'unit': 'px/s'}, 'movementPath': {'points': [{'x': 300, 'y': 200}]}}]}
    save_reports(result, tmp_path)
    assert result['reportStatus'] == 'unavailable'
    assert result['players'][0]['speed']['unit'] == 'px/s'


def test_report_lines_do_not_bridge_segments():
    assert [len(run) for run in runs([{'segmentId': 1}, {'segmentId': 1}, {'segmentId': 3}])] == [2, 1]
