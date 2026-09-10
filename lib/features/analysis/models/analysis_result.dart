enum MetricStatus {
  calibrated,
  experimental,
  unavailable;

  factory MetricStatus.fromJson(Object? value) {
    return switch (value) {
      'calibrated' => MetricStatus.calibrated,
      'experimental' => MetricStatus.experimental,
      _ => MetricStatus.unavailable,
    };
  }

  String get label => switch (this) {
    MetricStatus.calibrated => 'Calibrated',
    MetricStatus.experimental => 'Experimental',
    MetricStatus.unavailable => 'Not available',
  };
}

double? _doubleFromJson(Object? value) =>
    value is num ? value.toDouble() : null;

class TrajectoryPoint {
  const TrajectoryPoint({
    required this.timeSeconds,
    required this.x,
    required this.y,
  });

  factory TrajectoryPoint.fromJson(Map<String, dynamic> json) {
    return TrajectoryPoint(
      timeSeconds: _doubleFromJson(json['timeSeconds']) ?? 0,
      x: _doubleFromJson(json['x']) ?? 0,
      y: _doubleFromJson(json['y']) ?? 0,
    );
  }

  final double timeSeconds;
  final double x;
  final double y;
}

class MovementPath {
  const MovementPath({
    required this.status,
    required this.coordinateSystem,
    required this.points,
    this.note,
  });

  factory MovementPath.fromJson(Map<String, dynamic> json) {
    final rawPoints = json['points'];
    return MovementPath(
      status: MetricStatus.fromJson(json['status']),
      coordinateSystem: json['coordinateSystem'] as String? ?? 'unknown',
      points: rawPoints is List
          ? rawPoints
                .whereType<Map>()
                .map(
                  (point) => TrajectoryPoint.fromJson(
                    Map<String, dynamic>.from(point),
                  ),
                )
                .toList(growable: false)
          : const [],
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final String coordinateSystem;
  final List<TrajectoryPoint> points;
  final String? note;
}

class NumericMetric {
  const NumericMetric({required this.status, this.value, this.unit, this.note});

  factory NumericMetric.fromJson(Map<String, dynamic> json) {
    return NumericMetric(
      status: MetricStatus.fromJson(json['status']),
      value: _doubleFromJson(json['value']),
      unit: json['unit'] as String?,
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final double? value;
  final String? unit;
  final String? note;
}

class SpeedMetric {
  const SpeedMetric({
    required this.status,
    this.average,
    this.peak,
    this.unit,
    this.note,
  });

  factory SpeedMetric.fromJson(Map<String, dynamic> json) {
    return SpeedMetric(
      status: MetricStatus.fromJson(json['status']),
      average: _doubleFromJson(json['average']),
      peak: _doubleFromJson(json['peak']),
      unit: json['unit'] as String?,
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final double? average;
  final double? peak;
  final String? unit;
  final String? note;
}

class DirectionChangesMetric {
  const DirectionChangesMetric({required this.status, this.count, this.note});

  factory DirectionChangesMetric.fromJson(Map<String, dynamic> json) {
    return DirectionChangesMetric(
      status: MetricStatus.fromJson(json['status']),
      count: (json['count'] as num?)?.toInt(),
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final int? count;
  final String? note;
}

class PlayerAnalysis {
  const PlayerAnalysis({
    required this.trackId,
    required this.movementPath,
    required this.totalDistance,
    required this.speed,
    required this.acceleration,
    required this.deceleration,
    required this.directionChanges,
  });

  factory PlayerAnalysis.fromJson(Map<String, dynamic> json) {
    Map<String, dynamic> object(String key) =>
        Map<String, dynamic>.from(json[key] as Map? ?? const {});

    return PlayerAnalysis(
      trackId: json['trackId']?.toString() ?? 'unknown',
      movementPath: MovementPath.fromJson(object('movementPath')),
      totalDistance: NumericMetric.fromJson(object('totalDistance')),
      speed: SpeedMetric.fromJson(object('speed')),
      acceleration: NumericMetric.fromJson(object('acceleration')),
      deceleration: NumericMetric.fromJson(object('deceleration')),
      directionChanges: DirectionChangesMetric.fromJson(
        object('directionChanges'),
      ),
    );
  }

  final String trackId;
  final MovementPath movementPath;
  final NumericMetric totalDistance;
  final SpeedMetric speed;
  final NumericMetric acceleration;
  final NumericMetric deceleration;
  final DirectionChangesMetric directionChanges;
}

class CourtCalibrationResult {
  const CourtCalibrationResult({
    required this.status,
    required this.method,
    required this.confidence,
    required this.courtType,
    required this.widthMeters,
    required this.lengthMeters,
  });

  factory CourtCalibrationResult.fromJson(Map<String, dynamic> json) {
    return CourtCalibrationResult(
      status: json['status'] as String? ?? 'unknown',
      method: json['method'] as String? ?? 'unknown',
      confidence: _doubleFromJson(json['confidence']) ?? 0,
      courtType: json['courtType'] as String? ?? 'unknown',
      widthMeters: _doubleFromJson(json['widthMeters']),
      lengthMeters: _doubleFromJson(json['lengthMeters']),
    );
  }

  final String status;
  final String method;
  final double confidence;
  final String courtType;
  final double? widthMeters;
  final double? lengthMeters;
}

class AnalysisResult {
  const AnalysisResult({
    required this.analysisId,
    required this.calibrationStatus,
    required this.players,
    required this.warnings,
    this.selectedTrackId,
    this.annotatedVideoUrl,
    this.courtCalibration,
    this.algorithm,
    this.inferenceDevice,
  });

  factory AnalysisResult.fromJson(
    Map<String, dynamic> json, {
    required String analysisId,
  }) {
    final rawPlayers = json['players'];
    return AnalysisResult(
      analysisId: analysisId,
      calibrationStatus: json['calibrationStatus'] as String? ?? 'uncalibrated',
      selectedTrackId: json['selectedTrackId']?.toString(),
      players: rawPlayers is List
          ? rawPlayers
                .whereType<Map>()
                .map(
                  (player) => PlayerAnalysis.fromJson(
                    Map<String, dynamic>.from(player),
                  ),
                )
                .toList(growable: false)
          : const [],
      annotatedVideoUrl: json['annotatedVideoUrl'] as String?,
      courtCalibration: json['courtCalibration'] is Map
          ? CourtCalibrationResult.fromJson(
              Map<String, dynamic>.from(json['courtCalibration'] as Map),
            )
          : null,
      algorithm: json['algorithm'] as String?,
      inferenceDevice: json['inferenceDevice'] as String?,
      warnings: (json['warnings'] as List? ?? const [])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  final String analysisId;
  final String calibrationStatus;
  final String? selectedTrackId;
  final List<PlayerAnalysis> players;
  final String? annotatedVideoUrl;
  final CourtCalibrationResult? courtCalibration;
  final String? algorithm;
  final String? inferenceDevice;
  final List<String> warnings;

  PlayerAnalysis? playerById(String? trackId) {
    if (players.isEmpty) return null;
    if (trackId == null) return players.first;
    for (final player in players) {
      if (player.trackId == trackId) return player;
    }
    return players.first;
  }
}
