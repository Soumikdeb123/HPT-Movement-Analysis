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
  final List<double> speedSamples;
  final bool isPrototype;
  final String? heatmapPath;
  final String? annotatedVideoPath;
}
