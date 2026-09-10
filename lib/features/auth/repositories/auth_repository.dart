import 'dart:async';
import 'dart:convert';
import 'dart:io';

class AuthException implements Exception {
  const AuthException(this.message);

  final String message;

  @override
  String toString() => message;
}

class AuthRepository {
  static const String baseUrl = String.fromEnvironment(
    'HPT_AUTH_API_URL',
    defaultValue: 'http://10.0.2.2:3000',
  );

  static const String registerPath = '/api/auth/signIn';
  static const String loginPath = '/api/auth/login';

  static String? token;
  static String? userEmail;

  Future<void> register({
    required String username,
    required String email,
    required String password,
  }) async {
    if (username.trim().isEmpty) {
      throw const AuthException('Please enter your username.');
    }

    await _post(registerPath, {'email': email, 'password': password});
  }

  Future<void> login({required String email, required String password}) async {
    final data = await _post(loginPath, {'email': email, 'password': password});

    final receivedToken = data['token'];

    if (receivedToken is! String || receivedToken.trim().isEmpty) {
      throw const AuthException(
        'The server did not return a valid login token.',
      );
    }

    token = receivedToken;

    final receivedEmail = data['email'];
    userEmail = receivedEmail is String && receivedEmail.isNotEmpty
        ? receivedEmail
        : email;
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, String> body,
  ) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 15);

    try {
      return await _send(
        client,
        path,
        body,
      ).timeout(const Duration(seconds: 20));
    } on TimeoutException {
      throw const AuthException('The request timed out. Please try again.');
    } on SocketException {
      throw const AuthException(
        'Cannot connect to the server. Check the address and network.',
      );
    } on HandshakeException {
      throw const AuthException(
        'Cannot establish a secure connection to the server.',
      );
    } on HttpException {
      throw const AuthException(
        'The connection was interrupted. Please try again.',
      );
    } finally {
      client.close(force: true);
    }
  }

  Future<Map<String, dynamic>> _send(
    HttpClient client,
    String path,
    Map<String, String> body,
  ) async {
    final request = await client.postUrl(Uri.parse('$baseUrl$path'));

    // 登录请求不跟随重定向，避免把凭据发送到其他地址。
    request.followRedirects = false;
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode(body));

    final response = await request.close();
    final text = await response.transform(utf8.decoder).join();

    Map<String, dynamic> data = {};

    if (text.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(text);
        if (decoded is Map<String, dynamic>) {
          data = decoded;
        }
      } on FormatException {
        throw AuthException(
          'The server returned an unexpected response '
          '(HTTP ${response.statusCode}). Check the API address.',
        );
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = data['error'] ?? data['message'];

      throw AuthException(
        message is String && message.isNotEmpty
            ? message
            : 'Request failed (HTTP ${response.statusCode}).',
      );
    }

    return data;
  }
}
