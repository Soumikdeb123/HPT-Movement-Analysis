enum TargetPlayerPosition {
  nearCourt('near', 'Near-court player'),
  farCourt('far', 'Far-court player');

  const TargetPlayerPosition(this.apiValue, this.label);

  final String apiValue;
  final String label;
}

class NormalizedCourtPoint {
  const NormalizedCourtPoint(this.x, this.y);

  final double x;
  final double y;

  List<double> toJson() => [x, y];
}

class AnalysisRequest {
  const AnalysisRequest({
    required this.videoPath,
    required this.videoName,
    required this.playerId,
    required this.playerName,
    required this.targetPlayer,
    this.athleteMassKg,
    this.courtCorners,
  });

  final String videoPath;
  final String videoName;
  final String playerId;
  final String playerName;
  final TargetPlayerPosition targetPlayer;
  final double? athleteMassKg;
  final List<NormalizedCourtPoint>? courtCorners;
}
