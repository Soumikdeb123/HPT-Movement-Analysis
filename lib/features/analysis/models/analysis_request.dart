class AnalysisRequest {
  const AnalysisRequest({
    required this.videoPath,
    required this.playerLabel,
    required this.includeExperimentalSpeed,
  });

  final String videoPath;
  final String playerLabel;
  final bool includeExperimentalSpeed;
}
