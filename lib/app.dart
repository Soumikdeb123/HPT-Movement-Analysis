import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/analysis/views/analysis_page.dart';

class HptApp extends StatelessWidget {
  const HptApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'HPT Player Analysis',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const AnalysisPage(),
    );
  }
}
