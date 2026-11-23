class PlayerProfile {
  const PlayerProfile({
    required this.id,
    required this.name,
    this.defaultMassKg,
    this.analysisCount = 0,
    this.lastAnalysisAt,
  });

  factory PlayerProfile.fromJson(Map<String, dynamic> json) => PlayerProfile(
    id: json['playerId'] as String,
    name: json['displayName'] as String? ?? 'Unnamed player',
    defaultMassKg: (json['defaultMassKg'] as num?)?.toDouble(),
    analysisCount: (json['analysisCount'] as num?)?.toInt() ?? 0,
    lastAnalysisAt: DateTime.tryParse(json['lastAnalysisAt'] as String? ?? ''),
  );

  final String id;
  final String name;
  final double? defaultMassKg;
  final int analysisCount;
  final DateTime? lastAnalysisAt;
}
