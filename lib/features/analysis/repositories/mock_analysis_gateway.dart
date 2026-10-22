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
  averageSpeedKmh: request.includeExperimentalSpeed ? 14.2 : 0,
  peakSpeedKmh: request.includeExperimentalSpeed ? 23.7 : 0,

  speedSamples: request.includeExperimentalSpeed
      ? const [
          MetricSample(timeSeconds: 0, value: 0),
          MetricSample(timeSeconds: 1, value: 8.4),
          MetricSample(timeSeconds: 2, value: 14.1),
          MetricSample(timeSeconds: 3, value: 18.7),
          MetricSample(timeSeconds: 4, value: 12.9),
          MetricSample(timeSeconds: 5, value: 23.7),
          MetricSample(timeSeconds: 6, value: 9.6),
          MetricSample(timeSeconds: 7, value: 0),
        ]
      : const [],

  accelerationSamples: const [
    MetricSample(timeSeconds: 1, value: 2.4),
    MetricSample(timeSeconds: 2, value: 1.8),
    MetricSample(timeSeconds: 3, value: -2.5),
    MetricSample(timeSeconds: 4, value: -3.2),
  ],

  decelerationSamples: const [
    MetricSample(timeSeconds: 3, value: -2.5),
    MetricSample(timeSeconds: 4, value: -3.2),
  ],

  decelerationEfforts: const [
    DecelerationEffort(
      startTimeSeconds: 3,
      endTimeSeconds: 4,
      durationSeconds: 1,
      peakDeceleration: 3.2,
      meanDeceleration: 2.85,
      speedStart: 18.7,
      speedEnd: 12.9,
      highIntensity: true,
    ),
  ],

  decelerationEffortCount: 1,
  highIntensityDecelerationEffortCount: 1,
    isPrototype: true,
  );
  }
}