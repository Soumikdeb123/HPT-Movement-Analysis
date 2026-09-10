import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/app.dart';
import 'package:hpt_player_analysis/features/auth/repositories/auth_repository.dart';

class FakeAuth extends AuthRepository {
  bool fail = false;
  @override
  Future<void> login({required String email, required String password}) async {
    if (fail) throw const AuthException('Invalid credentials');
    AuthRepository.token = 'test-session';
  }
}

void main() {
  testWidgets('consent then login opens analysis; logout clears the session', (
    tester,
  ) async {
    final auth = FakeAuth()..fail = true;
    await tester.pumpWidget(HptApp(authRepository: auth));
    final adult = find.byKey(const Key('adult-confirmation-checkbox'));
    await tester.ensureVisible(adult);
    await tester.pumpAndSettle();
    await tester.tap(adult);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('email')),
      'test@example.com',
    );
    await tester.enterText(
      find.byKey(const ValueKey('password')),
      'Password123',
    );
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();
    expect(find.text('Invalid credentials'), findsOneWidget);
    expect(find.text('Analyse tennis movement'), findsNothing);
    auth.fail = false;
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();
    expect(find.text('Analyse tennis movement'), findsOneWidget);
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pumpAndSettle();
    expect(AuthRepository.token, isNull);
    expect(find.text('Sign in'), findsOneWidget);
  });
}
