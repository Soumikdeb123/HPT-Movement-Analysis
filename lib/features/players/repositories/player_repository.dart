import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../core/config/api_endpoints.dart';
import '../../auth/repositories/auth_repository.dart';
import '../models/player_profile.dart';

class PlayerRepositoryException implements Exception {
  const PlayerRepositoryException(this.message);
  final String message;
  @override
  String toString() => message;
}

class PlayerRepository {
  PlayerRepository({http.Client? client, Uri? baseUri})
    : _client = client ?? http.Client(),
      _ownsClient = client == null,
      baseUri = baseUri ?? Uri.parse(ApiEndpoints.analysis);

  final http.Client _client;
  final bool _ownsClient;
  final Uri baseUri;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    if (AuthRepository.token != null)
      'Authorization': 'Bearer ${AuthRepository.token}',
  };

  Future<List<PlayerProfile>> list() async {
    final response = await _client
        .get(baseUri.resolve('/api/players'), headers: _headers)
        .timeout(const Duration(seconds: 30));
    final data = _decode(response);
    return (data['items'] as List? ?? const [])
        .whereType<Map>()
        .map((item) => PlayerProfile.fromJson(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }

  Future<PlayerProfile> create(String name, {double? defaultMassKg}) async {
    final response = await _client
        .post(
          baseUri.resolve('/api/players'),
          headers: _headers,
          body: jsonEncode({
            'displayName': name,
            'defaultMassKg': ?defaultMassKg,
          }),
        )
        .timeout(const Duration(seconds: 30));
    return PlayerProfile.fromJson(_decode(response));
  }

  Future<PlayerProfile> update(
    String id, {
    String? name,
    double? defaultMassKg,
    bool clearDefaultMass = false,
  }) async {
    final response = await _client
        .patch(
          baseUri.resolve('/api/players/${Uri.encodeComponent(id)}'),
          headers: _headers,
          body: jsonEncode({
            'displayName': ?name,
            if (defaultMassKg != null || clearDefaultMass)
              'defaultMassKg': defaultMassKg,
          }),
        )
        .timeout(const Duration(seconds: 30));
    return PlayerProfile.fromJson(_decode(response));
  }

  Map<String, dynamic> _decode(http.Response response) {
    Object? decoded;
    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw const PlayerRepositoryException(
        'Unexpected player service response.',
      );
    }
    if (decoded is! Map) {
      throw const PlayerRepositoryException(
        'Unexpected player service response.',
      );
    }
    final data = Map<String, dynamic>.from(decoded);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw PlayerRepositoryException(
        data['detail']?.toString() ?? 'Could not save the player.',
      );
    }
    return data;
  }

  void close() {
    if (_ownsClient) _client.close();
  }
}
