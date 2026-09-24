import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/http_analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_video_picker.dart';
import 'package:hpt_player_analysis/features/analysis/views/analysis_page.dart';

void main() {
  testWidgets('user can select a real file and see agreed prototype outputs', (
    tester,
  ) async {
    final gateway = _StagedGateway();
    await tester.pumpWidget(
      MaterialApp(
        home: AnalysisPage(
          gateway: gateway,
          videoPicker: const _FakeVideoPicker(),
        ),
      ),
    );

    final startButton = find.byKey(const Key('start-analysis-button'));
    expect(tester.widget<FilledButton>(startButton).onPressed, isNull);

    await tester.tap(find.byKey(const Key('select-video-button')));
    await tester.pumpAndSettle();

    expect(find.text('client-video.mp4'), findsOneWidget);
    expect(find.textContaining('Ready to validate'), findsOneWidget);
    expect(find.text('Near-court player'), findsOneWidget);
    expect(tester.widget<FilledButton>(startButton).onPressed, isNotNull);

    await tester.ensureVisible(startButton);
    await tester.pumpAndSettle();
    await tester.tap(startButton);
    await tester.pump();

    expect(find.textContaining('Checking compatibility'), findsOneWidget);

    gateway.completeValidation();
    await tester.pump();

    expect(find.textContaining('Compatible • Analysing'), findsOneWidget);
    expect(find.byKey(const Key('input-video-metadata')), findsOneWidget);

    gateway.completeAnalysis();
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('analysis-results')), findsOneWidget);
    expect(find.byKey(const Key('movement-path-chart')), findsOneWidget);
    expect(find.text('500 px'), findsOneWidget);
    expect(find.text('Acceleration'), findsOneWidget);
    expect(find.text('Deceleration'), findsOneWidget);
    expect(find.text('Direction changes'), findsOneWidget);
    expect(find.text('Uncalibrated'), findsOneWidget);
    expect(find.byKey(const Key('input-video-metadata')), findsOneWidget);
    expect(find.text('H.264 (AVC)'), findsOneWidget);
    expect(find.text('1920 × 1080 • 30.00 FPS • 0:10'), findsOneWidget);
    expect(find.text('Heatmap'), findsNothing);

    final clearButton = find.byKey(const Key('clear-analysis-button'));
    await tester.scrollUntilVisible(clearButton, 500);
    await tester.pumpAndSettle();
    await tester.tap(clearButton);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('analysis-results')), findsNothing);
    expect(find.text('Choose video'), findsOneWidget);
  });

  testWidgets('an undecodable MP4 is reported inside the app', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: AnalysisPage(
          gateway: _RejectingGateway(),
          videoPicker: _FakeVideoPicker(name: 'fake-video.mp4'),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('select-video-button')));
    await tester.pumpAndSettle();
    final startButton = find.byKey(const Key('start-analysis-button'));
    await tester.ensureVisible(startButton);
    await tester.pumpAndSettle();
    await tester.tap(startButton);
    await tester.pumpAndSettle();

    expect(find.textContaining('Not compatible'), findsOneWidget);
    expect(find.text('The uploaded file cannot be decoded.'), findsOneWidget);
    expect(find.byKey(const Key('input-video-metadata')), findsNothing);
  });
}

class _FakeVideoPicker implements AnalysisVideoPicker {
  const _FakeVideoPicker({this.name = 'client-video.mp4'});

  final String name;

  @override
  Future<SelectedVideo?> pickVideo() async {
    return SelectedVideo(path: 'C:/videos/$name', name: name, sizeBytes: 1024);
  }
}

class _StagedGateway implements AnalysisGateway {
  final Completer<void> _validationGate = Completer<void>();
  final Completer<AnalysisResult> _analysisResult = Completer<AnalysisResult>();

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required VideoValidatedCallback onVideoValidated,
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  }) async {
    await _validationGate.future;
    onVideoValidated(InputVideoMetadata.fromJson(_inputVideoJson));
    onProgress(0.25);
    return _analysisResult.future;
  }

  void completeValidation() => _validationGate.complete();

  void completeAnalysis() => _analysisResult.complete(_testResult);

  @override
  Future<void> cancelAnalysis(
    AnalysisCancellationToken cancellationToken,
  ) async {
    cancellationToken.requestCancellation();
  }

  @override
  Future<void> deleteAnalysis(String analysisId) async {}
}

class _RejectingGateway implements AnalysisGateway {
  const _RejectingGateway();

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required VideoValidatedCallback onVideoValidated,
    required ProgressCallback onProgress,
    required AnalysisCancellationToken cancellationToken,
  }) {
    throw const AnalysisGatewayException(
      'The uploaded file cannot be decoded.',
    );
  }

  @override
  Future<void> cancelAnalysis(
    AnalysisCancellationToken cancellationToken,
  ) async {}

  @override
  Future<void> deleteAnalysis(String analysisId) async {}
}

const _inputVideoJson = <String, dynamic>{
  'originalFilename': 'client-video.mp4',
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

final _testResult = AnalysisResult.fromJson(
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
            {'timeSeconds': 0.0, 'x': 0.0, 'y': 0.0},
            {'timeSeconds': 1.0, 'x': 3.0, 'y': 4.0},
          ],
        },
        'totalDistance': {'status': 'experimental', 'value': 500, 'unit': 'px'},
        'speed': {
          'status': 'experimental',
          'average': 12,
          'peak': 18,
          'unit': 'px/s',
        },
        'acceleration': {'status': 'unavailable'},
        'deceleration': {'status': 'unavailable'},
        'directionChanges': {'status': 'unavailable'},
      },
    ],
    'warnings': [],
  },
  analysisId: 'test-analysis',
  inputVideoJson: _inputVideoJson,
);
