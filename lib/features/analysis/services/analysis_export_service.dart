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
      ['track_id', 'metric', 'value', 'unit', 'status', 'note'],
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
      metric('overall_effort', player.overallEffort);
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
    }
    return rows.map((row) => row.map(cell).join(',')).join('\r\n');
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
