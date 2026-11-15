import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class AnalysisNotificationService {
  AnalysisNotificationService._();

  static final AnalysisNotificationService instance =
      AnalysisNotificationService._(); // This means we're using one shared instance of the notification service rather than creating a new notification manager every time an analysis finish

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  Future<void> initialise() async {
    const darwinSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    const settings = InitializationSettings(
      iOS: darwinSettings,
      macOS: darwinSettings,   // cofigured both to use both apple platforms
    );

    await _notifications.initialize(settings: settings);
  }

  Future<void> showAnalysisComplete() async { // generated "ANALYSIS COMPLETE"
    const details = NotificationDetails(
      iOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
      macOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
    );

    await _notifications.show(
      id: 1001,
      title: 'Analysis Complete',
      body: 'Your player movement analysis is ready to view.',
      notificationDetails: details,
    );
  }
}
