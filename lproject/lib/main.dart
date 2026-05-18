import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'theme/app_theme.dart';
import 'screens/alert_detail_screen.dart';
import 'screens/forex_entry_alert_review_screen.dart';
import 'screens/forex_lab_screen.dart';
import 'screens/home_screen.dart';
import 'screens/notification_debug_screen.dart';
import 'services/device_service.dart';
import 'services/fcm_service.dart';

final RouteObserver<ModalRoute<void>> routeObserver = RouteObserver<ModalRoute<void>>();

class AppStartupConfig {
  static const bool enableFirebase = bool.fromEnvironment(
    'ENABLE_FIREBASE',
    defaultValue: false,
  );
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await WakelockPlus.enable();
  await DeviceService.instance.init();
  if (AppStartupConfig.enableFirebase) {
    try {
      await Firebase.initializeApp();
    } catch (error) {
      debugPrint('Firebase initialization skipped: $error');
    }
  }
  runApp(const AITradingApp());
}

class AITradingApp extends StatefulWidget {
  const AITradingApp({super.key});

  @override
  State<AITradingApp> createState() => _AITradingAppState();
}

class _AITradingAppState extends State<AITradingApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  Map<String, dynamic>? _pendingNotificationTap;

  @override
  void initState() {
    super.initState();
    if (AppStartupConfig.enableFirebase) {
      _initFcm();
    }
  }

  void _initFcm() {
    FcmService.instance.onNotificationTap = (data) {
      _handleNotificationTap(data);
    };
    FcmService.instance.init();
  }

  void _handleNotificationTap(Map<String, dynamic> data) {
    debugPrint("Notification tap data: $data");
    final nav = _navigatorKey.currentState;
    if (nav == null) {
      // App launched from a tap before the Navigator is ready. Queue and replay after first frame.
      _pendingNotificationTap = data;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final pending = _pendingNotificationTap;
        _pendingNotificationTap = null;
        if (pending != null) _handleNotificationTap(pending);
      });
      return;
    }

    final alertId = data['alert_id'] as String?;
    if (alertId == null) {
      nav.push(MaterialPageRoute(builder: (_) => NotificationDebugScreen(data: data)));
      return;
    }
    if (data['type'] == 'forex_entry_alert') {
      nav.push(
        MaterialPageRoute(
          builder: (_) => ForexEntryAlertReviewScreen(alertId: alertId),
        ),
      );
      return;
    }
    // If we got here, we have an alert_id but no recognized type; show debug.
    if (data['type'] == null) {
      nav.push(MaterialPageRoute(builder: (_) => NotificationDebugScreen(data: data)));
      return;
    }
    nav.push(
      MaterialPageRoute(
        builder: (_) => AlertDetailScreen(alertId: alertId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: 'Hey Jimmy',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      navigatorObservers: [routeObserver],
      home: const ForexLabScreen(),
    );
  }
}
