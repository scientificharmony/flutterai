class ApiConfig {
  // Private phone testing currently targets the nginx-backed server.
  // Local development: pass --dart-define=API_BASE_URL=http://127.0.0.1:8000.
  // Android emulator: use http://10.0.2.2:8000.
  // iOS simulator: use http://127.0.0.1:8000.
  static const String privateServerBaseUrl = 'http://172.237.116.65';
  static const bool hasExplicitBaseUrl = bool.hasEnvironment('API_BASE_URL');

  static String get defaultBaseUrl {
    return privateServerBaseUrl;
  }

  static final String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: defaultBaseUrl,
  );

  static final String scanMarket            = "$baseUrl/scan";
  static final String alerts                = "$baseUrl/alerts";
  static final String holdings              = "$baseUrl/holdings";
  static final String registerToken         = "$baseUrl/notifications/register-token";
  static final String health                = "$baseUrl/health";
  static final String performanceSummary    = "$baseUrl/test/performance-summary";
  static final String pieDeploy             = "$baseUrl/pie/deploy";
  static final String forexSummary          = "$baseUrl/forex/summary";
  static final String forexScan             = "$baseUrl/forex/scan";
  static final String forexEntryAlerts      = "$baseUrl/forex/entry-alerts";
  static String forexEntryAlert(String alertId) => "$baseUrl/forex/entry-alerts/$alertId";
  static String forexExecuteEntryAlert(String alertId) => "$baseUrl/forex/entry-alerts/$alertId/execute-demo";
  static String forexExecuteEntryAlertCustom(String alertId) =>
      "$baseUrl/forex/entry-alerts/$alertId/execute-demo-custom";
  static String forexDeclineEntryAlert(String alertId) => "$baseUrl/forex/entry-alerts/$alertId/decline";
  static final String forexPositions        = "$baseUrl/forex/positions";
  static final String cfdSummary            = "$baseUrl/cfd/summary";
  static final String cfdScan               = "$baseUrl/cfd/scan";
}
