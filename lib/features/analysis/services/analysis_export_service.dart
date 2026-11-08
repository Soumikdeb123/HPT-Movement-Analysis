import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;

import '../models/analysis_result.dart';
import '../../auth/repositories/auth_repository.dart';

class AnalysisExportService {
  String jsonText(AnalysisResult result) =>
      const JsonEncoder.withIndent('  ')
          .convert({'analysisId': result.analysisId, ...result.rawData});

  String csvText(AnalysisResult result) {
    String cell(Object? value) =>
        '"${(value ?? '').toString().replaceAll('"', '""')}"';
    final rows = <List<Object?>>[
      [
        'track_id',
        'metric',
        'value',
        'unit',
        'status',
        'note',
        'time_seconds',
        'segment_id',
      ],
    ];
    for (final player in result.players) {
      void metric(String label, NumericMetric m) => rows.add([
        player.trackId,
        label,
        m.value,
        m.unit,
        m.status.name,
        m.note,
      ]);
      metric('total_distance', player.totalDistance);
      metric('left_right_distance', player.leftRightDistance);
      metric('forward_back_distance', player.forwardBackDistance);
      metric('peak_acceleration', player.acceleration);
      metric('peak_deceleration', player.deceleration);
      metric('overall_effort_pending_client_definition', player.overallEffort);
      void series(String label, List<MetricSample> points, String? unit) {
        for (final p in points) {
          rows.add([
            player.trackId,
            label,
            p.value,
            unit,
            'experimental',
            'Screened samples; gaps are excluded.',
            p.timeSeconds,
            p.segmentId,
          ]);
        }
      }

      series('speed_sample', player.speed.samples, player.speed.unit);
      series(
        'signed_acceleration_sample',
        player.acceleration.samples,
        player.acceleration.unit,
      );
      for (final p in player.forceVelocity.samples) {
        rows.add([
          player.trackId,
          'estimated_tangential_net_force_sample',
          p.estimatedNetForceN,
          'N',
          player.forceVelocity.status.name,
          'Not a fatigue score.',
          p.timeSeconds,
          null,
        ]);
      }
      for (final event in player.deceleration.events) {
        rows.add([
          player.trackId,
          'braking_event_peak',
          event['peakDecelerationMps2'],
          'm/s²',
          'experimental',
          'Duration: ${event['durationSeconds']} s',
          event['startTimeSeconds'],
          null,
        ]);
      }
      rows.add([
        player.trackId,
        'average_speed',
        player.speed.average,
        player.speed.unit,
        player.speed.status.name,
        player.speed.note,
      ]);
      rows.add([
        player.trackId,
        'peak_speed',
        player.speed.peak,
        player.speed.unit,
        player.speed.status.name,
        player.speed.note,
      ]);
      rows.add([
        player.trackId,
        'direction_changes',
        player.directionChanges.count,
        'count',
        player.directionChanges.status.name,
        player.directionChanges.note,
      ]);
      rows.addAll([
        [
          player.trackId,
          'force_velocity_maximum_velocity',
          player.forceVelocity.maximumVelocityMps,
          'm/s',
          player.forceVelocity.status.name,
          player.forceVelocity.note,
        ],
        [
          player.trackId,
          'estimated_peak_propulsive_force',
          player.forceVelocity.peakPropulsiveForceN,
          'N',
          player.forceVelocity.status.name,
          player.forceVelocity.note,
        ],
        [
          player.trackId,
          'estimated_peak_braking_force',
          player.forceVelocity.peakBrakingForceN,
          'N',
          player.forceVelocity.status.name,
          player.forceVelocity.note,
        ],
      ]);
    }
    return rows
        .map(
          (row) => [
            ...row,
            ...List<Object?>.filled(8 - row.length, null),
          ].map(cell).join(','),
        )
        .join('\r\n');
  }

  Future<String?> saveData(AnalysisResult result, {required bool csv}) =>
      FilePicker.platform.saveFile(
        dialogTitle: 'Save analysis data',
        fileName: 'hpt-${result.analysisId}.${csv ? 'csv' : 'json'}',
        type: FileType.custom,
        allowedExtensions: [csv ? 'csv' : 'json'],
        bytes: Uint8List.fromList(
          utf8.encode(csv ? csvText(result) : jsonText(result)),
        ),
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
      dialogTitle: 'Save report images and data',
      fileName: 'hpt-${result.analysisId}-reports.zip',
      type: FileType.custom,
      allowedExtensions: ['zip'],
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
      allowedExtensions: ['mp4'],
      bytes: response.bodyBytes,
    );
  }
}
