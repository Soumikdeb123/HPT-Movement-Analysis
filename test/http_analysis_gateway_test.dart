import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/auth/repositories/auth_repository.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/http_analysis_gateway.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  tearDown(() => AuthRepository.token = null);
  test('cancel and delete use the authenticated session', () async {
    AuthRepository.token = 'test-session';
    final methods = <String>[];
    final client = MockClient((request) async {
      expect(request.headers['authorization'], 'Bearer test-session');
      methods.add(request.method);
      return http.Response('{}', 200);
    });
    final gateway = HttpAnalysisGateway(
      baseUri: Uri.parse('http://example.test'),
      client: client,
    );
    final token = AnalysisCancellationToken()..attachAnalysisId('job-1');
    await gateway.cancelAnalysis(token);
    await gateway.deleteAnalysis('job-1');
    expect(methods, ['POST', 'DELETE']);
    client.close();
  });
  test('gateway uploads a video and parses a completed result', () async {
    AuthRepository.token = 'test-session';
    final temporaryDirectory = await Directory.systemTemp.createTemp(
      'hpt-gateway-test-',
    );
    final video = File('${temporaryDirectory.path}/clip.mp4');
    await video.writeAsBytes(const [0, 1, 2, 3]);

    final client = MockClient((request) async {
      expect(request.headers['authorization'], 'Bearer test-session');
      expect(request.method, 'POST');
      expect(request.url.path, '/api/analyses');
      expect(
        request.headers['content-type'],
        startsWith('multipart/form-data'),
      );
      return http.Response(
        jsonEncode({
          'analysisId': 'job-123',
          'status': 'completed',
          'progress': 1,
          'result': {
            'calibrationStatus': 'uncalibrated',
            'selectedTrackId': '0',
            'players': [
              {
                'trackId': '0',
                'movementPath': {
                  'status': 'experimental',
                  'coordinateSystem': 'image_pixels',
                  'points': [],
                },
                'totalDistance': {
                  'status': 'experimental',
                  'value': 42,
                  'unit': 'px',
                },
                'speed': {'status': 'unavailable'},
                'acceleration': {'status': 'unavailable'},
                'deceleration': {'status': 'unavailable'},
                'directionChanges': {'status': 'unavailable'},
              },
            ],
            'annotatedVideoUrl': '/api/analyses/job-123/video',
            'warnings': [],
          },
        }),
        202,
        headers: {'content-type': 'application/json'},
      );
    });
    final gateway = HttpAnalysisGateway(
      baseUri: Uri.parse('http://example.test:8000/'),
      client: client,
      pollInterval: Duration.zero,
    );

    try {
      final result = await gateway.analyseVideo(
        AnalysisRequest(
          videoPath: video.path,
          videoName: 'clip.mp4',
          targetPlayer: TargetPlayerPosition.nearCourt,
        ),
        onProgress: (_) {},
        cancellationToken: AnalysisCancellationToken(),
      );

      expect(result.analysisId, 'job-123');
      expect(result.playerById('0')?.totalDistance.value, 42);
      expect(
        result.annotatedVideoUrl,
        'http://example.test:8000/api/analyses/job-123/video',
      );
    } finally {
      client.close();
      await temporaryDirectory.delete(recursive: true);
    }
  });
}
