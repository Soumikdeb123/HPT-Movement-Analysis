import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/analysis/views/analysis_page.dart';
import 'features/auth/repositories/auth_repository.dart';
import 'features/auth/views/auth_page.dart';
import 'features/consent/views/privacy_consent_gate.dart';

class HptApp extends StatefulWidget {
  const HptApp({super.key, this.authRepository});
  final AuthRepository? authRepository;
  @override
  State<HptApp> createState() => _HptAppState();
}

class _HptAppState extends State<HptApp> {
  bool _signedIn = false;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'HPT Player Analysis',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light,
    home: PrivacyConsentGate(
      child: _signedIn
          ? AnalysisPage(
              onSignOut: () {
                AuthRepository.token = null;
                AuthRepository.userEmail = null;
                setState(() => _signedIn = false);
              },
            )
          : AuthPage(
              repository: widget.authRepository,
              onSignedIn: () => setState(() => _signedIn = true),
            ),
    ),
  );
}
