import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import 'analysis_gateway.dart';

class MockAnalysisGateway implements AnalysisGateway {
  const MockAnalysisGateway();

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
  }) async {
    for (var step = 1; step <= 10; step += 1) {
      await Future<void>.delayed(const Duration(milliseconds: 180));
      onProgress(step / 10);
    }

    return AnalysisResult(
      distanceMetres: 1264.8,
      leftRightDistanceMetres: 742.5,
      forwardBackDistanceMetres: 522.3,
      averageSpeedKmh: request.includeExperimentalSpeed ? 14.2 : 0,
      peakSpeedKmh: request.includeExperimentalSpeed ? 23.7 : 0,
      peakAccelerationMetresPerSecondSquared: request.includeExperimentalSpeed
          ? 3.8
          : 0,
      peakDecelerationMetresPerSecondSquared: request.includeExperimentalSpeed
          ? 4.1
          : 0,
      directionChanges: 47,
      overallEffortLoad: request.includeExperimentalSpeed ? 78 : 0,
      speedSamples: request.includeExperimentalSpeed
          ? const [0, 8.4, 14.1, 18.7, 12.9, 23.7, 9.6, 0]
          : const [],
      isPrototype: true,
    );
  }
}
