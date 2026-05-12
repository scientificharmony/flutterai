import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/alert_model.dart';
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
          'device-id': 'demo-device-uuid',
        },
        body: jsonEncode({'mission': _missionController.text.trim()}),
      );

      if (!mounted) return;

      if (res.statusCode == 200) {
        final data = jsonDecode(res.body) as Map<String, dynamic>;
        final status = data['status'] as String;

        if (status == 'no_signal') {
          setState(() => _errorMessage = data['message'] as String?);
          return;
        }

        final alert = TradeAlert.fromJson(
            data['alert'] as Map<String, dynamic>);
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => AlertDetailScreen(alertId: alert.id),
          ),
        );
      } else if (res.statusCode == 429) {
        setState(() => _errorMessage =
            'Daily AI budget reached.\nClaude scans are paused today to control API costs.\nFormula-only checks can still run.');
      } else if (res.statusCode == 503) {
        setState(() => _errorMessage =
            'Unable to verify account balance. Scan blocked for safety.');
      } else {
        final detail = jsonDecode(res.body)['detail'] as String? ?? 'Unknown error';
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
      appBar: AppBar(title: const Text('Manual Scan')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Describe your investment goal and the scanner will search '
              'the default watchlist for matching setups.',
              style: TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _missionController,
              decoration: const InputDecoration(
                labelText: 'Mission',
                hintText: 'e.g. Find a defensive stock under £50',
                border: OutlineInputBorder(),
              ),
              maxLines: 3,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _isLoading ? null : _scan,
              style: ElevatedButton.styleFrom(padding: const EdgeInsets.all(16)),
              child: _isLoading
                  ? const CircularProgressIndicator()
                  : const Text('Run Scan', style: TextStyle(fontSize: 18)),
            ),
            if (_errorMessage != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.orange[50],
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange[300]!),
                ),
                child: Text(_errorMessage!,
                    style: const TextStyle(color: Colors.orange)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
