class SpeedSample {
  const SpeedSample({
    required this.timeSeconds,
    required this.value,
  });

  final double timeSeconds;
  final double value;
}

class AnalysisResult {
  const AnalysisResult({
    required this.distanceMetres,
    required this.averageSpeedKmh,
    required this.peakSpeedKmh,
    required this.speedSamples,
    required this.isPrototype,
    this.heatmapPath,
    this.annotatedVideoPath,
  });

  final double distanceMetres;
  final double averageSpeedKmh;
  final double peakSpeedKmh;
  final List<SpeedSample> speedSamples;
  final bool isPrototype;
  final String? heatmapPath;
  final String? annotatedVideoPath;
}