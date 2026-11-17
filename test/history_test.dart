import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:hpt_player_analysis/features/auth/repositories/auth_repository.dart';
import 'package:hpt_player_analysis/features/history/repositories/analysis_history_repository.dart';
import 'package:hpt_player_analysis/features/history/views/analysis_history_page.dart';

void main() {
  setUp(() => AuthRepository.token = 'test-token');
  tearDown(() => AuthRepository.token = null);

  test('history sends auth and pagination and surfaces expired sessions', () async {
    final repository = AnalysisHistoryRepository(
      baseUri: Uri.parse('http://localhost:8000'),
      client: MockClient((request) async {
        expect(request.headers['Authorization'], 'Bearer test-token');
        expect(request.url.queryParameters['offset'], '20');
        return http.Response('{}', 401);
      }),
    );
    await expectLater(repository.list(offset: 20), throwsA(
      isA<HistoryException>().having((e) => e.sessionExpired, 'expired', true)));
  });

  testWidgets('history lists records and deletes only after confirmation', (tester) async {
    var deleted = false;
    final repository = AnalysisHistoryRepository(
      baseUri: Uri.parse('http://localhost:8000'),
      client: MockClient((request) async {
        if (request.method == 'DELETE') {
          deleted = true;
          return http.Response('', 204);
        }
        return http.Response(jsonEncode({'items': deleted ? [] : [{
          'analysisId': 'a' * 32, 'originalFilename': 'test1.mp4',
          'createdAt': '2026-11-18T00:00:00Z', 'status': 'completed',
          'targetPlayer': 'near',
        }], 'hasMore': false}), 200);
      }),
    );
    await tester.pumpWidget(MaterialApp(home: AnalysisHistoryPage(repository: repository)));
    await tester.pumpAndSettle();
    expect(find.text('test1.mp4'), findsOneWidget);
    await tester.tap(find.text('Delete analysis'));
    await tester.pumpAndSettle();
    expect(deleted, isFalse);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(deleted, isFalse);
    await tester.tap(find.text('Delete analysis'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(deleted, isTrue);
    expect(find.text('No analysis history yet.'), findsOneWidget);
  });
}
