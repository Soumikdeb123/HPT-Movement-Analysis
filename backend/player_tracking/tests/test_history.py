import io
import json
import time

from fastapi.testclient import TestClient
from hpt_tracking.api import create_app
from hpt_tracking.config import Settings
from hpt_tracking.history import HistoryStore
from test_api import FakeTrackingEngine, FakeVideoProbe


def test_history_survives_restart_and_enforces_owner_for_files_and_delete(tmp_path, monkeypatch):
    def authenticate(request, timeout):
        name = request.get_header('Authorization').split()[1]
        return io.BytesIO(json.dumps({'id': 1 if name == 'alice' else 2,
                                     'email': name + '@example.com'}).encode())
    monkeypatch.setattr('hpt_tracking.api.urlopen', authenticate)
    settings = Settings(runtime_dir=tmp_path, auth_url='http://auth.test')
    def app():
        return create_app(settings, FakeTrackingEngine(), FakeVideoProbe())
    alice = {'Authorization': 'Bearer alice'}
    bob = {'Authorization': 'Bearer bob'}
    with TestClient(app()) as client:
        assert client.get('/api/analyses').status_code == 401
        ids = []
        for name in ('first.mp4', 'second.mp4'):
            response = client.post('/api/analyses', headers=alice,
                data={'athlete_mass_kg': '75'}, files={'video': (name, b'test-video', 'video/mp4')})
            assert response.status_code == 202
            job = response.json()['analysisId']
            ids.append(job)
            for _ in range(200):
                if client.get('/api/analyses/' + job, headers=alice).json()['status'] == 'completed':
                    break
                time.sleep(.01)
            assert client.get('/api/analyses/' + job, headers=alice).json()['status'] == 'completed'
        page = client.get('/api/analyses?limit=1', headers=alice).json()
        assert page['total'] == 2 and page['hasMore']
        assert page['items'][0]['analysisId'] == ids[1]
        assert client.get('/api/analyses?limit=1&offset=1', headers=alice).json()['items'][0]['analysisId'] == ids[0]
    with TestClient(app()) as client:
        assert client.get('/api/analyses', headers=bob).json()['items'] == []
        assert client.get('/api/analyses', headers=alice).json()['total'] == 2
        for suffix in ('', '/video', '/reports/reports.zip'):
            url = '/api/analyses/' + ids[0] + suffix
            assert client.get(url, headers=alice).status_code == 200
            assert client.get(url, headers=bob).status_code == 404
        assert client.get(
            '/api/analyses/' + ids[0] + '/reports/analysis.json',
            headers=alice,
        ).status_code == 404
        assert client.delete('/api/analyses/' + ids[0], headers=bob).status_code == 404
        assert client.delete('/api/analyses/' + ids[0], headers=alice).status_code == 204
        assert not (tmp_path / ids[0]).exists()
    with TestClient(app()) as client:
        assert client.get('/api/analyses', headers=alice).json()['total'] == 1
        assert client.get('/api/analyses/' + ids[0], headers=alice).status_code == 404


def test_restart_marks_unfinished_jobs_failed_without_removing_files(tmp_path):
    store = HistoryStore(tmp_path)
    record = dict(analysisId='a'*32, owner='user:1', createdAt='2026-11-18T00:00:00Z',
                  status='processing', progress=.2, originalFilename='test.mp4',
                  targetPlayer='near', inputVideo={})
    store.save(record)
    retained = tmp_path / ('a'*32)
    retained.mkdir()
    (retained / 'input.mp4').write_bytes(b'keep')
    restarted = HistoryStore(tmp_path)
    assert restarted.get('a'*32)['status'] == 'failed'
    assert 'restart' in restarted.get('a'*32)['error']
    assert (retained / 'input.mp4').read_bytes() == b'keep'


def test_players_are_owner_scoped_and_filter_their_analysis_history(tmp_path, monkeypatch):
    def authenticate(request, timeout):
        name = request.get_header('Authorization').split()[1]
        return io.BytesIO(json.dumps({
            'id': 1 if name == 'alice' else 2,
            'email': name + '@example.com',
        }).encode())

    monkeypatch.setattr('hpt_tracking.api.urlopen', authenticate)
    app = create_app(
        Settings(runtime_dir=tmp_path, auth_url='http://auth.test'),
        FakeTrackingEngine(), FakeVideoProbe(),
    )
    alice = {'Authorization': 'Bearer alice'}
    bob = {'Authorization': 'Bearer bob'}
    with TestClient(app) as client:
        created = client.post('/api/players', headers=alice, json={
            'displayName': 'Jordan Lee', 'defaultMassKg': 75,
        })
        assert created.status_code == 201
        player = created.json()
        assert player['displayName'] == 'Jordan Lee'
        assert client.get('/api/players', headers=bob).json()['items'] == []

        denied = client.post('/api/analyses', headers=bob,
            data={'player_id': player['playerId'], 'athlete_mass_kg': '75'},
            files={'video': ('match.mp4', b'test-video', 'video/mp4')})
        assert denied.status_code == 422

        accepted = client.post('/api/analyses', headers=alice,
            data={'player_id': player['playerId'], 'athlete_mass_kg': '75'},
            files={'video': ('match.mp4', b'test-video', 'video/mp4')})
        assert accepted.status_code == 202
        analysis_id = accepted.json()['analysisId']
        for _ in range(200):
            snapshot = client.get('/api/analyses/' + analysis_id, headers=alice).json()
            if snapshot['status'] == 'completed':
                break
            time.sleep(.01)
        assert snapshot['playerId'] == player['playerId']
        assert snapshot['playerName'] == 'Jordan Lee'
        filtered = client.get(
            '/api/analyses?player_id=' + player['playerId'], headers=alice,
        ).json()
        assert filtered['total'] == 1
        assert filtered['items'][0]['playerName'] == 'Jordan Lee'

        assert client.delete(
            '/api/players/' + player['playerId'], headers=alice,
        ).status_code == 204
        assert client.get('/api/players', headers=alice).json()['items'] == []
        # Archiving a player never deletes their evidence or history.
        assert client.get(
            '/api/analyses?player_id=' + player['playerId'], headers=alice,
        ).json()['total'] == 1


def test_force_velocity_baseline_uses_mean_of_recent_same_player_records(tmp_path):
    store = HistoryStore(tmp_path)
    player = store.create_player('owner', 'Jordan Lee')

    def record(identifier, created_at, value):
        return {
            'analysisId': identifier * 32,
            'owner': 'owner',
            'playerId': player['playerId'],
            'playerName': player['displayName'],
            'createdAt': created_at,
            'status': 'completed',
            'progress': 1,
            'originalFilename': identifier + '.mp4',
            'targetPlayer': 'near',
            'result': {
                'selectedTrackId': '1',
                'players': [{
                    'trackId': '1',
                        'forceVelocity': {
                            'algorithmVersion': '5.0.0',
                            'quality': {'status': 'good'},
                            'events': [{'eventId': identifier, 'startTimeSeconds': 1,
                                        'startSpeedMps': .5, 'peakSpeedMps': 2,
                                        'meanForceNPerKg': value}],
                            'fit': {'interceptNPerKg': value, 'slopeNPerKgPerMps': -.2,
                                    'minVelocityMps': .5, 'maxVelocityMps': 2.0},
                            'currentCurve': [
                                {'velocityMps': .5, 'forceNPerKg': value-.1},
                                {'velocityMps': 2.0, 'forceNPerKg': value-.4},
                            ],
                        },
                }],
            },
        }

    for identifier, day, value in (('a', '01', .9),):
        store.save(record(identifier, f'2026-11-{day}T00:00:00+00:00', value))

    current = record('d', '2026-11-04T00:00:00+00:00', 1.3)
    store.attach_force_velocity_baseline(current)
    profile = current['result']['players'][0]['forceVelocity']
    assert profile['baselineAnalysisCount'] == 1
    assert profile['baselineCurve'] == []
    assert profile['comparisonStatus'] == 'no_baseline'
    assert profile['comparisonSummary'] == (
        'Personal baseline is being built (3 analyses required)'
    )

    for identifier, day, value in (('b', '02', 1.1), ('c', '03', 1.3)):
        store.save(record(identifier, f'2026-11-{day}T00:00:00+00:00', value))

    current = record('d', '2026-11-04T00:00:00+00:00', 1.5)
    current_profile = current['result']['players'][0]['forceVelocity']
    current_profile['samples'] = [
        {
            'frame': index, 'segmentId': 0, 'timeSeconds': index/30,
            'velocityMps': .5+index*.06,
            'tangentialAccelerationMps2': 1.7-index*.02,
        }
        for index in range(24)
    ]
    store.attach_force_velocity_baseline(current)
    profile = current['result']['players'][0]['forceVelocity']
    assert profile['baselineAnalysisCount'] == 3
    assert len(profile['baselineCurve']) == len(profile['currentCurve'])
    assert profile['baselineCurve'][0]['velocityMps'] == profile['currentCurve'][0]['velocityMps']
    assert profile['baselineCurve'][-1]['velocityMps'] == profile['currentCurve'][-1]['velocityMps']
    assert profile['baselineCurve'][0]['forceNPerKg'] == 1.0
    assert profile['comparisonStatus'] == 'above'
    assert profile['comparisonChangePercent'] > 5
    assert profile['comparisonSummary'] == 'Above usual overall'
    assert profile['comparisonOverallChangePercent'] > 5
    assert profile['comparisonLargestDifferencePercent'] > 5
    assert profile['comparisonDetail'].startswith('Largest difference at ')
    assert profile['comparisonDetail'].endswith('% above personal baseline.')
    labels = ' · '.join(event['label'] for event in profile['events'])
    assert 'Above usual' in labels
    assert 'Largest baseline difference' not in labels
    assert 'Close to usual' not in labels
    assert len({int(event['startTimeSeconds']) for event in profile['events']}) == len(
        profile['events']
    )

    close = record('e', '2026-11-05T00:00:00+00:00', 1.1)
    close_profile = close['result']['players'][0]['forceVelocity']
    close_profile['samples'] = current_profile['samples']
    store.attach_force_velocity_baseline(close)
    close_profile = close['result']['players'][0]['forceVelocity']
    assert close_profile['comparisonStatus'] == 'close'
    assert close_profile['comparisonSummary'] == (
        'Close to usual overall (difference under 5%)'
    )
    assert close_profile['comparisonDetail'] is None
    close_labels = ' · '.join(event['label'] for event in close_profile['events'])
    assert 'Above usual' not in close_labels
    assert 'Below usual' not in close_labels
    assert 'Close to usual' not in close_labels

    local = record('f', '2026-11-06T00:00:00+00:00', 1.1)
    local_profile = local['result']['players'][0]['forceVelocity']
    velocities = [.5+1.5*index/23 for index in range(24)]
    local_profile['currentCurve'] = [
        {
            'velocityMps': velocity,
                'forceNPerKg': (1.0-.2*(velocity-.5))*(.70 if index >= 12 else 1.0),
        }
        for index, velocity in enumerate(velocities)
    ]
    local_profile['samples'] = current_profile['samples']
    store.attach_force_velocity_baseline(local)
    local_profile = local['result']['players'][0]['forceVelocity']
    assert local_profile['comparisonStatus'] == 'below'
    assert local_profile['comparisonSummary'] == 'Below usual overall'
    assert local_profile['comparisonDetail'].startswith('Largest difference at ')
    assert local_profile['comparisonDetail'].endswith('% below personal baseline.')


def test_history_refresh_uses_only_analyses_that_precede_each_record(tmp_path):
    store = HistoryStore(tmp_path)
    player = store.create_player('owner', 'Chronological Player')

    def record(identifier, day, force):
        return {
            'analysisId': identifier * 32,
            'owner': 'owner', 'playerId': player['playerId'],
            'playerName': player['displayName'],
            'createdAt': f'2026-11-{day}T00:00:00+00:00',
            'status': 'completed', 'progress': 1,
            'originalFilename': identifier + '.mp4', 'targetPlayer': 'near',
            'result': {'selectedTrackId': '1', 'players': [{
                'trackId': '1', 'forceVelocity': {
                    'algorithmVersion': '5.0.0',
                    'fit': {'model': 'test'}, 'events': [], 'samples': [],
                    'currentCurve': [
                        {'velocityMps': .5, 'forceNPerKg': force},
                        {'velocityMps': 1.5, 'forceNPerKg': force-.2},
                    ],
                },
            }]},
        }

    records = [
        record('a', '01', 1.0), record('b', '02', 1.1),
        record('c', '03', 1.2), record('d', '04', 1.3),
    ]
    for item in records:
        store.save(item)

    assert store.refresh_force_velocity_comparisons() == 4
    first = store.get('a'*32)['result']['players'][0]['forceVelocity']
    fourth = store.get('d'*32)['result']['players'][0]['forceVelocity']
    assert first['baselineAnalysisCount'] == 0
    assert first['baselineCurve'] == []
    assert fourth['baselineAnalysisCount'] == 3
    assert len(fourth['baselineCurve']) == len(fourth['currentCurve'])
    assert fourth['baselineCurve'][0]['velocityMps'] == fourth['currentCurve'][0]['velocityMps']
    assert fourth['baselineCurve'][-1]['velocityMps'] == fourth['currentCurve'][-1]['velocityMps']


def test_history_refresh_regenerates_reports_in_served_results_folder(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path)
    player = store.create_player('owner', 'Report Player')
    analysis_id = 'e' * 32
    results_dir = tmp_path / analysis_id / 'results'
    results_dir.mkdir(parents=True)
    record = {
        'analysisId': analysis_id,
        'owner': 'owner', 'playerId': player['playerId'],
        'playerName': player['displayName'],
        'createdAt': '2026-11-01T00:00:00+00:00',
        'status': 'completed', 'progress': 1,
        'originalFilename': 'report.mp4', 'targetPlayer': 'near',
        'result': {'selectedTrackId': '1', 'players': [{
            'trackId': '1', 'forceVelocity': {
                'algorithmVersion': '5.0.0',
                'fit': {'model': 'test'}, 'events': [], 'samples': [],
                'currentCurve': [
                    {'velocityMps': .5, 'forceNPerKg': 1.2},
                    {'velocityMps': 1.5, 'forceNPerKg': 1.0},
                ],
            },
        }]},
    }
    store.save(record)
    generated_in = []
    monkeypatch.setattr(
        'hpt_tracking.reports.save_reports',
        lambda _result, output_dir: generated_in.append(output_dir),
    )

    assert store.refresh_force_velocity_comparisons(regenerate_reports=True) == 1
    assert generated_in == [results_dir]


def _baseline_sample(frame, segment_id, acceleration):
    return {
        'frame': frame,
        'segmentId': segment_id,
        'timeSeconds': frame/30,
        'velocityMps': 1.0,
        'tangentialAccelerationMps2': acceleration,
    }


def test_above_baseline_moment_never_selects_opposite_direction_evidence():
    # The below-baseline run has the larger absolute deviation. An "above"
    # session must still select the smaller, directionally correct run.
    profile = {'samples': [
        *[_baseline_sample(frame, 1, .2) for frame in range(7)],
        *[_baseline_sample(100+frame, 2, 1.4) for frame in range(7)],
    ]}
    baseline = [
        {'velocityMps': .5, 'forceNPerKg': 1.0},
        {'velocityMps': 1.5, 'forceNPerKg': 1.0},
    ]

    events = HistoryStore._attach_baseline_moment(
        profile, [], .5, 1.5, lambda curve, velocity: 1.0,
        baseline, 'above',
    )

    assert len(events) == 1
    assert events[0]['label'] == 'Above usual'
    assert events[0]['startFrame'] >= 100


def test_close_to_usual_is_secondary_and_never_creates_its_own_clip():
    profile = {'samples': [
        _baseline_sample(frame, 1, 1.02) for frame in range(21)
    ]}
    baseline = [
        {'velocityMps': .5, 'forceNPerKg': 1.0},
        {'velocityMps': 1.5, 'forceNPerKg': 1.0},
    ]
    core = [{
        'eventId': 'movement-0-20',
        'label': 'Strongest propulsion',
        'startTimeSeconds': 0.0,
        'endTimeSeconds': 20/30,
    }]

    attached = HistoryStore._attach_baseline_moment(
        profile, core, .5, 1.5, lambda curve, velocity: 1.0,
        baseline, 'close',
    )
    standalone = HistoryStore._attach_baseline_moment(
        profile, [], .5, 1.5, lambda curve, velocity: 1.0,
        baseline, 'close',
    )

    assert attached[0]['label'] == 'Strongest propulsion · Close to usual'
    assert standalone == []


def test_coach_can_exclude_and_restore_a_key_movement(tmp_path):
    store = HistoryStore(tmp_path)
    player = store.create_player('owner', 'Alex')
    event = {
        'eventId': 'movement-1-20', 'excluded': False,
        'startTimeSeconds': 0, 'endTimeSeconds': .3,
        'startSpeedMps': .3, 'peakSpeedMps': 2.1,
        'meanForceNPerKg': 1.4,
    }
    record = {
        'analysisId': 'e'*32, 'owner': 'owner', 'playerId': player['playerId'],
        'playerName': 'Alex', 'createdAt': '2026-11-04T00:00:00+00:00',
        'status': 'completed', 'progress': 1, 'originalFilename': 'test.mp4',
        'targetPlayer': 'near', 'result': {
            'selectedTrackId': '1', 'players': [{'trackId': '1', 'forceVelocity': {
                'algorithmVersion': '5.0.0',
                'quality': {'status': 'available', 'trackingCoverage': .05,
                            'calibrationConfidence': .95},
                'events': [event], 'fit': {'model': 'robust_session_hill'},
                'samples': [
                    {'timeSeconds': index/30, 'velocityMps': .3+index*.2,
                     'tangentialAccelerationMps2': 2.6/(1+((.3+index*.2)/1.2)**1.4)}
                    for index in range(10)
                ],
                'currentCurve': [{'velocityMps': .3, 'forceNPerKg': 2.2},
                                 {'velocityMps': 2.1, 'forceNPerKg': 1.1}],
            }}],
        },
    }
    store.save(record)

    excluded = store.set_movement_moment_excluded(
        'owner', 'e'*32, 'movement-1-20', True,
    )
    profile = excluded['result']['players'][0]['forceVelocity']
    assert profile['events'][0]['excluded'] is True
    assert profile['currentCurve'] == []
    restored = store.set_movement_moment_excluded(
        'owner', 'e'*32, 'movement-1-20', False,
    )
    profile = restored['result']['players'][0]['forceVelocity']
    assert profile['events'][0]['excluded'] is False
    assert len(profile['currentCurve']) == 40
