import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import 'analysis_gateway.dart';

const _mockInputVideoJson = <String, dynamic>{
  'originalFilename': 'mock-video.mp4',
  'extension': '.mp4',
  'sizeBytes': 1048576,
  'codecTag': 'avc1',
  'codecName': 'H.264 (AVC)',
  'widthPixels': 1920,
  'heightPixels': 1080,
  'framesPerSecond': 30.0,
  'frameCount': 300,
  'durationSeconds': 10.0,
  'decodedSampleFrames': 3,
  'requestedSampleFrames': 3,
  'compatibilityStatus': 'compatible',
  'warnings': <String>[],
};

class MockAnalysisGateway implements AnalysisGateway {
  const MockAnalysisGateway();

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required VideoValidatedCallback onVideoValidated,
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  }) async {
    onVideoValidated(InputVideoMetadata.fromJson(_mockInputVideoJson));
    for (var step = 1; step <= 5; step += 1) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      if (cancellationToken.isCancellationRequested) {
        throw const AnalysisCancelledException();
      }
      onProgress(step / 5);
    }

    return AnalysisResult.fromJson(
      const {
        'calibrationStatus': 'uncalibrated',
        'selectedTrackId': '0',
        'players': [
          {
            'trackId': '0',
            'movementPath': {
              'status': 'experimental',
              'coordinateSystem': 'image_pixels',
              'points': [
                {'timeSeconds': 0.0, 'x': 20.0, 'y': 80.0},
                {'timeSeconds': 0.5, 'x': 42.0, 'y': 58.0},
                {'timeSeconds': 1.0, 'x': 70.0, 'y': 72.0},
              ],
            },
            'totalDistance': {
              'status': 'experimental',
              'value': 50.0,
              'unit': 'px',
            },
            'speed': {
              'status': 'experimental',
              'average': 50.0,
              'peak': 62.0,
              'unit': 'px/s',
            },
            'acceleration': {
              'status': 'unavailable',
              'value': null,
              'unit': null,
            },
            'deceleration': {
              'status': 'unavailable',
              'value': null,
              'unit': null,
            },
            'directionChanges': {'status': 'unavailable', 'count': null},
          },
        ],
        'warnings': ['Mock result used for automated UI testing only.'],
      },
      analysisId: 'mock-analysis',
      inputVideoJson: _mockInputVideoJson,
    );
  }

  @override
  Future<void> cancelAnalysis(
    AnalysisCancellationToken cancellationToken,
  ) async {
    cancellationToken.requestCancellation();
  }

  @override
  Future<void> deleteAnalysis(String analysisId) async {}
}
