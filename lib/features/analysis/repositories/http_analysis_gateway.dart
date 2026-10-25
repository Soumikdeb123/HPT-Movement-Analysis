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
  }) : baseUri =
           baseUri ??
           Uri.parse(
             const String.fromEnvironment(
               'HPT_ANALYSIS_API_URL',
               defaultValue: 'http://127.0.0.1:8000/',
             ),
           ),
       _client = client ?? http.Client(),
       _ownsClient = client == null;

  final Uri baseUri;
  final Duration pollInterval;
  final Duration analysisTimeout;
  final http.Client _client;
  final bool _ownsClient;

  @override
Future<AnalysisResult> analyseVideo(
  AnalysisRequest request, {
  required ProgressCallback onProgress,
}) async {
    final deadline = DateTime.now().add(analysisTimeout);
    final createRequest =
        http.MultipartRequest('POST', baseUri.resolve('/api/analyses'))
          ..fields['target_player'] = request.playerLabel
          ..files.add(
            await http.MultipartFile.fromPath(
              'video',
              request.videoPath,
              filename: request.videoPath.split('/').last,
            ),
          );

    http.StreamedResponse createResponse;
    try {
      createResponse = await _client.send(createRequest);
    } on Object catch (error) {
      throw AnalysisGatewayException(
        'Cannot reach the local analysis service. Start the Python server and '
        'try again. ($error)',
      );
    }

    var snapshot = await _decodeStreamedResponse(createResponse);
    final analysisId = snapshot['analysisId'] as String?;
    if (analysisId == null || analysisId.isEmpty) {
      throw const AnalysisGatewayException(
        'The analysis service returned an invalid job identifier.',
      );
    }

    while (true) {

      final progress = (snapshot['progress'] as num?)?.toDouble() ?? 0;
      onProgress(progress.clamp(0, 1));

      final status = snapshot['status'] as String?;
      if (status == 'completed') {
        final rawResult = snapshot['result'];
        if (rawResult is! Map) {
          throw const AnalysisGatewayException(
            'The completed analysis did not include a result.',
          );
        }
        final resultJson = Map<String, dynamic>.from(rawResult);
        final videoUrl = resultJson['annotatedVideoUrl'] as String?;
        if (videoUrl != null) {
          resultJson['annotatedVideoUrl'] = baseUri
              .resolve(videoUrl)
              .toString();
        }
        onProgress(1);
        return AnalysisResult.fromJson(resultJson, analysisId: analysisId);
      }
      if (status == 'failed') {
        throw AnalysisGatewayException(
          snapshot['error'] as String? ?? 'Player tracking failed.',
        );
      }

      if (DateTime.now().isAfter(deadline)) {
        throw const AnalysisGatewayException(
          'The analysis did not finish within the configured timeout.',
        );
      }

      await Future<void>.delayed(pollInterval);
      http.Response pollResponse;
      try {
        pollResponse = await _client.get(
          baseUri.resolve('/api/analyses/$analysisId'),
        );
      } on Object catch (error) {
        throw AnalysisGatewayException(
          'Lost connection to the local analysis service. ($error)',
        );
      }
      snapshot = _decodeResponse(pollResponse);
    }
  }

Future<void> deleteAnalysis(String analysisId) async {
    final response = await _client.delete(
      baseUri.resolve('/api/analyses/$analysisId'),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      _decodeResponse(response);
    }
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

  Map<String, dynamic> _decodeBody(int statusCode, String body) {
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
        json['detail'] as String? ?? 'Analysis request failed ($statusCode).',
      );
    }
    return json;
  }

  void close() {
    if (_ownsClient) _client.close();
  }
}
