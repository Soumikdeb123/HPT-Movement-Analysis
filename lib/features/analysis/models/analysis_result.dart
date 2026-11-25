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
}

double? _doubleFromJson(Object? value) =>
    value is num && value.isFinite ? value.toDouble() : null;

int? _intFromJson(Object? value) =>
    value is num && value.isFinite ? value.toInt() : null;

/// A missing value breaks the curve; it is not a zero measurement.
class MetricSample {
  const MetricSample(this.timeSeconds, this.value, {this.segmentId = 0});
  final double timeSeconds;
  final double? value;
  final int segmentId;

  static List<MetricSample> parse(Object? raw) {
    if (raw is! List) return const [];
    final result = <MetricSample>[];
    for (final point in raw.whereType<Map>()) {
      final time = _doubleFromJson(point['timeSeconds']);
      if (time == null || time < 0) continue;
      result.add(
        MetricSample(
          time,
          _doubleFromJson(point['value']),
          segmentId: _intFromJson(point['segmentId']) ?? 0,
        ),
      );
    }
    result.sort((a, b) => a.timeSeconds.compareTo(b.timeSeconds));
    return result;
  }
}

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
  const NumericMetric({
    this.details = const {},
    this.method,
    required this.status,
    this.value,
    this.unit,
    this.note,
    this.samples = const [],
    this.events = const [],
  });

  factory NumericMetric.fromJson(Map<String, dynamic> json) {
    return NumericMetric(
      details: {
        if (json['method'] == 'metric_motion_load_v1')
          for (final key in [
            'validSeconds',
            'speedAU',
            'accelerationAU',
            'brakingAU',
            'auPerValidMinute',
          ])
            key: _doubleFromJson(json[key]),
      },
      method: json['method'] as String?,
      status: MetricStatus.fromJson(json['status']),
      value: _doubleFromJson(json['value']),
      samples: MetricSample.parse(json['samples']),
      events: (json['events'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList(growable: false),
      unit: json['unit'] as String?,
      note: json['note'] as String?,
    );
  }

  final String? method;
  final Map<String, double?> details;
  final MetricStatus status;
  final double? value;
  final List<MetricSample> samples;
  final List<Map<String, dynamic>> events;
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
    this.samples = const [],
  });

  factory SpeedMetric.fromJson(Map<String, dynamic> json) {
    return SpeedMetric(
      status: MetricStatus.fromJson(json['status']),
      average: _doubleFromJson(json['average']),
      samples: MetricSample.parse(json['samples']),
      peak: _doubleFromJson(json['peak']),
      unit: json['unit'] as String?,
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final double? average;
  final List<MetricSample> samples;
  final double? peak;
  final String? unit;
  final String? note;
}

class ForceVelocitySample {
  const ForceVelocitySample({
    required this.timeSeconds,
    required this.velocityMps,
    required this.accelerationMps2,
    this.estimatedNetForceN,
    required this.estimatedForceNPerKg,
    required this.phase,
  });

  factory ForceVelocitySample.fromJson(Map<String, dynamic> json) {
    return ForceVelocitySample(
      timeSeconds: _doubleFromJson(json['timeSeconds']) ?? 0,
      velocityMps: _doubleFromJson(json['velocityMps']) ?? 0,
      accelerationMps2:
          _doubleFromJson(json['tangentialAccelerationMps2']) ?? 0,
      estimatedNetForceN: _doubleFromJson(json['estimatedNetForceN']),
      estimatedForceNPerKg:
          _doubleFromJson(json['estimatedForceNPerKg']) ??
          _doubleFromJson(json['tangentialAccelerationMps2']) ??
          0,
      phase: json['phase'] as String? ?? 'steady',
    );
  }

  final double timeSeconds;
  final double velocityMps;
  final double accelerationMps2;
  final double? estimatedNetForceN;
  final double estimatedForceNPerKg;
  final String phase;
}

class ForceVelocityEvent {
  const ForceVelocityEvent({
    required this.id,
    this.label = 'Key movement',
    required this.startTimeSeconds,
    required this.endTimeSeconds,
    required this.seekStartSeconds,
    required this.seekEndSeconds,
    required this.startSpeedMps,
    required this.peakSpeedMps,
    required this.meanForceNPerKg,
    this.durationSeconds = 0,
    this.deltaSpeedMps = 0,
    required this.startX,
    required this.startY,
    required this.endX,
    required this.endY,
    this.excluded = false,
  });

  factory ForceVelocityEvent.fromJson(Map<String, dynamic> json) =>
      ForceVelocityEvent(
        id: json['eventId'] as String? ?? 'event',
        label: json['label'] as String? ?? 'Key movement',
        startTimeSeconds: _doubleFromJson(json['startTimeSeconds']) ?? 0,
        endTimeSeconds: _doubleFromJson(json['endTimeSeconds']) ?? 0,
        seekStartSeconds: _doubleFromJson(json['videoSeekStartSeconds']) ?? 0,
        seekEndSeconds: _doubleFromJson(json['videoSeekEndSeconds']) ?? 0,
        startSpeedMps: _doubleFromJson(json['startSpeedMps']) ?? 0,
        peakSpeedMps: _doubleFromJson(json['peakSpeedMps']) ?? 0,
        meanForceNPerKg: _doubleFromJson(json['meanForceNPerKg']) ?? 0,
        durationSeconds: _doubleFromJson(json['durationSeconds']) ?? 0,
        deltaSpeedMps: _doubleFromJson(json['deltaSpeedMps']) ?? 0,
        startX: _doubleFromJson(json['startX']) ?? 0,
        startY: _doubleFromJson(json['startY']) ?? 0,
        endX: _doubleFromJson(json['endX']) ?? 0,
        endY: _doubleFromJson(json['endY']) ?? 0,
        excluded: json['excluded'] == true,
      );

  final String id;
  final String label;
  final double startTimeSeconds;
  final double endTimeSeconds;
  final double seekStartSeconds;
  final double seekEndSeconds;
  final double startSpeedMps;
  final double peakSpeedMps;
  final double meanForceNPerKg;
  final double durationSeconds;
  final double deltaSpeedMps;
  final double startX;
  final double startY;
  final double endX;
  final double endY;
  final bool excluded;
}

class ForceVelocityCurvePoint {
  const ForceVelocityCurvePoint({
    required this.velocityMps,
    required this.forceNPerKg,
  });

  factory ForceVelocityCurvePoint.fromJson(Map<String, dynamic> json) =>
      ForceVelocityCurvePoint(
        velocityMps: _doubleFromJson(json['velocityMps']) ?? 0,
        forceNPerKg: _doubleFromJson(json['forceNPerKg']) ?? 0,
      );

  final double velocityMps;
  final double forceNPerKg;
}

class ForceVelocitySpeedBin {
  const ForceVelocitySpeedBin({
    required this.label,
    required this.minSpeedMps,
    this.maxSpeedMps,
    this.representativeForceNPerKg,
    this.eventCount = 0,
    this.evidenceStatus = 'unavailable',
    this.comparisonStatus = 'no_baseline',
    this.baselineMedian,
    this.baselineLow,
    this.baselineHigh,
    this.changePercent,
    this.representativeEventIds = const [],
  });

  factory ForceVelocitySpeedBin.fromJson(Map<String, dynamic> json) =>
      ForceVelocitySpeedBin(
        label: json['label'] as String? ?? 'unknown',
        minSpeedMps: _doubleFromJson(json['minSpeedMps']) ?? 0,
        maxSpeedMps: _doubleFromJson(json['maxSpeedMps']),
        representativeForceNPerKg: _doubleFromJson(
          json['representativeForceNPerKg'],
        ),
        eventCount: _intFromJson(json['eventCount']) ?? 0,
        evidenceStatus: json['evidenceStatus'] as String? ?? 'unavailable',
        comparisonStatus: json['comparisonStatus'] as String? ?? 'no_baseline',
        baselineMedian: _doubleFromJson(json['baselineMedian']),
        baselineLow: _doubleFromJson(json['baselineLow']),
        baselineHigh: _doubleFromJson(json['baselineHigh']),
        changePercent: _doubleFromJson(json['changePercent']),
        representativeEventIds:
            (json['representativeEventIds'] as List? ?? const [])
                .whereType<String>()
                .toList(growable: false),
      );

  final String label;
  final double minSpeedMps;
  final double? maxSpeedMps;
  final double? representativeForceNPerKg;
  final int eventCount;
  final String evidenceStatus;
  final String comparisonStatus;
  final double? baselineMedian;
  final double? baselineLow;
  final double? baselineHigh;
  final double? changePercent;
  final List<String> representativeEventIds;

  String get title => switch (label) {
    'low' => 'Low-speed acceleration',
    'mid' => 'Mid-speed acceleration',
    'high' => 'High-speed acceleration',
    _ => 'Acceleration',
  };

  String get rangeLabel => maxSpeedMps == null
      ? '≥${minSpeedMps.toStringAsFixed(1)} m/s'
      : '${minSpeedMps.toStringAsFixed(1)}–${maxSpeedMps!.toStringAsFixed(1)} m/s';
}

class ForceVelocityQuality {
  const ForceVelocityQuality({
    this.status = 'unavailable',
    this.trackingCoverage = 0,
    this.calibrationConfidence = 0,
    this.validEventCount = 0,
    this.reasons = const [],
  });

  factory ForceVelocityQuality.fromJson(Map<String, dynamic> json) =>
      ForceVelocityQuality(
        status: json['status'] as String? ?? 'unavailable',
        trackingCoverage: _doubleFromJson(json['trackingCoverage']) ?? 0,
        calibrationConfidence:
            _doubleFromJson(json['calibrationConfidence']) ?? 0,
        validEventCount: _intFromJson(json['validEventCount']) ?? 0,
        reasons: (json['reasons'] as List? ?? const [])
            .whereType<String>()
            .toList(growable: false),
      );

  final String status;
  final double trackingCoverage;
  final double calibrationConfidence;
  final int validEventCount;
  final List<String> reasons;
}

class ForceVelocityAnalysis {
  const ForceVelocityAnalysis({
    required this.status,
    required this.samples,
    this.events = const [],
    this.currentCurve = const [],
    this.baselineCurve = const [],
    this.speedBins = const [],
    this.quality = const ForceVelocityQuality(),
    this.algorithmVersion,
    this.baselineAnalysisCount = 0,
    this.comparisonSummary,
    this.comparisonDetail,
    this.comparisonStatus = 'no_baseline',
    this.comparisonVelocityMinMps,
    this.comparisonVelocityMaxMps,
    this.recommendedEventIds = const [],
    this.massKg,
    this.peakEstimatedPropulsionN,
    this.maximumVelocityMps,
    this.peakPropulsiveForceN,
    this.peakBrakingForceN,
    this.note,
  });

  const ForceVelocityAnalysis.unavailable()
    : status = MetricStatus.unavailable,
      samples = const [],
      events = const [],
      currentCurve = const [],
      baselineCurve = const [],
      speedBins = const [],
      quality = const ForceVelocityQuality(),
      algorithmVersion = null,
      baselineAnalysisCount = 0,
      comparisonSummary = null,
      comparisonDetail = null,
      comparisonStatus = 'no_baseline',
      comparisonVelocityMinMps = null,
      comparisonVelocityMaxMps = null,
      recommendedEventIds = const [],
      massKg = null,
      peakEstimatedPropulsionN = null,
      maximumVelocityMps = null,
      peakPropulsiveForceN = null,
      peakBrakingForceN = null,
      note = null;

  factory ForceVelocityAnalysis.fromJson(Map<String, dynamic> json) {
    final rawSamples = json['samples'];
    return ForceVelocityAnalysis(
      status: MetricStatus.fromJson(json['status']),
      samples: rawSamples is List
          ? rawSamples
                .whereType<Map>()
                .where(
                  (s) => [
                    'timeSeconds',
                    'velocityMps',
                    'tangentialAccelerationMps2',
                  ].every((key) => _doubleFromJson(s[key]) != null),
                )
                .map(
                  (sample) => ForceVelocitySample.fromJson(
                    Map<String, dynamic>.from(sample),
                  ),
                )
                .toList(growable: false)
          : const [],
      events: (json['events'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                ForceVelocityEvent.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(growable: false),
      currentCurve: (json['currentCurve'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => ForceVelocityCurvePoint.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(growable: false),
      baselineCurve: (json['baselineCurve'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => ForceVelocityCurvePoint.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(growable: false),
      speedBins: (json['speedBins'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                ForceVelocitySpeedBin.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(growable: false),
      quality: ForceVelocityQuality.fromJson(
        Map<String, dynamic>.from(json['quality'] as Map? ?? const {}),
      ),
      algorithmVersion: json['algorithmVersion'] as String?,
      baselineAnalysisCount: _intFromJson(json['baselineAnalysisCount']) ?? 0,
      comparisonSummary: json['comparisonSummary'] as String?,
      comparisonDetail: json['comparisonDetail'] as String?,
      comparisonStatus: json['comparisonStatus'] as String? ?? 'no_baseline',
      comparisonVelocityMinMps: _doubleFromJson(
        json['comparisonVelocityMinMps'],
      ),
      comparisonVelocityMaxMps: _doubleFromJson(
        json['comparisonVelocityMaxMps'],
      ),
      recommendedEventIds: (json['recommendedEventIds'] as List? ?? const [])
          .whereType<String>()
          .toList(growable: false),
      massKg: _doubleFromJson(json['massKg']),
      peakEstimatedPropulsionN: _doubleFromJson(
        json['peakEstimatedPropulsionN'],
      ),
      maximumVelocityMps: _doubleFromJson(json['maximumVelocityMps']),
      peakPropulsiveForceN: _doubleFromJson(json['peakPropulsiveForceN']),
      peakBrakingForceN: _doubleFromJson(json['peakBrakingForceN']),
      note: json['note'] as String?,
    );
  }

  final MetricStatus status;
  final List<ForceVelocitySample> samples;
  final List<ForceVelocityEvent> events;
  final List<ForceVelocityCurvePoint> currentCurve;
  final List<ForceVelocityCurvePoint> baselineCurve;
  final List<ForceVelocitySpeedBin> speedBins;
  final ForceVelocityQuality quality;
  final String? algorithmVersion;
  final int baselineAnalysisCount;
  final String? comparisonSummary;
  final String? comparisonDetail;
  final String comparisonStatus;
  final double? comparisonVelocityMinMps;
  final double? comparisonVelocityMaxMps;
  final List<String> recommendedEventIds;
  final double? massKg;
  final double? peakEstimatedPropulsionN;
  final double? maximumVelocityMps;
  final double? peakPropulsiveForceN;
  final double? peakBrakingForceN;
  final String? note;

  double? get resolvedPeakEstimatedPropulsionN {
    if (peakEstimatedPropulsionN != null) return peakEstimatedPropulsionN;
    if (massKg == null || massKg! <= 0 || currentCurve.isEmpty) return null;
    final peak = currentCurve
        .map((point) => point.forceNPerKg)
        .where((value) => value.isFinite && value >= 0)
        .fold<double?>(
          null,
          (best, value) => best == null || value > best ? value : best,
        );
    return peak == null ? null : peak * massKg!;
  }
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
    this.trackedFrames,
    this.coverageFrameCount,
    this.metricDurationSeconds,
    this.excludedMetricSamples,
    this.forceVelocity = const ForceVelocityAnalysis.unavailable(),
    this.leftRightDistance = const NumericMetric(
      status: MetricStatus.unavailable,
    ),
    this.forwardBackDistance = const NumericMetric(
      status: MetricStatus.unavailable,
    ),
    this.overallEffort = const NumericMetric(
      status: MetricStatus.unavailable,
      note: 'Effort formula awaiting client validation.',
    ),
  });

  factory PlayerAnalysis.fromJson(Map<String, dynamic> json) {
    Map<String, dynamic> object(String key) =>
        Map<String, dynamic>.from(json[key] as Map? ?? const {});

    return PlayerAnalysis(
      leftRightDistance: NumericMetric.fromJson(object('leftRightDistance')),
      forwardBackDistance: NumericMetric.fromJson(
        object('forwardBackDistance'),
      ),
      overallEffort: NumericMetric.fromJson(object('overallEffort')),
      trackedFrames: _intFromJson(json['trackedFrames']),
      coverageFrameCount: _intFromJson(json['coverageFrameCount']),
      metricDurationSeconds: _doubleFromJson(
        object('coverage')['validDurationSeconds'],
      ),
      excludedMetricSamples: _intFromJson(
        object('coverage')['excludedSamples'],
      ),
      trackId: json['trackId']?.toString() ?? 'unknown',
      movementPath: MovementPath.fromJson(object('movementPath')),
      totalDistance: NumericMetric.fromJson(object('totalDistance')),
      speed: SpeedMetric.fromJson(object('speed')),
      acceleration: NumericMetric.fromJson(object('acceleration')),
      deceleration: NumericMetric.fromJson(object('deceleration')),
      directionChanges: DirectionChangesMetric.fromJson(
        object('directionChanges'),
      ),
      forceVelocity: ForceVelocityAnalysis.fromJson(object('forceVelocity')),
    );
  }

  final NumericMetric leftRightDistance;
  final NumericMetric forwardBackDistance;
  final NumericMetric overallEffort;
  final int? trackedFrames;
  final int? coverageFrameCount;
  final double? metricDurationSeconds;
  final int? excludedMetricSamples;
  final String trackId;
  final MovementPath movementPath;
  final NumericMetric totalDistance;
  final SpeedMetric speed;
  final NumericMetric acceleration;
  final NumericMetric deceleration;
  final DirectionChangesMetric directionChanges;
  final ForceVelocityAnalysis forceVelocity;
}

/// Video facts measured by the backend after it successfully decodes the file.
class InputVideoMetadata {
  const InputVideoMetadata({
    required this.originalFilename,
    required this.extension,
    required this.sizeBytes,
    required this.codecTag,
    required this.codecName,
    required this.widthPixels,
    required this.heightPixels,
    required this.framesPerSecond,
    required this.frameCount,
    required this.durationSeconds,
    required this.decodedSampleFrames,
    required this.requestedSampleFrames,
    required this.compatibilityStatus,
    required this.warnings,
  });

  factory InputVideoMetadata.fromJson(Map<String, dynamic> json) {
    return InputVideoMetadata(
      originalFilename: json['originalFilename'] as String? ?? 'Unknown video',
      extension: json['extension'] as String? ?? '',
      sizeBytes: _intFromJson(json['sizeBytes']) ?? 0,
      codecTag: json['codecTag'] as String? ?? 'unknown',
      codecName: json['codecName'] as String? ?? 'Unknown codec',
      widthPixels: _intFromJson(json['widthPixels']) ?? 0,
      heightPixels: _intFromJson(json['heightPixels']) ?? 0,
      framesPerSecond: _doubleFromJson(json['framesPerSecond']) ?? 0,
      frameCount: _intFromJson(json['frameCount']) ?? 0,
      durationSeconds: _doubleFromJson(json['durationSeconds']) ?? 0,
      decodedSampleFrames: _intFromJson(json['decodedSampleFrames']) ?? 0,
      requestedSampleFrames: _intFromJson(json['requestedSampleFrames']) ?? 0,
      compatibilityStatus: json['compatibilityStatus'] as String? ?? 'unknown',
      warnings: (json['warnings'] as List? ?? const [])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  final String originalFilename;
  final String extension;
  final int sizeBytes;
  final String codecTag;
  final String codecName;
  final int widthPixels;
  final int heightPixels;
  final double framesPerSecond;
  final int frameCount;
  final double durationSeconds;
  final int decodedSampleFrames;
  final int requestedSampleFrames;
  final String compatibilityStatus;
  final List<String> warnings;

  bool get hasWarnings => warnings.isNotEmpty;
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
    this.coachReportUrl,
    this.playerId,
    this.playerName,
    this.courtCalibration,
    this.algorithm,
    this.inferenceDevice,
    this.inputVideo,
    this.processedFrames,
    this.rawData = const {},
  });

  factory AnalysisResult.fromJson(
    Map<String, dynamic> json, {
    required String analysisId,
    Map<String, dynamic>? inputVideoJson,
  }) {
    final rawPlayers = json['players'];
    final rawVideo = Map<String, dynamic>.from(
      json['video'] as Map? ?? const {},
    );
    final rawData = Map<String, dynamic>.from(json);
    if (inputVideoJson != null) {
      rawData['inputVideo'] = Map<String, dynamic>.from(inputVideoJson);
    }
    return AnalysisResult(
      rawData: rawData,
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
      coachReportUrl: json['coachReportUrl'] as String?,
      playerId: json['playerId'] as String?,
      playerName: json['playerName'] as String?,
      courtCalibration: json['courtCalibration'] is Map
          ? CourtCalibrationResult.fromJson(
              Map<String, dynamic>.from(json['courtCalibration'] as Map),
            )
          : null,
      algorithm: json['algorithm'] as String?,
      inferenceDevice: json['inferenceDevice'] as String?,
      inputVideo: inputVideoJson == null
          ? null
          : InputVideoMetadata.fromJson(inputVideoJson),
      processedFrames: _intFromJson(rawVideo['processedFrames']),
      warnings: (json['warnings'] as List? ?? const [])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  final Map<String, dynamic> rawData;
  final String analysisId;
  final String calibrationStatus;
  final String? selectedTrackId;
  final List<PlayerAnalysis> players;
  final String? annotatedVideoUrl;
  final String? coachReportUrl;
  final String? playerId;
  final String? playerName;
  final CourtCalibrationResult? courtCalibration;
  final String? algorithm;
  final String? inferenceDevice;
  final InputVideoMetadata? inputVideo;
  final int? processedFrames;
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
