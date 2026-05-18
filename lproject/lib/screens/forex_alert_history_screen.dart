import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';
import 'forex_lab_screen.dart' show ForexEntryAlert;

class ForexAlertHistoryScreen extends StatefulWidget {
  const ForexAlertHistoryScreen({super.key});

  @override
  State<ForexAlertHistoryScreen> createState() => _ForexAlertHistoryScreenState();
}

class _ForexAlertHistoryScreenState extends State<ForexAlertHistoryScreen> {
  List<ForexEntryAlert> _alerts = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.forexAlertHistory),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List<dynamic>;
        setState(() {
          _alerts = list.map((e) => ForexEntryAlert.fromJson(e as Map<String, dynamic>)).toList();
        });
      } else {
        setState(() => _error = 'Could not load history (${res.statusCode}).');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Backend unavailable.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('ALERT HISTORY',
            style: GoogleFonts.orbitron(
                color: AppColors.cyan, fontWeight: FontWeight.w700, fontSize: 15)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, size: 20), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.cyan))
          : _error != null
              ? Center(child: Text(_error!, style: GoogleFonts.dmSans(color: AppColors.textMuted)))
              : _alerts.isEmpty
                  ? Center(
                      child: Text('No alerts yet.',
                          style: GoogleFonts.dmSans(color: AppColors.textMuted)))
                  : ListView.separated(
                      padding: const EdgeInsets.all(14),
                      itemCount: _alerts.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (_, i) => _AlertHistoryTile(alert: _alerts[i]),
                    ),
    );
  }
}

class _AlertHistoryTile extends StatelessWidget {
  final ForexEntryAlert alert;
  const _AlertHistoryTile({required this.alert});

  @override
  Widget build(BuildContext context) {
    final color = alert.direction == 'LONG' ? AppColors.green : AppColors.pink;
    final expired = DateTime.now().toUtc().difference(alert.createdAt.toUtc()).inHours >= 2;

    String statusLabel;
    Color statusColor;
    if (alert.tracked) {
      statusLabel = 'Executed';
      statusColor = AppColors.green;
    } else if (alert.declined) {
      statusLabel = 'Declined';
      statusColor = AppColors.textMuted;
    } else if (expired) {
      statusLabel = 'Expired';
      statusColor = AppColors.textMuted;
    } else {
      statusLabel = 'Pending';
      statusColor = AppColors.cyan;
    }

    final time = alert.createdAt.toLocal();
    final timeStr = '${time.day}/${time.month} ${time.hour.toString().padLeft(2,'0')}:${time.minute.toString().padLeft(2,'0')}';

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('${alert.pair}  ${alert.direction}',
                        style: GoogleFonts.orbitron(
                            color: AppColors.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text('${alert.strength}/100',
                          style: GoogleFonts.dmSans(color: color, fontSize: 11)),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text('Entry ${alert.entryPrice.toStringAsFixed(5)}  •  $timeStr',
                    style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
              ],
            ),
          ),
          Text(statusLabel,
              style: GoogleFonts.dmSans(
                  color: statusColor, fontSize: 12, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
