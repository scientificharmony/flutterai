import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';

class CfdLabScreen extends StatefulWidget {
  const CfdLabScreen({super.key});

  @override
  State<CfdLabScreen> createState() => _CfdLabScreenState();
}

class _CfdLabScreenState extends State<CfdLabScreen> {
  CfdSummary? _summary;
  bool _loading = true;
  String? _error;
  Timer? _autoRefreshTimer;

  @override
  void initState() {
    super.initState();
    _loadSummary();
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _loadSummary());
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadSummary() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.cfdSummary),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        setState(() => _summary = CfdSummary.fromJson(jsonDecode(res.body) as Map<String, dynamic>));
      } else {
        setState(() => _error = 'CFD Lab unavailable (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Connection failed. Ensure backend is running.');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('CFD LAB', style: GoogleFonts.orbitron(fontWeight: FontWeight.w700)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadSummary,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: RefreshIndicator(
        color: AppColors.orange,
        backgroundColor: AppColors.surface,
        onRefresh: _loadSummary,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: AppColors.orange));
    }
    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(18),
        children: [
          const Icon(Icons.error_outline, color: AppColors.pink, size: 44),
          const SizedBox(height: 12),
          Text(_error!, textAlign: TextAlign.center, style: GoogleFonts.dmSans(color: AppColors.textMuted)),
        ],
      );
    }
    final summary = _summary;
    if (summary == null) return const SizedBox.shrink();
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 32),
      children: [
        _Header(summary: summary),
        const SizedBox(height: 16),
        Text('Practice signals', style: GoogleFonts.orbitron(color: AppColors.textPrimary, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        ...summary.signals.map((signal) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _CfdSignalCard(signal: signal),
            )),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  final CfdSummary summary;

  const _Header({required this.summary});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(summary.connected ? Icons.link : Icons.link_off, color: summary.connected ? AppColors.green : AppColors.orange),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  summary.connected ? '${summary.provider.toUpperCase()} demo connected' : 'No CFD broker connected',
                  style: GoogleFonts.dmSans(color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 15),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Practice-only. £${summary.riskAmount.toStringAsFixed(0)} risk guide per setup. Manual entry only until CFD Level 2 is built.',
            style: GoogleFonts.dmSans(color: AppColors.textMuted, height: 1.35),
          ),
        ],
      ),
    );
  }
}

class _CfdSignalCard extends StatelessWidget {
  final CfdSignal signal;

  const _CfdSignalCard({required this.signal});

  @override
  Widget build(BuildContext context) {
    final actionColor = switch (signal.direction) {
      'LONG' => AppColors.green,
      'SHORT' => AppColors.pink,
      _ => AppColors.orange,
    };
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: actionColor.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(signal.market,
                    style: GoogleFonts.orbitron(color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 14)),
              ),
              _Badge(label: signal.direction, color: actionColor),
              const SizedBox(width: 8),
              Text('${signal.strength}/100', style: GoogleFonts.dmSans(color: actionColor, fontWeight: FontWeight.w800)),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _Metric(label: 'Entry', value: signal.entry.toStringAsFixed(2)),
              _Metric(label: 'Stop', value: signal.stopLoss.toStringAsFixed(2)),
              _Metric(label: 'Target', value: signal.takeProfit.toStringAsFixed(2)),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _Metric(label: 'Risk', value: '£${signal.riskAmount.toStringAsFixed(0)}'),
              _Metric(label: 'Size guide', value: signal.contractSize.toStringAsFixed(1)),
              _Metric(label: 'R:R', value: signal.riskReward.toStringAsFixed(1)),
            ],
          ),
          const SizedBox(height: 12),
          Text(signal.rationale, style: GoogleFonts.dmSans(color: AppColors.textMuted, height: 1.35)),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;

  const _Metric({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
          const SizedBox(height: 4),
          Text(value, style: GoogleFonts.dmSans(color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 15)),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;

  const _Badge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(label, style: GoogleFonts.dmSans(color: color, fontWeight: FontWeight.w700, fontSize: 11)),
    );
  }
}

class CfdSummary {
  final String provider;
  final bool connected;
  final double riskAmount;
  final List<CfdSignal> signals;

  CfdSummary({
    required this.provider,
    required this.connected,
    required this.riskAmount,
    required this.signals,
  });

  factory CfdSummary.fromJson(Map<String, dynamic> json) {
    return CfdSummary(
      provider: json['provider'] as String? ?? 'mock',
      connected: json['connected'] as bool? ?? false,
      riskAmount: (json['risk_amount'] as num?)?.toDouble() ?? 0,
      signals: ((json['signals'] as List?) ?? [])
          .map((item) => CfdSignal.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CfdSignal {
  final String market;
  final String direction;
  final int strength;
  final double entry;
  final double stopLoss;
  final double takeProfit;
  final double riskReward;
  final double riskAmount;
  final double contractSize;
  final String rationale;

  CfdSignal({
    required this.market,
    required this.direction,
    required this.strength,
    required this.entry,
    required this.stopLoss,
    required this.takeProfit,
    required this.riskReward,
    required this.riskAmount,
    required this.contractSize,
    required this.rationale,
  });

  factory CfdSignal.fromJson(Map<String, dynamic> json) {
    return CfdSignal(
      market: json['market'] as String? ?? '',
      direction: json['direction'] as String? ?? 'NO_TRADE',
      strength: json['strength'] as int? ?? 0,
      entry: (json['entry'] as num?)?.toDouble() ?? 0,
      stopLoss: (json['stop_loss'] as num?)?.toDouble() ?? 0,
      takeProfit: (json['take_profit'] as num?)?.toDouble() ?? 0,
      riskReward: (json['risk_reward'] as num?)?.toDouble() ?? 0,
      riskAmount: (json['risk_amount'] as num?)?.toDouble() ?? 0,
      contractSize: (json['contract_size'] as num?)?.toDouble() ?? 0,
      rationale: json['rationale'] as String? ?? '',
    );
  }
}
