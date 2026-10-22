class MetricSample {
  const MetricSample({
    required this.timeSeconds,
    required this.value,
  });

  final double timeSeconds;
  final double value;
}

class DecelerationEffort {
  const DecelerationEffort({
    required this.startTimeSeconds,
    required this.endTimeSeconds,
    required this.durationSeconds,
    required this.peakDeceleration,
    required this.meanDeceleration,
    required this.speedStart,
    required this.speedEnd,
    required this.highIntensity,
  });

  final double startTimeSeconds;
  final double endTimeSeconds;
  final double durationSeconds;
  final double peakDeceleration;
  final double meanDeceleration;
  final double speedStart;
  final double speedEnd;
  final bool highIntensity;
}

class AnalysisResult {
  const AnalysisResult({
    required this.distanceMetres,
    required this.averageSpeedKmh,
    required this.peakSpeedKmh,
    required this.speedSamples,
    required this.accelerationSamples,
    required this.decelerationSamples,
    required this.decelerationEfforts,
    required this.decelerationEffortCount,
    required this.highIntensityDecelerationEffortCount,
    required this.isPrototype,
    this.heatmapPath,
    this.annotatedVideoPath,
  });

  final double distanceMetres;
  final double averageSpeedKmh;
  final double peakSpeedKmh;

  final List<MetricSample> speedSamples;
  final List<MetricSample> accelerationSamples;
  final List<MetricSample> decelerationSamples;

  final List<DecelerationEffort> decelerationEfforts;
  final int decelerationEffortCount;
  final int highIntensityDecelerationEffortCount;

  final bool isPrototype;
  final String? heatmapPath;
  final String? annotatedVideoPath;
}

