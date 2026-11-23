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
        for suffix in ('', '/video', '/reports/analysis.json', '/reports/reports.zip'):
            url = '/api/analyses/' + ids[0] + suffix
            assert client.get(url, headers=alice).status_code == 200
            assert client.get(url, headers=bob).status_code == 404
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


def test_force_velocity_baseline_uses_three_recent_good_same_player_records(tmp_path):
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
                            'algorithmVersion': '3.0.0',
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

    for identifier, day, value in (
        ('a', '01', .9), ('b', '02', 1.0), ('c', '03', 1.1),
    ):
        store.save(record(identifier, f'2026-11-{day}T00:00:00+00:00', value))

    current = record('d', '2026-11-04T00:00:00+00:00', 1.3)
    store.attach_force_velocity_baseline(current)
    profile = current['result']['players'][0]['forceVelocity']
    assert profile['baselineAnalysisCount'] == 3
    assert len(profile['baselineCurve']) == 24
    assert profile['comparisonStatus'] == 'above'
    assert profile['comparisonChangePercent'] > 5
    assert 'personal baseline' in profile['comparisonSummary']
