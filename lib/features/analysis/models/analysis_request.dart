enum TargetPlayerPosition {
  nearCourt('near', 'Near-court player'),
  farCourt('far', 'Far-court player');

  const TargetPlayerPosition(this.apiValue, this.label);

  final String apiValue;
  final String label;
}

class AnalysisRequest {
  const AnalysisRequest({
    required this.videoPath,
    required this.videoName,
    required this.targetPlayer,
  });

  final String videoPath;
  final String videoName;
  final TargetPlayerPosition targetPlayer;
}
