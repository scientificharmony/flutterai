import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/alert_model.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';
import 'alert_detail_screen.dart';

class MissionScreen extends StatefulWidget {
  const MissionScreen({super.key});

  @override
  State<MissionScreen> createState() => _MissionScreenState();
}

class _MissionScreenState extends State<MissionScreen> {
  final _missionController = TextEditingController();
  bool _isLoading = false;
  String? _errorMessage;

  static const _suggestions = [
    'Find a safer ETF for long-term growth',
    'Look for a tech stock under £200',
    'Find a defensive dividend stock',
    'Scan for momentum in clean energy',
  ];

  @override
  void dispose() {
    _missionController.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    if (_missionController.text.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final res = await http.post(
        Uri.parse(ApiConfig.scanMarket),
        headers: {
          'Content-Type': 'application/json',
          'device-id': DeviceService.instance.deviceId,
        },
        body: jsonEncode({'mission': _missionController.text.trim()}),
      );

      if (!mounted) return;

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final status = data['status'] as String;

        if (status == 'no_signal' || status == 'no_action' || status == 'no_alert') {
          setState(() => _errorMessage =
              data['message'] as String? ?? 'No actionable alert found.');
          return;
        }

        final alertJson = data['alert'] as Map<String, dynamic>?;
        if (alertJson == null) {
          setState(() => _errorMessage =
              data['message'] as String? ?? 'No actionable alert found.');
          return;
        }

        final alert = TradeAlert.fromJson(alertJson);
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => AlertDetailScreen(alertId: alert.id),
          ),
        );
      } else if (res.statusCode == 429) {
        setState(() => _errorMessage =
            'Daily AI budget reached.\nClaude scans are paused today to control API costs.');
      } else if (res.statusCode == 503) {
        setState(() => _errorMessage =
            'Unable to verify account balance. Scan blocked for safety.');
      } else {
        final detail =
            jsonDecode(res.body)['detail'] as String? ?? 'Unknown error';
        setState(() => _errorMessage = detail);
      }
    } catch (_) {
      setState(() =>
          _errorMessage = 'Connection failed. Ensure backend is running.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('SCAN MARKET',
            style: GoogleFonts.orbitron(
                color: AppColors.cyan, fontWeight: FontWeight.w600, fontSize: 14)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header block
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.radar, color: AppColors.orange, size: 20),
                      const SizedBox(width: 10),
                      Text('Mission Brief',
                          style: GoogleFonts.orbitron(
                              color: AppColors.orange,
                              fontWeight: FontWeight.w600,
                              fontSize: 13)),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Describe your investment goal. Jimmy will scan the watchlist and surface the strongest matching setup.',
                    style: GoogleFonts.dmSans(
                        color: AppColors.textMuted, fontSize: 13, height: 1.5),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Mission input
            TextField(
              controller: _missionController,
              style: GoogleFonts.dmSans(color: AppColors.textPrimary),
              decoration: InputDecoration(
                labelText: 'Your mission',
                hintText: 'e.g. Find a defensive stock under £50',
                hintStyle: GoogleFonts.dmSans(
                    color: AppColors.textMuted.withValues(alpha: 0.5)),
                prefixIcon: const Icon(Icons.search, color: AppColors.textMuted, size: 18),
              ),
              maxLines: 3,
              textInputAction: TextInputAction.done,
            ),

            const SizedBox(height: 14),

            // Quick suggestions
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _suggestions.map((s) => _SuggestionChip(
                label: s,
                onTap: () => setState(() => _missionController.text = s),
              )).toList(),
            ),

            const SizedBox(height: 24),

            // Scan button
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _scan,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.orange,
                  foregroundColor: Colors.black,
                  disabledBackgroundColor: AppColors.orange.withValues(alpha: 0.3),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  elevation: _isLoading ? 0 : 6,
                  shadowColor: AppColors.orange.withValues(alpha: 0.4),
                ),
                child: _isLoading
                    ? Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                color: Colors.black, strokeWidth: 2),
                          ),
                          const SizedBox(width: 12),
                          Text('Scanning…',
                              style: GoogleFonts.dmSans(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 15,
                                  color: Colors.black54)),
                        ],
                      )
                    : Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.bolt, size: 20),
                          const SizedBox(width: 8),
                          Text('Run Scan',
                              style: GoogleFonts.dmSans(
                                  fontWeight: FontWeight.w700, fontSize: 16)),
                        ],
                      ),
              ),
            ),

            // Error / no-action message
            if (_errorMessage != null) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: AppColors.orange.withValues(alpha: 0.07),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                      color: AppColors.orange.withValues(alpha: 0.3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline,
                        color: AppColors.orange, size: 18),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _errorMessage!,
                        style: GoogleFonts.dmSans(
                            color: AppColors.orange, fontSize: 13, height: 1.5),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }
}

class _SuggestionChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _SuggestionChip({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surfaceHigh,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(label,
            style: GoogleFonts.dmSans(
                color: AppColors.textMuted, fontSize: 11)),
      ),
    );
  }
}
