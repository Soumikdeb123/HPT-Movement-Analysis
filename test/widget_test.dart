import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_video_picker.dart';
import 'package:hpt_player_analysis/features/analysis/views/analysis_page.dart';

void main() {
  testWidgets('pixel results hide customer speed and acceleration curves', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AnalysisPage(
          gateway: _PixelGateway(),
          videoPicker: const _FakeVideoPicker(),
        ),
      ),
    );
    await tester.tap(find.byKey(const Key('select-video-button')));
    await tester.pumpAndSettle();
    final start = find.byKey(const Key('start-analysis-button'));
    await tester.ensureVisible(start);
    await tester.pumpAndSettle();
    await tester.tap(start);
    await tester.pumpAndSettle();
    expect(find.text('Metre-based charts unavailable'), findsOneWidget);
    expect(find.text('Speed over time'), findsNothing);
    expect(find.text('Signed acceleration / deceleration'), findsNothing);
    expect(find.byKey(const Key('acceleration-profile-chart')), findsNothing);
  });

  testWidgets('user can select a real file and see agreed prototype outputs', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: AnalysisPage(
          gateway: _ImmediateGateway(),
          videoPicker: const _FakeVideoPicker(),
        ),
      ),
    );

    final startButton = find.byKey(const Key('start-analysis-button'));
    expect(tester.widget<FilledButton>(startButton).onPressed, isNull);

    await tester.tap(find.byKey(const Key('select-video-button')));
    await tester.pumpAndSettle();

    expect(find.text('client-video.mp4'), findsOneWidget);
    expect(find.text('Near-court player'), findsOneWidget);
    expect(tester.widget<FilledButton>(startButton).onPressed, isNotNull);
    await tester.enterText(find.byKey(const Key('athlete-mass-field')), '75');
    await tester.pump();
    expect(tester.widget<FilledButton>(startButton).onPressed, isNotNull);

    await tester.ensureVisible(startButton);
    await tester.pumpAndSettle();
    await tester.tap(startButton);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('analysis-results')), findsOneWidget);
    expect(find.text('Movement analysis results'), findsOneWidget);
    expect(find.text('Tracking coverage'), findsOneWidget);
    expect(find.text('80 of 100 frames • 80%'), findsOneWidget);
    expect(find.text('500 m'), findsOneWidget);
    expect(find.text('Acceleration'), findsNothing);
    expect(find.text('Deceleration'), findsNothing);
    expect(find.text('Direction changes'), findsOneWidget);
    expect(find.text('Experimental'), findsWidgets);
    expect(find.text('Heatmap'), findsNothing);
    expect(find.text('Directional movement'), findsOneWidget);
    expect(find.text('Pixel effort index (demo)'), findsNothing);
    expect(find.text('3. Review prototype scope'), findsNothing);
    expect(
      find.text('Estimated Force-Velocity'),
      findsOneWidget,
    );
    await tester.scrollUntilVisible(
      find.byKey(const Key('force-velocity-chart')).first,
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('force-velocity-chart')), findsWidgets);
    expect(find.byKey(const Key('export-csv-button')), findsOneWidget);
    expect(find.byKey(const Key('export-json-button')), findsOneWidget);
    expect(find.byKey(const Key('export-video-button')), findsOneWidget);

    final clearButton = find.byKey(const Key('clear-analysis-button'));
    await tester.scrollUntilVisible(
      clearButton,
      500,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(clearButton);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('analysis-results')), findsNothing);
    expect(find.text('Choose video'), findsOneWidget);
  });
}

class _PixelGateway extends _ImmediateGateway {
  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
    VideoValidatedCallback? onVideoValidated,
  }) async => AnalysisResult.fromJson({
    'calibrationStatus': 'uncalibrated',
    'selectedTrackId': '0',
    'players': [
      {
        'trackId': '0',
        'speed': {'unit': 'px/s', 'samples': []},
        'acceleration': {'unit': 'px/s²', 'samples': []},
      },
    ],
  }, analysisId: 'pixel-test');
}

class _FakeVideoPicker implements AnalysisVideoPicker {
  const _FakeVideoPicker();

  @override
  Future<SelectedVideo?> pickVideo() async {
    return const SelectedVideo(
      path: 'C:/videos/client-video.mp4',
      name: 'client-video.mp4',
      sizeBytes: 1024,
    );
  }
}

class _ImmediateGateway implements AnalysisGateway {
  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
    VideoValidatedCallback? onVideoValidated,
  }) async {
    const inputVideo = {
      'originalFilename': 'client-video.mp4',
      'extension': '.mp4',
      'sizeBytes': 1024,
      'codecTag': 'avc1',
      'codecName': 'H.264 (AVC)',
      'widthPixels': 1920,
      'heightPixels': 1080,
      'framesPerSecond': 30.0,
      'frameCount': 100,
      'durationSeconds': 3.33,
      'decodedSampleFrames': 3,
      'requestedSampleFrames': 3,
      'compatibilityStatus': 'compatible',
      'warnings': <String>[],
    };
    onVideoValidated?.call(InputVideoMetadata.fromJson(inputVideo));
    onProgress(1);
    return AnalysisResult.fromJson(
      const {
        'calibrationStatus': 'estimated',
        'courtCalibration': {
          'status': 'estimated',
          'method': 'court_lines',
          'confidence': 0.96,
          'courtType': 'doubles',
          'widthMeters': 10.97,
          'lengthMeters': 23.77,
        },
        'video': {'processedFrames': 100},
        'selectedTrackId': '0',
        'players': [
          {
            'trackId': '0',
            'trackedFrames': 80,
            'overallEffort': {
              'status': 'experimental',
              'value': 10,
              'unit': 'AU',
              'note': 'Unvalidated pixel-motion proxy.',
            },
            'movementPath': {
              'status': 'experimental',
              'coordinateSystem': 'estimated_court_metres',
              'points': [
                {'timeSeconds': 0.0, 'x': 0.0, 'y': 0.0},
                {'timeSeconds': 1.0, 'x': 3.0, 'y': 4.0},
              ],
            },
            'totalDistance': {
              'status': 'experimental',
              'value': 500,
              'unit': 'm',
            },
            'speed': {
              'status': 'experimental',
              'average': 12,
              'peak': 18,
              'unit': 'm/s',
            },
            'acceleration': {'status': 'unavailable'},
            'deceleration': {'status': 'unavailable'},
            'directionChanges': {'status': 'unavailable'},
            'forceVelocity': {
              'status': 'experimental',
              'massKg': 75,
              'maximumVelocityMps': 4,
              'peakPropulsiveForceN': 120,
              'peakBrakingForceN': 90,
              'note': 'Estimated from entered body mass and video-derived acceleration.',
              'samples': [
                {
                  'timeSeconds': 0,
                  'velocityMps': 1,
                  'tangentialAccelerationMps2': 1.6,
                  'estimatedNetForceN': 120,
                  'phase': 'propulsive',
                },
                {
                  'timeSeconds': 1,
                  'velocityMps': 4,
                  'tangentialAccelerationMps2': -1.2,
                  'estimatedNetForceN': -90,
                  'phase': 'braking',
                },
              ],
            },
          },
        ],
        'warnings': [],
      },
      analysisId: 'test-analysis',
      inputVideoJson: inputVideo,
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
