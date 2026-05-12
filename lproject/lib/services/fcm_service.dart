import 'dart:convert';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import 'device_service.dart';

// Top-level handler required by Firebase for background messages
@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  // Message handled in background — navigation happens on tap in main isolate
}

class FcmService {
  FcmService._();
  static final FcmService instance = FcmService._();

  final _messaging = FirebaseMessaging.instance;
  final _localNotifications = FlutterLocalNotificationsPlugin();

  // Callback set by the app to navigate on notification tap
  void Function(String alertId)? onAlertTap;

  Future<void> init() async {
    // Request permission (iOS)
    await _messaging.requestPermission(alert: true, badge: true, sound: true);

    // Local notifications channel (Android)
    const androidChannel = AndroidNotificationChannel(
      'trade_alerts',
      'Trade Alerts',
      description: 'AI-generated market setup notifications',
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(androidChannel);

    await _localNotifications.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
      onDidReceiveNotificationResponse: (details) {
        final payload = details.payload;
        if (payload != null) {
          final data = jsonDecode(payload) as Map<String, dynamic>;
          final alertId = data['alert_id'] as String?;
          if (alertId != null) onAlertTap?.call(alertId);
        }
      },
    );

    FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);

    // Foreground messages — show local notification
    FirebaseMessaging.onMessage.listen((message) {
      final notification = message.notification;
      if (notification != null) {
        _localNotifications.show(
          notification.hashCode,
          notification.title,
          notification.body,
          NotificationDetails(
            android: AndroidNotificationDetails(
              'trade_alerts',
              'Trade Alerts',
              channelDescription: 'AI-generated market setup notifications',
              importance: Importance.high,
              priority: Priority.high,
            ),
          ),
          payload: jsonEncode(message.data),
        );
      }
    });

    // App opened from notification tap
    FirebaseMessaging.onMessageOpenedApp.listen((message) {
      final alertId = message.data['alert_id'] as String?;
      if (alertId != null) onAlertTap?.call(alertId);
    });

    // Register token with backend
    final token = await _messaging.getToken();
    if (token != null) await _registerToken(token);

    _messaging.onTokenRefresh.listen(_registerToken);
  }

  Future<void> _registerToken(String token) async {
    try {
      await http.post(
        Uri.parse(ApiConfig.registerToken),
        headers: {
          'Content-Type': 'application/json',
          'device-id': DeviceService.instance.deviceId,
        },
        body: jsonEncode({'token': token, 'platform': DeviceService.instance.platform}),
      );
    } catch (_) {
      // Non-fatal — will retry on next token refresh
    }
  }
}
