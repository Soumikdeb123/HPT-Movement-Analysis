import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

enum AnalysisNotice {
  validating('Checking video', null, ongoing: true),
  processing('Analyzing...', null, ongoing: true),
  completed('Analysis complete.', null),
  failed('Analysis failed.', null);

  const AnalysisNotice(this.title, this.body, {this.ongoing = false});
  final String title;
  final String? body;
  final bool ongoing;
}

class AnalysisNotifications {
  static const _channel = MethodChannel('hpt/analysis_notifications');

  static void show(AnalysisNotice notice) {
    unawaited(_invoke('show', {
      'title': notice.title,
      'body': notice.body,
      'ongoing': notice.ongoing,
      'start': notice == AnalysisNotice.validating,
    }));
  }

  static void clearProgress() => unawaited(_invoke('clearProgress'));

  static Future<void> _invoke(String method, [Map<String, Object?>? data]) async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return;
    try {
      await _channel.invokeMethod<void>(method, data);
    } on MissingPluginException {
      // Widget tests can run without an Android activity.
    } on PlatformException catch (error) {
      debugPrint('Analysis notification ($method): ${error.code}');
    }
  }
}
