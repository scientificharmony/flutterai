import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'screens/alert_detail_screen.dart';
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
    FcmService.instance.onAlertTap = (alertId) {
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
      title: 'Flutter AI',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
