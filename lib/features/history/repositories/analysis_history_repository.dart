import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../core/config/api_endpoints.dart';
import '../../analysis/models/analysis_result.dart';
import '../../analysis/repositories/http_analysis_gateway.dart';
import '../../auth/repositories/auth_repository.dart';

class HistoryException implements Exception {
  const HistoryException(this.message, {this.sessionExpired = false});
  final String message;
  final bool sessionExpired;
  @override
  String toString() => message;
}

class AnalysisHistoryEntry {
  AnalysisHistoryEntry(this.data);
  final Map<String, dynamic> data;
  String get id => data['analysisId'] as String;
  String get videoName =>
      data['originalFilename'] as String? ?? 'Untitled video';
  String? get playerId => data['playerId'] as String?;
  String get playerName => data['playerName'] as String? ?? 'Unassigned';
  String get qualityStatus => data['qualityStatus'] as String? ?? 'unavailable';
  String get status => data['status'] as String? ?? 'unknown';
  String get targetPlayerLabel =>
      data['targetPlayer'] == 'far' ? 'Far-court player' : 'Near-court player';
  bool get isRunning =>
      const ['queued', 'processing', 'cancelling'].contains(status);
  String get statusLabel => switch (status) {
    'queued' => 'Queued',
    'processing' => 'Processing',
    'cancelling' => 'Cancelling',
    'completed' => 'Completed',
    'failed' => 'Failed',
    'cancelled' => 'Cancelled',
    _ => 'Unknown',
  };
  String get dateLabel {
    final date = DateTime.tryParse(data['createdAt'] as String? ?? '')
        ?.toLocal();
    if (date == null) return 'Date unavailable';
    String two(int value) => value.toString().padLeft(2, '0');
    return '${date.year}-${two(date.month)}-${two(date.day)} '
        '${two(date.hour)}:${two(date.minute)}';
  }

  String get summary {
    final forceVelocity = data['forceVelocitySummary'] as String?;
    if (forceVelocity != null && forceVelocity.isNotEmpty) {
      return forceVelocity;
    }
    final distance = data['totalDistance'];
    final speed = data['speed'];
    String? formatted(Object? value) =>
        value is num && value.isFinite ? value.toStringAsFixed(1) : null;
    final parts = <String>[];
    if (distance is Map && distance['status'] != 'unavailable') {
      final value = formatted(distance['value']);
      if (value != null) {
        parts.add('Distance: $value ${distance['unit'] ?? ''}');
      }
    }
    if (speed is Map && speed['status'] != 'unavailable') {
      final value = formatted(speed['average']);
      if (value != null) {
        parts.add('Average speed: $value ${speed['unit'] ?? ''}');
      }
    }
    return parts.join(' · ');
  }
}

class AnalysisHistoryBatch {
  const AnalysisHistoryBatch(this.items, this.hasMore);
  final List<AnalysisHistoryEntry> items;
  final bool hasMore;
}

class SavedAnalysis {
  SavedAnalysis(this.entry, this.result);
  final AnalysisHistoryEntry entry;
  final AnalysisResult? result;
}

class AnalysisHistoryRepository {
  AnalysisHistoryRepository({http.Client? client, Uri? baseUri})
    : _client = client ?? http.Client(),
      _ownsClient = client == null,
      baseUri = baseUri ?? Uri.parse(ApiEndpoints.analysis);
  final http.Client _client;
  final bool _ownsClient;
  final Uri baseUri;

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
  }) async {
    final token = AuthRepository.token;
    if (token == null || token.isEmpty) {
      throw const HistoryException(
        'Please sign in again.',
        sessionExpired: true,
      );
    }
    try {
      final request =
          http.Request(
              method,
              baseUri.resolve(path).replace(queryParameters: query),
            )
            ..followRedirects = false
            ..headers['Authorization'] = 'Bearer $token';
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(body);
      }
      final response = await (() async {
        final streamed = await _client.send(request);
        return http.Response.fromStream(streamed);
      })().timeout(const Duration(seconds: 30));
      if (response.statusCode == 401) {
        throw const HistoryException(
          'Session ended. Please sign in again.',
          sessionExpired: true,
        );
      }
      if (response.statusCode == 204) return {};
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) throw const FormatException();
      final data = Map<String, dynamic>.from(decoded);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw HistoryException(
          data['detail']?.toString() ?? 'Could not load history.',
        );
      }
      return data;
    } on TimeoutException {
      throw const HistoryException('Request timed out. Please try again.');
    } on FormatException {
      throw const HistoryException(
        'Unexpected server response. Check the analysis service.',
      );
    } on http.ClientException {
      throw const HistoryException(
        'Cannot connect to the analysis service. Please try again.',
      );
    }
  }

  Future<AnalysisHistoryBatch> list({int offset = 0, String? playerId}) async {
    final data = await _request(
      'GET',
      '/api/analyses',
      query: {'offset': '$offset', 'limit': '20', 'player_id': ?playerId},
    );
    if (data['items'] is! List) {
      throw const HistoryException('Unexpected history response.');
    }
    return AnalysisHistoryBatch(
      (data['items'] as List)
          .whereType<Map>()
          .map((item) => AnalysisHistoryEntry(Map<String, dynamic>.from(item)))
          .toList(),
      data['hasMore'] == true,
    );
  }

  Future<SavedAnalysis> get(String id) async {
    final snapshot = await _request(
      'GET',
      '/api/analyses/${Uri.encodeComponent(id)}',
    );
    final entry = AnalysisHistoryEntry(snapshot);
    return SavedAnalysis(
      entry,
      entry.status == 'completed'
          ? analysisResultFromSnapshot(snapshot, baseUri)
          : null,
    );
  }

  Future<void> delete(String id) async {
    await _request('DELETE', '/api/analyses/${Uri.encodeComponent(id)}');
  }

  Future<SavedAnalysis> setMovementMomentExcluded(
    String analysisId,
    String eventId,
    bool excluded,
  ) async {
    final snapshot = await _request(
      'PATCH',
      '/api/analyses/${Uri.encodeComponent(analysisId)}/movement-moments/'
          '${Uri.encodeComponent(eventId)}',
      body: {'excluded': excluded},
    );
    final entry = AnalysisHistoryEntry(snapshot);
    return SavedAnalysis(entry, analysisResultFromSnapshot(snapshot, baseUri));
  }

  void close() {
    if (_ownsClient) _client.close();
  }
}
