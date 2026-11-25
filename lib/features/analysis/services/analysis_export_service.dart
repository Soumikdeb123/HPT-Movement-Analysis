import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;

import '../../auth/repositories/auth_repository.dart';
import '../models/analysis_result.dart';

class AnalysisExportService {
  String csvText(AnalysisResult result) {
    final rows = <List<Object?>>[
      [
        'Section',
        'Metric',
        'Video time',
        'Speed / range',
        'This session',
        'Personal baseline',
        'Difference',
        'Unit',
      ],
    ];
    final player = result.playerById(result.selectedTrackId);
    if (player == null) return _encodeRows(rows);

    void add(
      String section,
      String metric, {
      Object? videoTime,
      Object? speedRange,
      Object? session,
      Object? baseline,
      Object? difference,
      Object? unit,
    }) {
      rows.add([
        section,
        metric,
        videoTime,
        speedRange,
        session,
        baseline,
        difference,
        unit,
      ]);
    }

    add('Session', 'Player', session: result.playerName ?? 'Player');
    if (result.inputVideo case final video?) {
      add('Session', 'Video', session: video.originalFilename);
      add(
        'Session',
        'Video duration',
        session: _number(video.durationSeconds, 1),
        unit: 's',
      );
    }
    if (player.forceVelocity.massKg case final mass?) {
      add('Session', 'Body mass', session: _number(mass, 1), unit: 'kg');
    }

    void addMetric(String metric, NumericMetric value) {
      if (value.value == null) return;
      add(
        'Movement summary',
        metric,
        session: _number(value.value!, 2),
        unit: value.unit,
      );
    }

    addMetric('Lateral movement', player.leftRightDistance);
    addMetric('Forward/back movement', player.forwardBackDistance);
    addMetric('Total distance', player.totalDistance);
    if (player.speed.average case final value?) {
      add(
        'Movement summary',
        'Average speed',
        session: _number(value, 2),
        unit: player.speed.unit,
      );
    }
    if (player.speed.peak case final value?) {
      add(
        'Movement summary',
        'Peak speed',
        session: _number(value, 2),
        unit: player.speed.unit,
      );
    }
    if (player.directionChanges.count case final value?) {
      add('Movement summary', 'Direction changes', session: value);
    }
    final tracked = player.trackedFrames ?? player.movementPath.points.length;
    final total = player.coverageFrameCount ?? result.processedFrames;
    if (total != null && total > 0) {
      add(
        'Movement summary',
        'Tracking coverage',
        session: _number(tracked / total * 100, 1),
        unit: '%',
      );
    }
    if (player.metricDurationSeconds case final value?) {
      add(
        'Movement summary',
        'Analysed movement time',
        session: _number(value, 1),
        unit: 's',
      );
    }

    final effort = player.overallEffort;
    if (effort.method == 'metric_motion_load_v1') {
      void addEffort(String metric, String key) {
        if (effort.details[key] case final value?) {
          add(
            'Overall effort',
            metric,
            session: _number(value, 2),
            unit: key == 'validSeconds' ? 's' : 'AU',
          );
        }
      }

      addEffort('Usable time', 'validSeconds');
      addEffort('Speed contribution', 'speedAU');
      addEffort('Acceleration contribution', 'accelerationAU');
      addEffort('Braking contribution', 'brakingAU');
      addEffort('Effort per valid minute', 'auPerValidMinute');
      if (effort.value case final value?) {
        add(
          'Overall effort',
          'Total load',
          session: _number(value, 2),
          unit: effort.unit ?? 'AU',
        );
      }
    }

    final forceVelocity = player.forceVelocity;
    if (forceVelocity.comparisonSummary case final summary?) {
      if (summary.trim().isNotEmpty) {
        add('Force-Velocity', 'Match performance', session: summary.trim());
      }
    }
    if (forceVelocity.resolvedPeakEstimatedPropulsionN case final value?) {
      add(
        'Force-Velocity',
        'Peak estimated propulsion',
        session: _number(value, 1),
        unit: 'N',
      );
    }
    final curvePoints = _sampleCurve(forceVelocity.currentCurve, 15);
    for (var index = 0; index < curvePoints.length; index++) {
      final point = curvePoints[index];
      final baseline = _interpolate(
        forceVelocity.baselineCurve,
        point.velocityMps,
      );
      final difference = baseline == null || baseline == 0
          ? null
          : (point.forceNPerKg - baseline) / baseline * 100;
      add(
        'Force-Velocity curve',
        'Curve point ${index + 1}',
        speedRange: _number(point.velocityMps, 2),
        session: _number(point.forceNPerKg, 3),
        baseline: baseline == null ? null : _number(baseline, 3),
        difference: difference == null
            ? null
            : '${difference >= 0 ? '+' : ''}${_number(difference, 1)}%',
        unit: 'N/kg',
      );
    }

    for (final event in forceVelocity.events.where(
      (event) => !event.excluded,
    )) {
      add(
        'Key movement moments',
        event.label,
        videoTime: _time(event.startTimeSeconds),
        speedRange:
            '${_number(event.startSpeedMps, 1)}-${_number(event.peakSpeedMps, 1)} m/s',
        session: _number(event.meanForceNPerKg, 2),
        unit: 'N/kg',
      );
    }
    return _encodeRows(rows);
  }

  Future<String?> saveCsv(AnalysisResult result) =>
      FilePicker.platform.saveFile(
        dialogTitle: 'Save analysis summary',
        fileName: 'hpt-${result.analysisId}.csv',
        type: FileType.custom,
        allowedExtensions: const ['csv'],
        bytes: Uint8List.fromList([
          0xEF,
          0xBB,
          0xBF,
          ...utf8.encode(csvText(result)),
        ]),
      );

  Future<String?> saveReports(AnalysisResult result) async {
    final url = result.rawData['reportArchiveUrl'] as String?;
    if (url == null) throw StateError('No report archive is available.');
    final response = await http
        .get(
          Uri.parse(url),
          headers: {
            if (AuthRepository.token != null)
              'Authorization': 'Bearer ${AuthRepository.token}',
          },
        )
        .timeout(const Duration(minutes: 2));
    if (response.statusCode != 200) {
      throw StateError('Report download failed (HTTP ${response.statusCode}).');
    }
    return FilePicker.platform.saveFile(
      dialogTitle: 'Save charts and report',
      fileName: 'hpt-${result.analysisId}-reports.zip',
      type: FileType.custom,
      allowedExtensions: const ['zip'],
      bytes: response.bodyBytes,
    );
  }

  Future<String?> saveCoachReport(AnalysisResult result) async {
    final url = result.coachReportUrl;
    if (url == null) throw StateError('No coach PDF is available.');
    final response = await http
        .get(
          Uri.parse(url),
          headers: {
            if (AuthRepository.token != null)
              'Authorization': 'Bearer ${AuthRepository.token}',
          },
        )
        .timeout(const Duration(minutes: 2));
    if (response.statusCode != 200) {
      throw StateError(
        'Coach report download failed (HTTP ${response.statusCode}).',
      );
    }
    final safePlayer = (result.playerName ?? 'player').replaceAll(
      RegExp(r'[^A-Za-z0-9_-]+'),
      '-',
    );
    final shortId = result.analysisId.length <= 8
        ? result.analysisId
        : result.analysisId.substring(0, 8);
    return FilePicker.platform.saveFile(
      dialogTitle: 'Save coach report',
      fileName: 'hpt-$safePlayer-$shortId.pdf',
      type: FileType.custom,
      allowedExtensions: const ['pdf'],
      bytes: response.bodyBytes,
    );
  }

  Future<String?> saveVideo(AnalysisResult result) async {
    final url = result.annotatedVideoUrl;
    if (url == null) throw StateError('No annotated video is available.');
    final response = await http
        .get(
          Uri.parse(url),
          headers: {
            if (AuthRepository.token != null)
              'Authorization': 'Bearer ${AuthRepository.token}',
          },
        )
        .timeout(const Duration(minutes: 5));
    if (response.statusCode != 200) {
      throw StateError('Video download failed (HTTP ${response.statusCode}).');
    }
    return FilePicker.platform.saveFile(
      dialogTitle: 'Save annotated video',
      fileName: 'hpt-${result.analysisId}.mp4',
      type: FileType.custom,
      allowedExtensions: const ['mp4'],
      bytes: response.bodyBytes,
    );
  }

  static String _encodeRows(List<List<Object?>> rows) => rows
      .map(
        (row) => row
            .map(
              (value) => '"${(value ?? '').toString().replaceAll('"', '""')}"',
            )
            .join(','),
      )
      .join('\r\n');

  static String _number(num value, int digits) => value.toStringAsFixed(digits);

  static String _time(double seconds) {
    final minutes = seconds ~/ 60;
    final remainder = seconds - minutes * 60;
    return '$minutes:${remainder.toStringAsFixed(1).padLeft(4, '0')}';
  }

  static List<ForceVelocityCurvePoint> _sampleCurve(
    List<ForceVelocityCurvePoint> points,
    int maximum,
  ) {
    final valid = points
        .where(
          (point) => point.velocityMps.isFinite && point.forceNPerKg.isFinite,
        )
        .toList(growable: false);
    if (valid.length <= maximum) return valid;
    return List.generate(
      maximum,
      (index) => valid[((valid.length - 1) * index / (maximum - 1)).round()],
      growable: false,
    );
  }

  static double? _interpolate(
    List<ForceVelocityCurvePoint> points,
    double velocity,
  ) {
    final sorted = points.toList(growable: false)
      ..sort((a, b) => a.velocityMps.compareTo(b.velocityMps));
    if (sorted.isEmpty ||
        velocity < sorted.first.velocityMps ||
        velocity > sorted.last.velocityMps) {
      return null;
    }
    for (var index = 1; index < sorted.length; index++) {
      final left = sorted[index - 1];
      final right = sorted[index];
      if (velocity <= right.velocityMps) {
        final width = right.velocityMps - left.velocityMps;
        if (width == 0) return right.forceNPerKg;
        final ratio = (velocity - left.velocityMps) / width;
        return left.forceNPerKg +
            (right.forceNPerKg - left.forceNPerKg) * ratio;
      }
    }
    return sorted.last.forceNPerKg;
  }
}
