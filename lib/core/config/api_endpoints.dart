import 'package:flutter/foundation.dart';

/// Defaults target emulators/simulators only. Real phones need explicit LAN/HTTPS URLs.
class ApiEndpoints {
  static String defaultHost(TargetPlatform platform) =>
      platform == TargetPlatform.android ? '10.0.2.2' : '127.0.0.1';

  static final String auth = _resolve(
    const String.fromEnvironment('HPT_AUTH_API_URL'),
    3000,
  );
  static final String analysis = _resolve(
    const String.fromEnvironment('HPT_ANALYSIS_API_URL'),
    8000,
  );

  static String _resolve(String configured, int port) {
    final value = configured.trim().isEmpty
        ? 'http://${defaultHost(defaultTargetPlatform)}:$port'
        : configured.trim();
    final uri = Uri.tryParse(value);
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty) {
      throw ArgumentError(
        'Invalid API URL: use a complete http:// or https:// address.',
      );
    }
    return value.replaceFirst(RegExp(r'/+$'), '');
  }
}
