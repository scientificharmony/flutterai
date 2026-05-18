import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';
import 'forex_lab_screen.dart' show ForexEntryAlert; // reuse model + dialog helpers live there

class ForexEntryAlertReviewScreen extends StatefulWidget {
  final String alertId;

  const ForexEntryAlertReviewScreen({super.key, required this.alertId});

  @override
  State<ForexEntryAlertReviewScreen> createState() => _ForexEntryAlertReviewScreenState();
}

class _ForexEntryAlertReviewScreenState extends State<ForexEntryAlertReviewScreen> {
  ForexEntryAlert? _alert;
  bool _loading = true;
  bool _busy = false;
  String? _error;
  String? _executionError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.forexEntryAlert(widget.alertId)),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() {
          _alert = ForexEntryAlert.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
        });
      } else {
        setState(() => _error = 'Alert not found (${res.statusCode}).');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Forex backend unavailable.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _decline() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final res = await http.post(
        Uri.parse(ApiConfig.forexDeclineEntryAlert(widget.alertId)),
        headers: {'device-id': DeviceService.instance.deviceId, 'Content-Type': 'application/json'},
        body: jsonEncode({}),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Declined.')));
        await _load();
      } else {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Could not decline (${res.statusCode}).')));
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Forex backend unavailable.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _execute() async {
    if (_alert == null || _busy) return;
    setState(() => _busy = true);
    try {
      // One-tap execute uses the "custom" endpoint so we can keep a consistent
      // request shape and later allow edits without adding new endpoint.
      final body = {
        'size': 0.1,
        'stop_loss': _alert!.stopLoss,
        'take_profit': _alert!.takeProfit,
      };
      final res = await http.post(
        Uri.parse(ApiConfig.forexExecuteEntryAlertCustom(widget.alertId)),
        headers: {'device-id': DeviceService.instance.deviceId, 'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() => _executionError = null);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${_alert!.pair} demo trade placed and tracked.')),
        );
        Navigator.of(context).pop(); // back to wherever the user came from
      } else {
        String message = 'Could not place IG demo trade (${res.statusCode}).';
        try {
          final decoded = jsonDecode(res.body) as Map<String, dynamic>;
          message = decoded['detail'] as String? ?? message;
        } catch (_) {}
        setState(() => _executionError = message);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _executionError = 'Forex backend unavailable.');
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Forex backend unavailable.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('FOREX ALERT',
            style: GoogleFonts.orbitron(
                color: AppColors.cyan, fontWeight: FontWeight.w700, fontSize: 15)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, size: 20),
            tooltip: 'Refresh',
            onPressed: _load,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(14),
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: AppColors.cyan))
            : (_error != null)
                ? _InlineError(message: _error!, onRetry: _load)
                : _AlertBody(
                    alert: _alert!,
                    busy: _busy,
                    executionError: _executionError,
                    onExecute: _execute,
                    onDecline: _decline,
                  ),
      ),
    );
  }
}

class _AlertBody extends StatelessWidget {
  final ForexEntryAlert alert;
  final bool busy;
  final String? executionError;
  final VoidCallback onExecute;
  final VoidCallback onDecline;

  const _AlertBody({
    required this.alert,
    required this.busy,
    required this.onExecute,
    required this.onDecline,
    this.executionError,
  });

  @override
  Widget build(BuildContext context) {
    final color = alert.direction == 'LONG' ? AppColors.green : AppColors.pink;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: color.withValues(alpha: 0.35)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${alert.pair}  ${alert.direction}',
                  style: GoogleFonts.orbitron(
                      color: AppColors.textPrimary, fontSize: 14, fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              Text('Strength ${alert.strength}/100',
                  style: GoogleFonts.dmSans(color: AppColors.textMuted)),
              const SizedBox(height: 12),
              _RowLine(label: 'Entry', value: alert.entryPrice.toStringAsFixed(5)),
              if (alert.currentPrice != null)
                _RowLine(
                  label: 'Now',
                  value: alert.currentPrice!.toStringAsFixed(5),
                  valueColor: alert.currentPrice! > alert.entryPrice
                      ? (alert.direction == 'LONG' ? AppColors.green : AppColors.pink)
                      : (alert.direction == 'LONG' ? AppColors.pink : AppColors.green),
                ),
              _RowLine(label: 'Stop', value: alert.stopLoss.toStringAsFixed(5)),
              _RowLine(label: 'Target', value: alert.takeProfit.toStringAsFixed(5)),
            ],
          ),
        ),
        const SizedBox(height: 14),
        if (alert.declined)
          Text('Declined', style: GoogleFonts.dmSans(color: AppColors.textMuted)),
        if (executionError != null) ...[
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.pink.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(executionError!,
                style: GoogleFonts.dmSans(color: AppColors.pink, fontSize: 13)),
          ),
        ],
        const Spacer(),
        Builder(builder: (context) {
          final expired = DateTime.now().toUtc().difference(alert.createdAt.toUtc()).inHours >= 2;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (expired)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    'Setup expired — alert is over 2 hours old. Check current price before trading.',
                    style: GoogleFonts.dmSans(color: AppColors.pink, fontSize: 12),
                  ),
                ),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: busy ? null : onDecline,
                      child: const Text('Decline'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton(
                      onPressed: (busy || alert.declined || expired) ? null : onExecute,
                      style: FilledButton.styleFrom(backgroundColor: expired ? AppColors.border : color),
                      child: Text(expired ? 'Expired' : 'Execute trade'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                'If the market moved too far from the alert entry, Hey Jimmy will block execution.',
                style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12),
              ),
            ],
          );
        }),
      ],
    );
  }
}

class _RowLine extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _RowLine({required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          SizedBox(width: 64, child: Text(label, style: GoogleFonts.dmSans(color: AppColors.textMuted))),
          Expanded(child: Text(value, style: GoogleFonts.dmSans(color: valueColor ?? AppColors.textPrimary))),
        ],
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _InlineError({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(message, style: GoogleFonts.dmSans(color: AppColors.textMuted)),
          const SizedBox(height: 10),
          FilledButton(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}

