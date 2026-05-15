import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'theme/app_theme.dart';
import 'screens/alert_detail_screen.dart';
import 'screens/forex_entry_alert_review_screen.dart';
import 'screens/forex_lab_screen.dart';
import 'screens/home_screen.dart';
import 'services/device_service.dart';
import 'services/fcm_service.dart';

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

  @override
  void initState() {
    super.initState();
    if (AppStartupConfig.enableFirebase) {
      _initFcm();
    }
  }

  void _initFcm() {
    FcmService.instance.onNotificationTap = (data) {
      final alertId = data['alert_id'] as String?;
      if (alertId == null) return;
      if (data['type'] == 'forex_entry_alert') {
        _navigatorKey.currentState?.push(
          MaterialPageRoute(
            builder: (_) => ForexEntryAlertReviewScreen(alertId: alertId),
          ),
        );
        return;
      }
      _navigatorKey.currentState?.push(
        MaterialPageRoute(
          builder: (_) => AlertDetailScreen(alertId: alertId),
        ),
      );
    };
    FcmService.instance.init();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: 'Hey Jimmy',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const HomeScreen(),
    );
  }
}
