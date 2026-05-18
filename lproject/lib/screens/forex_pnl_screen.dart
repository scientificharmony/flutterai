import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';

class ForexPnlScreen extends StatefulWidget {
  const ForexPnlScreen({super.key});

  @override
  State<ForexPnlScreen> createState() => _ForexPnlScreenState();
}

class _ForexPnlScreenState extends State<ForexPnlScreen> {
  ForexPnlSummary? _summary;
  bool _loading = true;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.forexPnlSummary),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        setState(() => _summary = ForexPnlSummary.fromJson(jsonDecode(res.body) as Map<String, dynamic>));
      } else {
        setState(() => _error = 'Failed to load P&L (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Backend unavailable.');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('P&L SUMMARY', style: GoogleFonts.orbitron(fontWeight: FontWeight.w700, fontSize: 15)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, size: 20), onPressed: _load, tooltip: 'Refresh'),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: AppColors.cyan,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator(color: AppColors.cyan));
    if (_error != null) {
      return ListView(padding: const EdgeInsets.all(18), children: [
        const Icon(Icons.error_outline, color: AppColors.pink, size: 44),
        const SizedBox(height: 12),
        Text(_error!, textAlign: TextAlign.center, style: GoogleFonts.dmSans(color: AppColors.textMuted)),
      ]);
    }
    final s = _summary;
    if (s == null) return const SizedBox.shrink();

    if (s.totalClosed == 0) {
      return ListView(padding: const EdgeInsets.all(18), children: [
        const Icon(Icons.bar_chart, color: AppColors.textMuted, size: 44),
        const SizedBox(height: 12),
        Text('No closed trades yet.', textAlign: TextAlign.center,
            style: GoogleFonts.dmSans(color: AppColors.textMuted)),
        const SizedBox(height: 6),
        Text('${s.openCount} position${s.openCount == 1 ? '' : 's'} currently open.',
            textAlign: TextAlign.center,
            style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
      ]);
    }

    final pnlColor = s.totalRealisedPnl >= 0 ? AppColors.green : AppColors.pink;

    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 32),
      children: [
        // Total P&L hero
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: pnlColor.withValues(alpha: 0.35)),
          ),
          child: Column(
            children: [
              Text('Total realised P&L',
                  style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 13)),
              const SizedBox(height: 8),
              Text('£${s.totalRealisedPnl.toStringAsFixed(2)}',
                  style: GoogleFonts.orbitron(
                      color: pnlColor, fontSize: 32, fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text('${s.openCount} open · ${s.totalClosed} closed',
                  style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
            ],
          ),
        ),
        const SizedBox(height: 14),

        // Win/Loss stats
        Row(
          children: [
            Expanded(child: _StatCard(label: 'Win rate', value: '${s.winRate.toStringAsFixed(0)}%',
                color: s.winRate >= 50 ? AppColors.green : AppColors.pink)),
            const SizedBox(width: 10),
            Expanded(child: _StatCard(label: 'Wins', value: '${s.totalWins}', color: AppColors.green)),
            const SizedBox(width: 10),
            Expanded(child: _StatCard(label: 'Losses', value: '${s.totalLosses}', color: AppColors.pink)),
          ],
        ),
        const SizedBox(height: 10),

        // Avg win/loss
        Row(
          children: [
            Expanded(child: _StatCard(label: 'Avg win', value: '£${s.avgWin.toStringAsFixed(2)}',
                color: AppColors.green)),
            const SizedBox(width: 10),
            Expanded(child: _StatCard(label: 'Avg loss', value: '£${s.avgLoss.toStringAsFixed(2)}',
                color: AppColors.pink)),
            const SizedBox(width: 10),
            Expanded(child: _StatCard(
                label: 'Expectancy',
                value: _expectancy(s),
                color: _expectancyValue(s) >= 0 ? AppColors.green : AppColors.pink)),
          ],
        ),
        const SizedBox(height: 10),

        // Best / worst trade
        Row(
          children: [
            if (s.bestTradePnl != null)
              Expanded(child: _StatCard(
                  label: 'Best trade', value: '£${s.bestTradePnl!.toStringAsFixed(2)}',
                  color: AppColors.green)),
            if (s.bestTradePnl != null) const SizedBox(width: 10),
            if (s.worstTradePnl != null)
              Expanded(child: _StatCard(
                  label: 'Worst trade', value: '£${s.worstTradePnl!.toStringAsFixed(2)}',
                  color: AppColors.pink)),
          ],
        ),
        if (s.bestPair != null) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: AppColors.cyan.withValues(alpha: 0.25)),
            ),
            child: Row(
              children: [
                const Icon(Icons.emoji_events, color: AppColors.cyan, size: 20),
                const SizedBox(width: 10),
                Text('Best performing pair: ',
                    style: GoogleFonts.dmSans(color: AppColors.textMuted)),
                Text(s.bestPair!,
                    style: GoogleFonts.orbitron(color: AppColors.cyan, fontWeight: FontWeight.w700, fontSize: 13)),
              ],
            ),
          ),
        ],
      ],
    );
  }

  double _expectancyValue(ForexPnlSummary s) {
    if (s.totalClosed == 0) return 0;
    return (s.winRate / 100 * s.avgWin) + ((1 - s.winRate / 100) * s.avgLoss);
  }

  String _expectancy(ForexPnlSummary s) {
    final v = _expectancyValue(s);
    return '£${v.toStringAsFixed(2)}';
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatCard({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        children: [
          Text(label, style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 11)),
          const SizedBox(height: 6),
          Text(value,
              style: GoogleFonts.dmSans(color: color, fontWeight: FontWeight.w800, fontSize: 16)),
        ],
      ),
    );
  }
}

class ForexPnlSummary {
  final int totalClosed;
  final int totalWins;
  final int totalLosses;
  final double winRate;
  final double totalRealisedPnl;
  final double avgWin;
  final double avgLoss;
  final double? bestTradePnl;
  final double? worstTradePnl;
  final String? bestPair;
  final int openCount;

  const ForexPnlSummary({
    required this.totalClosed,
    required this.totalWins,
    required this.totalLosses,
    required this.winRate,
    required this.totalRealisedPnl,
    required this.avgWin,
    required this.avgLoss,
    required this.bestTradePnl,
    required this.worstTradePnl,
    required this.bestPair,
    required this.openCount,
  });

  factory ForexPnlSummary.fromJson(Map<String, dynamic> json) => ForexPnlSummary(
        totalClosed: json['total_closed'] as int,
        totalWins: json['total_wins'] as int,
        totalLosses: json['total_losses'] as int,
        winRate: (json['win_rate'] as num).toDouble(),
        totalRealisedPnl: (json['total_realised_pnl'] as num).toDouble(),
        avgWin: (json['avg_win'] as num).toDouble(),
        avgLoss: (json['avg_loss'] as num).toDouble(),
        bestTradePnl: (json['best_trade_pnl'] as num?)?.toDouble(),
        worstTradePnl: (json['worst_trade_pnl'] as num?)?.toDouble(),
        bestPair: json['best_pair'] as String?,
        openCount: json['open_count'] as int,
      );
}
