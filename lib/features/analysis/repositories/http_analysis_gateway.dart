import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/analysis_request.dart';
import '../models/analysis_result.dart';
import 'analysis_gateway.dart';

class AnalysisGatewayException implements Exception {
  const AnalysisGatewayException(this.message);

  final String message;

  @override
  String toString() => message;
}

class HttpAnalysisGateway implements AnalysisGateway {
  HttpAnalysisGateway({
    Uri? baseUri,
    http.Client? client,
    this.pollInterval = const Duration(seconds: 1),
    this.analysisTimeout = const Duration(hours: 2),
  })  : baseUri = baseUri ??
            Uri.parse(
              const String.fromEnvironment(
                'HPT_ANALYSIS_API_URL',
                defaultValue: 'http://127.0.0.1:8000/',
              ),
            ),
        _client = client ?? http.Client();

  final Uri baseUri;
  final Duration pollInterval;
  final Duration analysisTimeout;
  final http.Client _client;

  @override
  Future<AnalysisResult> analyseVideo(
    AnalysisRequest request, {
    required ProgressCallback onProgress,
  }) async {
    final deadline = DateTime.now().add(analysisTimeout);

    final createRequest =
        http.MultipartRequest('POST', baseUri.resolve('/api/analyses'))
          ..fields['target_player'] = _targetPlayer(request.playerLabel)
          ..files.add(
            await http.MultipartFile.fromPath(
              'video',
              request.videoPath,
            ),
          );

    http.StreamedResponse createResponse;

    try {
      createResponse = await _client.send(createRequest);
    } on Object catch (error) {
      throw AnalysisGatewayException(
        'Cannot reach the local analysis service. '
        'Make sure the Python backend is running. ($error)',
      );
    }

    var snapshot = await _decodeStreamedResponse(createResponse);

    final analysisId =
        snapshot['analysisId']?.toString() ??
        snapshot['analysis_id']?.toString() ??
        snapshot['job_id']?.toString();

    if (analysisId == null || analysisId.isEmpty) {
      throw const AnalysisGatewayException(
        'The analysis service returned an invalid job identifier.',
      );
    }

    while (true) {
      final progress = (snapshot['progress'] as num?)?.toDouble() ?? 0;
      onProgress(progress.clamp(0.0, 1.0));

      final status = snapshot['status']?.toString();

      if (status == 'completed') {
        final rawResult = snapshot['result'];

        if (rawResult is! Map) {
          throw const AnalysisGatewayException(
            'The completed analysis did not include a result.',
          );
        }

        onProgress(1);

        return _parseResult(
          Map<String, dynamic>.from(rawResult),
          request,
        );
      }

      if (status == 'failed') {
        throw AnalysisGatewayException(
          snapshot['error']?.toString() ?? 'Player tracking failed.',
        );
      }

      if (status == 'cancelled') {
        throw const AnalysisGatewayException('Analysis was cancelled.');
      }

      if (DateTime.now().isAfter(deadline)) {
        throw const AnalysisGatewayException(
          'The analysis did not finish within the configured timeout.',
        );
      }

      await Future<void>.delayed(pollInterval);

      try {
        final response = await _client.get(
          baseUri.resolve('/api/analyses/$analysisId'),
        );

        snapshot = _decodeResponse(response);
      } on AnalysisGatewayException {
        rethrow;
      } on Object catch (error) {
        throw AnalysisGatewayException(
          'Lost connection to the local analysis service. ($error)',
        );
      }
    }
  }

  AnalysisResult _parseResult(
    Map<String, dynamic> json,
    AnalysisRequest request,
  ) {
    final rawPlayers = json['players'];

    if (rawPlayers is! List || rawPlayers.isEmpty) {
      throw const AnalysisGatewayException(
        'The analysis completed without player results.',
      );
    }

    Map<String, dynamic>? selectedPlayer;

    final selectedTrackId = json['selectedTrackId']?.toString();

    if (selectedTrackId != null) {
      for (final player in rawPlayers.whereType<Map>()) {
        final playerJson = Map<String, dynamic>.from(player);

        if (playerJson['trackId']?.toString() == selectedTrackId) {
          selectedPlayer = playerJson;
          break;
        }
      }
    }

    selectedPlayer ??= Map<String, dynamic>.from(
      rawPlayers.whereType<Map>().first,
    );

    final distanceJson = _object(selectedPlayer, 'totalDistance');
    final speedJson = _object(selectedPlayer, 'speed');

    final distance =
        (distanceJson['value'] as num?)?.toDouble() ?? 0;

    final averageRaw =
        (speedJson['average'] as num?)?.toDouble() ?? 0;

    final peakRaw =
        (speedJson['peak'] as num?)?.toDouble() ?? 0;

    final speedUnit = speedJson['unit']?.toString();

    final conversionFactor = speedUnit == 'm/s' ? 3.6 : 1.0;

    final rawSamples = speedJson['samples'];

    final speedSamples = request.includeExperimentalSpeed &&
            rawSamples is List
        ? rawSamples
            .whereType<Map>()
            .map((sample) {
              final sampleJson = Map<String, dynamic>.from(sample);

              return SpeedSample(
                timeSeconds:
                    (sampleJson['timeSeconds'] as num?)?.toDouble() ?? 0,
                value:
                    ((sampleJson['value'] as num?)?.toDouble() ?? 0) *
                    conversionFactor,
              );
            })
            .toList(growable: false)
        : <SpeedSample>[];

    return AnalysisResult(
      distanceMetres: distance,
      averageSpeedKmh: request.includeExperimentalSpeed
          ? averageRaw * conversionFactor
          : 0,
      peakSpeedKmh: request.includeExperimentalSpeed
          ? peakRaw * conversionFactor
          : 0,
      speedSamples: speedSamples,
      isPrototype: true,
      annotatedVideoPath: _resolveAnnotatedVideo(json),
    );
  }

  String? _resolveAnnotatedVideo(Map<String, dynamic> json) {
    final value = json['annotatedVideoUrl']?.toString();

    if (value == null || value.isEmpty) {
      return null;
    }

    return baseUri.resolve(value).toString();
  }

  Map<String, dynamic> _object(
    Map<String, dynamic> json,
    String key,
  ) {
    final value = json[key];

    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    return const {};
  }

  String _targetPlayer(String playerLabel) {
    final normalized = playerLabel.toLowerCase();

    if (normalized.contains('far')) {
      return 'far';
    }

    return 'near';
  }

  Future<Map<String, dynamic>> _decodeStreamedResponse(
    http.StreamedResponse response,
  ) async {
    final body = await response.stream.bytesToString();
    return _decodeBody(response.statusCode, body);
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    return _decodeBody(response.statusCode, response.body);
  }

  Map<String, dynamic> _decodeBody(
    int statusCode,
    String body,
  ) {
    Object? decoded;

    try {
      decoded = jsonDecode(body);
    } on FormatException {
      throw AnalysisGatewayException(
        'The analysis service returned an unreadable response ($statusCode).',
      );
    }

    if (decoded is! Map) {
      throw const AnalysisGatewayException(
        'The analysis service returned an unexpected response.',
      );
    }

    final json = Map<String, dynamic>.from(decoded);

    if (statusCode < 200 || statusCode >= 300) {
      throw AnalysisGatewayException(
        json['detail']?.toString() ??
            'Analysis request failed ($statusCode).',
      );
    }

    return json;
  }
}