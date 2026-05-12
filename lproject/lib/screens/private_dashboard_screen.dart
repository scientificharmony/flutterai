import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/alert_model.dart';

class PrivateDashboardScreen extends StatefulWidget {
  const PrivateDashboardScreen({super.key});

  @override
  State<PrivateDashboardScreen> createState() => _PrivateDashboardScreenState();
}

class _PrivateDashboardScreenState extends State<PrivateDashboardScreen> {
  _Summary? _data;
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
        Uri.parse(ApiConfig.performanceSummary),
        headers: {'device-id': 'demo-device-uuid'},
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() => _data = _Summary.fromJson(
            jsonDecode(res.body) as Map<String, dynamic>));
      } else {
        setState(() => _error = 'Error ${res.statusCode}');
      }
    } catch (e) {
      setState(() => _error = 'Connection failed');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Private Test Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) return Center(child: Text(_error!));
    if (_data == null) return const SizedBox.shrink();
    final d = _data!;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Budget card
        _SectionCard(
          title: 'Today\'s Budget',
          child: Column(
            children: [
              _MetricRow('Claude calls today', '${d.todayCalls} / 20'),
              _MetricRow('Alerts sent today', '${d.todayAlerts} / 5'),
              _MetricRow('Spent today', '£${d.todayCostGbp.toStringAsFixed(4)}'),
              _MetricRow('Budget remaining',
                  '£${d.budgetRemainingGbp.toStringAsFixed(4)}',
                  valueColor: d.budgetRemainingGbp < 0.20 ? Colors.red : Colors.green),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _SectionCard(
          title: 'Action Strength Bands',
          child: Column(
            children: [
              _MetricRow('Average 1h result', d.average1hResult != null ? '${d.average1hResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Average 4h result', d.average4hResult != null ? '${d.average4hResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Average 1d result', d.average1dResult != null ? '${d.average1dResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Average 5d result', d.average5dResult != null ? '${d.average5dResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Acted-on result', d.actedOnResult != null ? '${d.actedOnResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Ignored result', d.ignoredResult != null ? '${d.ignoredResult!.toStringAsFixed(2)}%' : '—'),
              _MetricRow('Best band', d.bestBand ?? '—', valueColor: Colors.green),
              _MetricRow('Worst band', d.worstBand ?? '—', valueColor: Colors.red),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Alert outcomes card
        _SectionCard(
          title: 'Signal Outcomes',
          child: Column(
            children: [
              _MetricRow('Total alerts', '${d.totalAlerts}'),
              _MetricRow('Took trade', '${d.tookTrade}', valueColor: Colors.green),
              _MetricRow('Ignored', '${d.ignored}', valueColor: Colors.grey),
              _MetricRow('Watching', '${d.watching}', valueColor: Colors.orange),
              _MetricRow('Unrecorded', '${d.unrecorded}'),
              if (d.winRatePct != null)
                _MetricRow('Win rate', '${d.winRatePct!.toStringAsFixed(1)}%',
                    valueColor: d.winRatePct! >= 50 ? Colors.green : Colors.red),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Performance card
        _SectionCard(
          title: 'Performance',
          child: Column(
            children: [
              if (d.avg1dPct != null)
                _MetricRow('Avg 1-day move', '${d.avg1dPct! >= 0 ? '+' : ''}${d.avg1dPct!.toStringAsFixed(2)}%',
                    valueColor: d.avg1dPct! >= 0 ? Colors.green : Colors.red),
              if (d.avg5dPct != null)
                _MetricRow('Avg 5-day move', '${d.avg5dPct! >= 0 ? '+' : ''}${d.avg5dPct!.toStringAsFixed(2)}%',
                    valueColor: d.avg5dPct! >= 0 ? Colors.green : Colors.red),
              _MetricRow('Realised P&L',
                  '£${d.realisedPnl.toStringAsFixed(2)}',
                  valueColor: d.realisedPnl >= 0 ? Colors.green : Colors.red),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Cost & net card
        _SectionCard(
          title: 'API Costs vs P&L',
          child: Column(
            children: [
              _MetricRow('Total Claude cost', '£${d.claudeCostGbp.toStringAsFixed(4)}'),
              _MetricRow('Market data cost', '£${d.marketDataCostGbp.toStringAsFixed(4)}'),
              const Divider(),
              _MetricRow('Net after API costs',
                  '£${d.netAfterCosts.toStringAsFixed(4)}',
                  valueColor: d.netAfterCosts >= 0 ? Colors.green : Colors.red,
                  bold: true),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Recent signals
        if (d.recentSignals.isNotEmpty) ...[
          const Text('Recent Signals',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 8),
          ...d.recentSignals.take(10).map((s) => _SignalRow(signal: s)),
        ],

        const SizedBox(height: 24),
      ],
    );
  }
}

// ── Data model (local, parsed from JSON) ─────────────────────────────────────

class _Summary {
  final int totalAlerts;
  final int tookTrade;
  final int ignored;
  final int watching;
  final int unrecorded;
  final double? winRatePct;
  final double? avg1dPct;
  final double? avg5dPct;
  final double realisedPnl;
  final double claudeCostGbp;
  final double marketDataCostGbp;
  final double netAfterCosts;
  final int todayCalls;
  final int todayAlerts;
  final double todayCostGbp;
  final double budgetRemainingGbp;
  final List<SignalOutcome> recentSignals;
  final double? average1hResult;
  final double? average4hResult;
  final double? average1dResult;
  final double? average5dResult;
  final double? actedOnResult;
  final double? ignoredResult;
  final String? bestBand;
  final String? worstBand;

  const _Summary({
    required this.totalAlerts,
    required this.tookTrade,
    required this.ignored,
    required this.watching,
    required this.unrecorded,
    this.winRatePct,
    this.avg1dPct,
    this.avg5dPct,
    required this.realisedPnl,
    required this.claudeCostGbp,
    required this.marketDataCostGbp,
    required this.netAfterCosts,
    required this.todayCalls,
    required this.todayAlerts,
    required this.todayCostGbp,
    required this.budgetRemainingGbp,
    required this.recentSignals,
    this.average1hResult,
    this.average4hResult,
    this.average1dResult,
    this.average5dResult,
    this.actedOnResult,
    this.ignoredResult,
    this.bestBand,
    this.worstBand,
  });

  factory _Summary.fromJson(Map<String, dynamic> j) {
    final today = j['today_usage'] as Map<String, dynamic>;
    return _Summary(
      totalAlerts: j['total_alerts'] as int,
      tookTrade: j['took_trade'] as int,
      ignored: j['ignored'] as int,
      watching: j['watching'] as int,
      unrecorded: j['unrecorded'] as int,
      winRatePct: (j['win_rate_pct'] as num?)?.toDouble(),
      avg1dPct: (j['avg_1d_pct'] as num?)?.toDouble(),
      avg5dPct: (j['avg_5d_pct'] as num?)?.toDouble(),
      realisedPnl: (j['total_realised_pnl'] as num).toDouble(),
      claudeCostGbp: (j['estimated_claude_cost_gbp'] as num).toDouble(),
      marketDataCostGbp: (j['estimated_market_data_cost_gbp'] as num).toDouble(),
      netAfterCosts: (j['net_after_api_costs'] as num).toDouble(),
      todayCalls: today['claude_calls'] as int,
      todayAlerts: today['alerts_sent'] as int,
      todayCostGbp: (today['estimated_cost_gbp'] as num).toDouble(),
      budgetRemainingGbp: (today['budget_remaining_gbp'] as num).toDouble(),
      recentSignals: (j['recent_signals'] as List)
          .map((s) => SignalOutcome.fromJson(s as Map<String, dynamic>))
          .toList(),
      average1hResult: (j['average_1h_result'] as num?)?.toDouble(),
      average4hResult: (j['average_4h_result'] as num?)?.toDouble(),
      average1dResult: (j['average_1d_result'] as num?)?.toDouble(),
      average5dResult: (j['average_5d_result'] as num?)?.toDouble(),
      actedOnResult: (j['acted_on_result'] as num?)?.toDouble(),
      ignoredResult: (j['ignored_result'] as num?)?.toDouble(),
      bestBand: j['best_performing_action_strength_band'] as String?,
      worstBand: j['worst_performing_action_strength_band'] as String?,
    );
  }
}

// ── Shared widgets ────────────────────────────────────────────────────────────

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;
  const _SectionCard({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    color: Colors.grey,
                    fontSize: 13)),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;
  final bool bold;
  const _MetricRow(this.label, this.value, {this.valueColor, this.bold = false});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(fontSize: 13, fontWeight: bold ? FontWeight.bold : FontWeight.normal)),
          Text(value,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: bold ? FontWeight.bold : FontWeight.w600,
                  color: valueColor)),
        ],
      ),
    );
  }
}

class _SignalRow extends StatelessWidget {
  final SignalOutcome signal;
  const _SignalRow({required this.signal});

  @override
  Widget build(BuildContext context) {
    final outcomeColor = switch (signal.outcome) {
      'took_trade' => Colors.green,
      'ignored' => Colors.grey,
      'watching' => Colors.orange,
      _ => Colors.grey[300]!,
    };
    final outcomeLabel = signal.outcome?.replaceAll('_', ' ') ?? '—';

    return Card(
      margin: const EdgeInsets.only(bottom: 6),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(signal.ticker,
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                      const SizedBox(width: 6),
                      _SmallBadge(signal.action,
                          color: signal.action == 'BUY_REVIEW'
                              ? Colors.green
                              : signal.action == 'REVIEW_SELL'
                                  ? Colors.red
                                  : Colors.orange),
                    ],
                  ),
                  Text(
                    'Action Strength ${signal.actionStrength}/100 · ${signal.actionLabel}',
                    style: const TextStyle(fontSize: 11, color: Colors.grey),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                _SmallBadge(outcomeLabel, color: outcomeColor),
                if (signal.realisedPnl != null)
                  Text(
                    '£${signal.realisedPnl!.toStringAsFixed(2)}',
                    style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: signal.realisedPnl! >= 0 ? Colors.green : Colors.red),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SmallBadge extends StatelessWidget {
  final String label;
  final Color color;
  const _SmallBadge(this.label, {required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8)),
      child: Text(label,
          style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: color)),
    );
  }
}
