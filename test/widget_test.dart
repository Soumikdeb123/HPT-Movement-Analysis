import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/services/analysis_video_picker.dart';
import 'package:hpt_player_analysis/features/analysis/views/analysis_page.dart';

void main() {
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

    await tester.ensureVisible(startButton);
    await tester.pumpAndSettle();
    await tester.tap(startButton);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('analysis-results')), findsOneWidget);
    expect(find.byKey(const Key('movement-path-chart')), findsOneWidget);
    expect(find.text('500 px'), findsOneWidget);
    expect(find.text('Acceleration'), findsOneWidget);
    expect(find.text('Deceleration'), findsOneWidget);
    expect(find.text('Direction changes'), findsOneWidget);
    expect(find.text('Uncalibrated'), findsOneWidget);
    expect(find.text('Heatmap'), findsNothing);
    expect(find.text('Directional movement'), findsOneWidget);
    expect(find.text('Overall effort load'), findsOneWidget);
    expect(find.byKey(const Key('export-csv-button')), findsOneWidget);
    expect(find.byKey(const Key('export-json-button')), findsOneWidget);
    expect(find.byKey(const Key('export-video-button')), findsOneWidget);

    final clearButton = find.byKey(const Key('clear-analysis-button'));
    await tester.scrollUntilVisible(clearButton, 500);
    await tester.pumpAndSettle();
    await tester.tap(clearButton);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('analysis-results')), findsNothing);
    expect(find.text('Choose video'), findsOneWidget);
  });
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
  }) async {
    onProgress(1);
    return AnalysisResult.fromJson(const {
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
          'totalDistance': {
            'status': 'experimental',
            'value': 500,
            'unit': 'px',
          },
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
    }, analysisId: 'test-analysis');
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
