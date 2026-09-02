import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_request.dart';
import 'package:hpt_player_analysis/features/analysis/models/analysis_result.dart';
import 'package:hpt_player_analysis/features/analysis/repositories/analysis_gateway.dart';
import 'package:hpt_player_analysis/features/analysis/view_models/analysis_view_model.dart';

void main() {
  test('analysis progresses from selected video to completed result', () async {
    final viewModel = AnalysisViewModel(_ImmediateGateway());

    expect(viewModel.canStart, isFalse);

    viewModel.selectPrototypeVideo();
    expect(viewModel.canStart, isTrue);

    await viewModel.startAnalysis();

    expect(viewModel.status, AnalysisStatus.completed);
    expect(viewModel.progress, 1);
    expect(viewModel.result?.distanceMetres, 500);
  });
}

class _ImmediateGateway implements AnalysisGateway {
  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
  }) async {
    onProgress(0.5);
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
