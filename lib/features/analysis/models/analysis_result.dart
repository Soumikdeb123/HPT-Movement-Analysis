class AnalysisResult {
  const AnalysisResult({
    required this.distanceMetres,
    required this.leftRightDistanceMetres,
    required this.forwardBackDistanceMetres,
    required this.averageSpeedKmh,
    required this.peakSpeedKmh,
    required this.peakAccelerationMetresPerSecondSquared,
    required this.peakDecelerationMetresPerSecondSquared,
    required this.directionChanges,
    required this.overallEffortLoad,
    required this.speedSamples,
    required this.isPrototype,
    this.annotatedVideoPath,
  });

  final double distanceMetres;
  final double leftRightDistanceMetres;
  final double forwardBackDistanceMetres;
  final double averageSpeedKmh;
  final double peakSpeedKmh;
  final double peakAccelerationMetresPerSecondSquared;
  final double peakDecelerationMetresPerSecondSquared;
  final int directionChanges;
  final double overallEffortLoad;
  final List<double> speedSamples;
  final bool isPrototype;
  final String? annotatedVideoPath;
}
