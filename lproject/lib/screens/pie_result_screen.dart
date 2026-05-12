import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import '../config/api_config.dart';
import '../models/pie_model.dart';

class PieResultScreen extends StatelessWidget {
  final PieBuildResult pie;
  const PieResultScreen({super.key, required this.pie});

  Future<void> _savePie(BuildContext context) async {
    if (!pie.executable) return;
    try {
      final slicesJson = pie.slices
          .map((s) => {
                'ticker': s.ticker,
                'name': s.name,
                'instrument_type': s.instrumentType,
                'market_theme': s.marketTheme,
                'allocation_percent': s.allocationPercent,
                'amount': s.amount,
                'opportunity_score': s.opportunityScore,
                'opportunity_strength': s.opportunityStrength,
                'strength_label': s.strengthLabel,
                'rationale': s.rationale,
              })
          .toList();

      final res = await http.post(
        Uri.parse('${ApiConfig.baseUrl}/pie/save'),
        headers: {
          'Content-Type': 'application/json',
          'device-id': 'demo-device-uuid',
        },
        body: jsonEncode({
          'pie': {
            'pie_name': pie.pieName,
            'goal': pie.goal,
            'risk_level': pie.riskLevel,
            'total_amount': pie.totalAmount,
            'time_horizon': pie.timeHorizon,
            'slices': slicesJson,
            'overall_rationale': pie.overallRationale,
            'risk_note': pie.riskNote,
            'executable': pie.executable,
            'safety_flags': pie.safetyFlags,
            'warnings': pie.warnings,
            'data_freshness': {
              'status': pie.dataFreshness.status,
              'newest_data_timestamp': pie.dataFreshness.newestDataTimestamp,
              'oldest_allowed_timestamp': pie.dataFreshness.oldestAllowedTimestamp,
              'stale_tickers': pie.dataFreshness.staleTickers,
            },
            'market_data_timestamp': pie.marketDataTimestamp,
            'valid_until': pie.validUntil,
            'invest_only_verified': pie.investOnlyVerified,
            'all_slices_validated': pie.allSlicesValidated,
            'manual_execution_only': pie.manualExecutionOnly,
          }
        }),
      );

      if (!context.mounted) return;
      if (res.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Pie saved to history')),
        );
      } else {
        final detail = (jsonDecode(res.body))['detail'] as String? ?? 'Save failed.';
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(detail)));
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Save failed. Check connection.')),
        );
      }
    }
  }

  void _copySliceList(BuildContext context) {
    Clipboard.setData(ClipboardData(text: pie.toCopyText()));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Slice list copied to clipboard')),
    );
  }

  Future<void> _openT212(BuildContext context) async {
    if (!pie.executable) return;
    const url = 'https://www.trading212.com/';
    if (!await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication)) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open Trading 212')),
        );
      }
    }
  }

  String _formatTimestamp(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      return '${dt.day}/${dt.month}/${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Your Pie'),
        actions: [
          IconButton(
            icon: const Icon(Icons.save_outlined),
            tooltip: pie.executable ? 'Save Pie' : 'Cannot save non-executable Pie',
            onPressed: pie.executable ? () => _savePie(context) : null,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Non-executable warning banner
          if (!pie.executable)
            _WarningBanner(
              message: pie.safetyFlags.isNotEmpty
                  ? pie.safetyFlags.first
                  : 'This Pie cannot be executed. Review the safety flags below.',
            ),

          // Warnings (e.g. amount too low)
          if (pie.warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...pie.warnings.map((w) => _WarningBanner(message: w, isInfo: true)),
          ],

          if (!pie.executable) const SizedBox(height: 8),

          // Header
          _PieHeader(pie: pie),
          const SizedBox(height: 12),

          // Freshness metadata card
          _FreshnessCard(
            freshness: pie.dataFreshness,
            generatedAt: _formatTimestamp(pie.marketDataTimestamp),
            validUntil: _formatTimestamp(pie.validUntil),
          ),
          const SizedBox(height: 8),

          // Rationale
          if (pie.overallRationale.isNotEmpty) ...[
            _InfoCard(title: 'Strategy', body: pie.overallRationale),
            const SizedBox(height: 8),
          ],
          if (pie.riskNote.isNotEmpty)
            _InfoCard(
              title: 'Risk Note',
              body: pie.riskNote,
              titleColor: Colors.orange,
            ),

          // Safety flags
          if (pie.safetyFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...pie.safetyFlags.map((f) => _SafetyFlag(message: f)),
          ],

          if (pie.slices.isNotEmpty) ...[
            const SizedBox(height: 16),
            const Text('Slices',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 8),
            ...pie.slices.map((s) => _SliceCard(slice: s)),
          ],

          const SizedBox(height: 16),

          // Disclaimer
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Text(
              'This app does not create the Pie or place trades automatically. '
              'Review and create manually in Trading 212. '
              'You are responsible for all trading decisions.',
              style: TextStyle(fontSize: 11, color: Colors.grey),
              textAlign: TextAlign.center,
            ),
          ),

          const SizedBox(height: 16),

          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _copySliceList(context),
                  icon: const Icon(Icons.copy, size: 18),
                  label: const Text('Copy Slice List'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: pie.executable ? () => _savePie(context) : null,
                  icon: const Icon(Icons.save, size: 18),
                  label: const Text('Save Pie Idea'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: pie.executable ? () => _openT212(context) : null,
            icon: const Icon(Icons.open_in_new),
            label: const Text('Open Trading 212 to Create Pie'),
            style: ElevatedButton.styleFrom(
              backgroundColor: pie.executable ? Colors.green : Colors.grey,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.all(14),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _FreshnessCard extends StatelessWidget {
  final DataFreshness freshness;
  final String generatedAt;
  final String validUntil;
  const _FreshnessCard({
    required this.freshness,
    required this.generatedAt,
    required this.validUntil,
  });

  @override
  Widget build(BuildContext context) {
    final (color, icon, label) = switch (freshness.status) {
      'fresh' => (Colors.green, Icons.check_circle_outline, 'Data Fresh'),
      'stale' => (Colors.orange, Icons.warning_amber_outlined, 'Data Stale'),
      _ => (Colors.red, Icons.error_outline, 'Data Unavailable'),
    };

    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 16),
                const SizedBox(width: 6),
                Text(label,
                    style: TextStyle(
                        color: color,
                        fontWeight: FontWeight.bold,
                        fontSize: 13)),
              ],
            ),
            const SizedBox(height: 6),
            _FreshnessRow(label: 'Generated', value: generatedAt),
            _FreshnessRow(label: 'Valid until', value: validUntil),
            if (freshness.staleTickers.isNotEmpty)
              _FreshnessRow(
                  label: 'Stale tickers',
                  value: freshness.staleTickers.join(', ')),
          ],
        ),
      ),
    );
  }
}

class _FreshnessRow extends StatelessWidget {
  final String label;
  final String value;
  const _FreshnessRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        children: [
          SizedBox(
            width: 90,
            child: Text(label,
                style: TextStyle(fontSize: 11, color: Colors.grey[600])),
          ),
          Expanded(
            child: Text(value, style: const TextStyle(fontSize: 11)),
          ),
        ],
      ),
    );
  }
}

class _WarningBanner extends StatelessWidget {
  final String message;
  final bool isInfo;
  const _WarningBanner({required this.message, this.isInfo = false});

  @override
  Widget build(BuildContext context) {
    final color = isInfo ? Colors.blue : Colors.red;
    final icon = isInfo ? Icons.info_outline : Icons.block_outlined;
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 8),
          Expanded(
              child: Text(message,
                  style: TextStyle(fontSize: 13, color: color))),
        ],
      ),
    );
  }
}

class _PieHeader extends StatelessWidget {
  final PieBuildResult pie;
  const _PieHeader({required this.pie});

  @override
  Widget build(BuildContext context) {
    final riskColor = switch (pie.riskLevel) {
      'low' => Colors.green,
      'high' => Colors.red,
      _ => Colors.orange,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(pie.pieName,
                style: const TextStyle(
                    fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                _Badge(text: pie.riskLevel.toUpperCase(), color: riskColor),
                _Badge(
                    text: '${pie.slices.length} slices', color: Colors.blue),
                _Badge(
                    text: '£${pie.totalAmount.toStringAsFixed(2)}',
                    color: Colors.grey),
                if (!pie.executable)
                  _Badge(text: 'NOT EXECUTABLE', color: Colors.red),
                if (pie.investOnlyVerified)
                  _Badge(text: 'T212 Verified', color: Colors.green),
              ],
            ),
            if (pie.slices.isNotEmpty) ...[
              const SizedBox(height: 8),
              _AllocationBar(slices: pie.slices),
            ],
          ],
        ),
      ),
    );
  }
}

class _AllocationBar extends StatelessWidget {
  final List<PieSlice> slices;
  const _AllocationBar({required this.slices});

  static const _colors = [
    Colors.blue, Colors.green, Colors.orange, Colors.purple,
    Colors.teal, Colors.red, Colors.indigo, Colors.amber,
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: Row(
            children: slices.asMap().entries.map((e) {
              final color = _colors[e.key % _colors.length];
              return Flexible(
                flex: (e.value.allocationPercent * 10).round(),
                child: Container(height: 12, color: color),
              );
            }).toList(),
          ),
        ),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          runSpacing: 2,
          children: slices.asMap().entries.map((e) {
            final color = _colors[e.key % _colors.length];
            return Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                    width: 8, height: 8,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                const SizedBox(width: 4),
                Text('${e.value.ticker} ${e.value.allocationPercent.toStringAsFixed(1)}%',
                    style: const TextStyle(fontSize: 11)),
              ],
            );
          }).toList(),
        ),
      ],
    );
  }
}

class _SliceCard extends StatelessWidget {
  final PieSlice slice;
  const _SliceCard({required this.slice});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 56,
              child: Column(
                children: [
                  Text('${slice.allocationPercent.toStringAsFixed(1)}%',
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.bold)),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                    decoration: BoxDecoration(
                      color: slice.instrumentType == 'ETF'
                          ? Colors.blue[50]
                          : Colors.purple[50],
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(slice.instrumentType,
                        style: TextStyle(
                            fontSize: 9,
                            color: slice.instrumentType == 'ETF'
                                ? Colors.blue[700]
                                : Colors.purple[700])),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(slice.ticker,
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                      Text('£${slice.amount.toStringAsFixed(2)}',
                          style: const TextStyle(fontWeight: FontWeight.bold)),
                    ],
                  ),
                  Text(slice.name,
                      style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  const SizedBox(height: 4),
                  Text(slice.rationale,
                      style: const TextStyle(fontSize: 12)),
                  const SizedBox(height: 2),
                  Text(
                      'Opportunity Strength: ${slice.opportunityStrength}/100 (${slice.strengthLabel})',
                      style: TextStyle(
                          fontSize: 11, color: Colors.grey[600])),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final String title;
  final String body;
  final Color? titleColor;
  const _InfoCard({required this.title, required this.body, this.titleColor});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: titleColor ?? Colors.grey)),
            const SizedBox(height: 4),
            Text(body),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  const _Badge({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12)),
      child: Text(text,
          style: TextStyle(
              fontSize: 12, fontWeight: FontWeight.bold, color: color)),
    );
  }
}

class _SafetyFlag extends StatelessWidget {
  final String message;
  const _SafetyFlag({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.orange[50],
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.orange[300]!),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber, color: Colors.orange, size: 16),
          const SizedBox(width: 8),
          Expanded(
              child: Text(message,
                  style: const TextStyle(fontSize: 13, color: Colors.orange))),
        ],
      ),
    );
  }
}
