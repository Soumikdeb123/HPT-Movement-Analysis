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
