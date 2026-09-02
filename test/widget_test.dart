import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/views/analysis_page.dart';

void main() {
  testWidgets('user can select a video and display prototype results', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: AnalysisPage(gateway: _ImmediateGateway())),
    );

    final startButton = find.byKey(const Key('start-analysis-button'));
    expect(tester.widget<FilledButton>(startButton).onPressed, isNull);

    await tester.tap(find.byKey(const Key('select-video-button')));
    await tester.pump();

    expect(find.text('sample_tennis_match.mp4'), findsOneWidget);
    expect(tester.widget<FilledButton>(startButton).onPressed, isNotNull);

    await tester.ensureVisible(startButton);
    await tester.pumpAndSettle();
    await tester.tap(startButton);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('analysis-results')), findsOneWidget);
    expect(find.text('500.0 m'), findsOneWidget);
    expect(find.text('Mock data'), findsOneWidget);
  });
}

class _ImmediateGateway implements AnalysisGateway {
  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
  }) async {
    onProgress(1);
    return const AnalysisResult(
      distanceMetres: 500,
      averageSpeedKmh: 12,
      peakSpeedKmh: 18,
      speedSamples: [0, 12, 18, 0],
      isPrototype: true,
    );
  }
}
