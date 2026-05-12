import 'dart:io';
import 'package:device_info_plus/device_info_plus.dart';

class DeviceService {
  DeviceService._();
  static final DeviceService instance = DeviceService._();

  String _deviceId = 'unknown-device';
  String _platform = 'android';

  Future<void> init() async {
    final info = DeviceInfoPlugin();
    try {
      if (Platform.isAndroid) {
        final android = await info.androidInfo;
        _deviceId = android.id;
        _platform = 'android';
      } else if (Platform.isIOS) {
        final ios = await info.iosInfo;
        _deviceId = ios.identifierForVendor ?? 'unknown-ios';
        _platform = 'ios';
      }
    } catch (_) {
      // Keep defaults — non-fatal
    }
  }

  String get deviceId => _deviceId;
  String get platform => _platform;
}
