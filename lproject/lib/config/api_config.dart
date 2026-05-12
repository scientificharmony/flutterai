class ApiConfig {
  // Defaults to localhost for safe desktop/simulator development.
  // Physical phone testing: pass --dart-define=API_BASE_URL=http://YOUR_PC_IP:8000.
  // Android emulator: use http://10.0.2.2:8000.
  // iOS simulator: use http://127.0.0.1:8000.
  static const bool hasExplicitBaseUrl = bool.hasEnvironment('API_BASE_URL');

  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const String scanMarket            = "$baseUrl/scan";
  static const String alerts                = "$baseUrl/alerts";
  static const String registerToken         = "$baseUrl/notifications/register-token";
  static const String health                = "$baseUrl/health";
  static const String performanceSummary    = "$baseUrl/test/performance-summary";
}
