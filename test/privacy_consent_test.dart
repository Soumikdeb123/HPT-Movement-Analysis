import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hpt_player_analysis/app.dart';

void main() {
  testWidgets('privacy gate is shown before the application', (tester) async {
    await tester.pumpWidget(const HptApp());

    expect(find.byKey(const Key('privacy-consent-screen')), findsOneWidget);
    expect(find.text('Analyse tennis movement'), findsNothing);
  });

  testWidgets('adult confirmation immediately opens the application', (
    tester,
  ) async {
    await tester.pumpWidget(const HptApp());

    final adultCheckbox = find.byKey(const Key('adult-confirmation-checkbox'));
    await tester.ensureVisible(adultCheckbox);
    await tester.pumpAndSettle();
    await tester.tap(adultCheckbox);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('privacy-consent-screen')), findsNothing);
    expect(find.text('Analyse tennis movement'), findsOneWidget);
  });

  testWidgets('under-18 access requires every acknowledgement', (tester) async {
    await tester.pumpWidget(const HptApp());

    final under18Button = find.byKey(const Key('under-18-button'));
    await tester.ensureVisible(under18Button);
    await tester.pumpAndSettle();
    await tester.tap(under18Button);
    await tester.pumpAndSettle();

    final continueButton = find.byKey(const Key('minor-continue-button'));
    await tester.ensureVisible(continueButton);
    expect(tester.widget<FilledButton>(continueButton).onPressed, isNull);

    for (final key in const [
      Key('guardian-consent-checkbox'),
      Key('organisation-permission-checkbox'),
      Key('privacy-notice-read-checkbox'),
    ]) {
      final checkbox = find.byKey(key);
      await tester.scrollUntilVisible(checkbox, 300);
      await tester.pumpAndSettle();
      await tester.tap(checkbox);
      await tester.pumpAndSettle();
    }

    await tester.scrollUntilVisible(continueButton, 300);
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(continueButton).onPressed, isNotNull);
    await tester.tap(continueButton);
    await tester.pumpAndSettle();

    expect(find.text('Analyse tennis movement'), findsOneWidget);
  });
}
