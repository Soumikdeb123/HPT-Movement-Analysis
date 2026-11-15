import 'package:flutter/material.dart';

import 'app.dart';
import 'features/analysis/services/analysis_notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await AnalysisNotificationService.instance.initialise();

  runApp(const HptApp());
}