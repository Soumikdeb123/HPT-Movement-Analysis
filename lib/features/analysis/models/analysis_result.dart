class MetricSample {
  const MetricSample({
    required this.timeSeconds,
    required this.value,
  });

  final double timeSeconds;
  final double value;
}

class DecelerationEffort {
  const DecelerationEffort({
    required this.startTimeSeconds,
    required this.endTimeSeconds,
    required this.durationSeconds,
    required this.peakDeceleration,
    required this.meanDeceleration,
    required this.speedStart,
    required this.speedEnd,
    required this.highIntensity,
  });

  final double startTimeSeconds;
  final double endTimeSeconds;
  final double durationSeconds;
  final double peakDeceleration;
  final double meanDeceleration;
  final double speedStart;
  final double speedEnd;
  final bool highIntensity;
}

class AnalysisResult {
  const AnalysisResult({
    required this.distanceMetres,
    required this.averageSpeedKmh,
    required this.peakSpeedKmh,
    required this.speedSamples,
    required this.accelerationSamples,
    required this.decelerationSamples,
    required this.decelerationEfforts,
    required this.decelerationEffortCount,
    required this.highIntensityDecelerationEffortCount,
    required this.isPrototype,
    this.heatmapPath,
    this.annotatedVideoPath,
  });
  factory AnalysisResult.fromJson(
  Map<String, dynamic> json, {
  String? analysisId,
}) {
  final players = json['players'] as List<dynamic>? ?? const [];

  final player = players.isNotEmpty
      ? players.first as Map<String, dynamic>
      : <String, dynamic>{};

  final totalDistance =
      player['totalDistance'] as Map<String, dynamic>? ?? {};
  final speed =
      player['speed'] as Map<String, dynamic>? ?? {};
  final acceleration =
      player['acceleration'] as Map<String, dynamic>? ?? {};
  final deceleration =
      player['deceleration'] as Map<String, dynamic>? ?? {};

  List<MetricSample> parseSamples(dynamic rawSamples) {
    if (rawSamples is! List) return const [];

    return rawSamples
        .whereType<Map<String, dynamic>>()
        .map(
          (sample) => MetricSample(
            timeSeconds:
                (sample['timeSeconds'] as num?)?.toDouble() ?? 0,
            value:
                (sample['value'] as num?)?.toDouble() ?? 0,
          ),
        )
        .toList();
  }

  final rawEfforts = deceleration['efforts'];

  final efforts = rawEfforts is List
      ? rawEfforts
          .whereType<Map<String, dynamic>>()
          .map(
            (effort) => DecelerationEffort(
              startTimeSeconds:
                  (effort['startTimeSeconds'] as num?)?.toDouble() ?? 0,
              endTimeSeconds:
                  (effort['endTimeSeconds'] as num?)?.toDouble() ?? 0,
              durationSeconds:
                  (effort['durationSeconds'] as num?)?.toDouble() ?? 0,
              peakDeceleration:
                  (effort['peakDeceleration'] as num?)?.toDouble() ?? 0,
              meanDeceleration:
                  (effort['meanDeceleration'] as num?)?.toDouble() ?? 0,
              speedStart:
                  (effort['speedStart'] as num?)?.toDouble() ?? 0,
              speedEnd:
                  (effort['speedEnd'] as num?)?.toDouble() ?? 0,
              highIntensity:
                  effort['highIntensity'] == true,
            ),
          )
          .toList()
      : <DecelerationEffort>[];

  return AnalysisResult(
    distanceMetres:
        (totalDistance['value'] as num?)?.toDouble() ?? 0,
    averageSpeedKmh:
        (speed['average'] as num?)?.toDouble() ?? 0,
    peakSpeedKmh:
        (speed['peak'] as num?)?.toDouble() ?? 0,
    speedSamples:
        parseSamples(speed['samples']),
    accelerationSamples:
        parseSamples(acceleration['samples']),
    decelerationSamples:
        parseSamples(deceleration['samples']),
    decelerationEfforts:
        efforts,
    decelerationEffortCount:
        (deceleration['effortCount'] as num?)?.toInt() ??
            efforts.length,
    highIntensityDecelerationEffortCount:
        (deceleration['highIntensityEffortCount'] as num?)?.toInt() ??
            efforts.where((effort) => effort.highIntensity).length,
    isPrototype: false,
    annotatedVideoPath:
        json['annotatedVideoUrl'] as String?,
  );
}

  final double distanceMetres;
  final double averageSpeedKmh;
  final double peakSpeedKmh;

  final List<MetricSample> speedSamples;
  final List<MetricSample> accelerationSamples;
  final List<MetricSample> decelerationSamples;

  final List<DecelerationEffort> decelerationEfforts;
  final int decelerationEffortCount;
  final int highIntensityDecelerationEffortCount;

  final bool isPrototype;
  final String? heatmapPath;
  final String? annotatedVideoPath;
}

