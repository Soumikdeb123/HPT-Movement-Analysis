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
    required this.playerId,
    required this.playerName,
    required this.targetPlayer,
    this.athleteMassKg,
  });

  final String videoPath;
  final String videoName;
  final String playerId;
  final String playerName;
  final TargetPlayerPosition targetPlayer;
  final double? athleteMassKg;
}
