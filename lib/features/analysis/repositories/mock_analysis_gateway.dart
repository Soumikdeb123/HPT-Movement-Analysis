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
      await Future<void>.delayed(const Duration(milliseconds: 180)); // wait for 180 ms
      onProgress(step / 10);
    }

    return AnalysisResult(
      distanceMetres: 1264.8,
      averageSpeedKmh: request.includeExperimentalSpeed ? 14.2 : 0, // ternary (if exp speed is enabled then abvg speed = 14.2 else 0)
      peakSpeedKmh: request.includeExperimentalSpeed ? 23.7 : 0,
      speedSamples: request.includeExperimentalSpeed
          ? const [
              SpeedSample(timeSeconds: 0, value: 8.0),
              SpeedSample(timeSeconds: 1, value: 10.5),
              SpeedSample(timeSeconds: 2, value: 12.5),
              SpeedSample(timeSeconds: 3, value: 15.2),
              SpeedSample(timeSeconds: 4, value: 18.4),
              SpeedSample(timeSeconds: 5, value: 20.1),
              SpeedSample(timeSeconds: 6, value: 23.7),
              SpeedSample(timeSeconds: 7, value: 19.0),
            ]
          : const [],
      isPrototype: true,
    );
  }
}