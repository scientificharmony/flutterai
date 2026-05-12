import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import '../config/api_config.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';

class OpenPosition {
  final String id;
  final String ticker;
  final double entryPrice;
  final double amount;
  final double? peakPrice;
  final double? currentGainPct;
  final String status;
  final String? sellAlertId;
  final DateTime openedAt;
  final DateTime? closedAt;

  const OpenPosition({
    required this.id,
    required this.ticker,
    required this.entryPrice,
    required this.amount,
    this.peakPrice,
    this.currentGainPct,
    required this.status,
    this.sellAlertId,
    required this.openedAt,
    this.closedAt,
  });

  factory OpenPosition.fromJson(Map<String, dynamic> j) => OpenPosition(
        id: j['id'] as String,
        ticker: j['ticker'] as String,
        entryPrice: (j['entry_price'] as num).toDouble(),
        amount: (j['amount'] as num).toDouble(),
        peakPrice: (j['peak_price'] as num?)?.toDouble(),
        currentGainPct: (j['current_gain_pct'] as num?)?.toDouble(),
        status: j['status'] as String,
        sellAlertId: j['sell_alert_id'] as String?,
        openedAt: DateTime.parse(j['opened_at'] as String),
        closedAt: j['closed_at'] != null
            ? DateTime.parse(j['closed_at'] as String)
            : null,
      );

  bool get isOpen => status == 'open';
  double get gainGbp => amount * (currentGainPct ?? 0) / 100;
}

class HoldingsScreen extends StatefulWidget {
  const HoldingsScreen({super.key});

  @override
  State<HoldingsScreen> createState() => _HoldingsScreenState();
}

class _HoldingsScreenState extends State<HoldingsScreen> {
  List<OpenPosition> _positions = [];
  bool _loading = true;
  String? _error;

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
        Uri.parse(ApiConfig.holdings),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List;
        setState(() {
          _positions = list
              .map((e) => OpenPosition.fromJson(e as Map<String, dynamic>))
              .toList();
        });
      } else {
        setState(() => _error = 'Failed to load holdings (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Connection failed.');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _closePosition(OpenPosition pos) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text('Close ${pos.ticker}?',
            style: GoogleFonts.orbitron(color: AppColors.textPrimary, fontSize: 15)),
        content: Text(
          'Mark this position as closed. This records that you have sold ${pos.ticker} in Trading 212.',
          style: GoogleFonts.dmSans(color: AppColors.textMuted),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.pink),
            child: Text('Mark Closed',
                style: GoogleFonts.dmSans(color: Colors.white, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      final res = await http.post(
        Uri.parse('${ApiConfig.holdings}/${pos.id}/close'),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        _load();
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error: ${res.statusCode}')),
          );
        }
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connection failed.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        title: Text('My Holdings',
            style: GoogleFonts.orbitron(
                color: AppColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 15)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, size: 20),
            onPressed: _load,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(color: AppColors.orange));
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: AppColors.pink),
              const SizedBox(height: 12),
              Text(_error!,
                  textAlign: TextAlign.center,
                  style: GoogleFonts.dmSans(color: AppColors.textMuted)),
              const SizedBox(height: 16),
              OutlinedButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final open = _positions.where((p) => p.isOpen).toList();
    final closed = _positions.where((p) => !p.isOpen).toList();

    if (_positions.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.account_balance_wallet_outlined,
                  size: 64, color: AppColors.orange.withValues(alpha: 0.3)),
              const SizedBox(height: 20),
              Text('No open positions',
                  style: GoogleFonts.orbitron(
                      color: AppColors.textMuted, fontSize: 14)),
              const SizedBox(height: 8),
              Text(
                'When you mark an alert as "took trade", it appears here so Jimmy can alert you when to sell.',
                textAlign: TextAlign.center,
                style: GoogleFonts.dmSans(
                    color: AppColors.textMuted, fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      color: AppColors.orange,
      backgroundColor: AppColors.surface,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 40),
        children: [
          if (open.isNotEmpty) ...[
            _sectionHeader('Open Positions', open.length),
            const SizedBox(height: 8),
            ...open.map((p) => _PositionCard(
                  pos: p,
                  onClose: () => _closePosition(p),
                )),
          ],
          if (closed.isNotEmpty) ...[
            const SizedBox(height: 20),
            _sectionHeader('Closed Positions', closed.length),
            const SizedBox(height: 8),
            ...closed.map((p) => _PositionCard(pos: p)),
          ],
        ],
      ),
    );
  }

  Widget _sectionHeader(String title, int count) {
    return Row(
      children: [
        Text(title,
            style: GoogleFonts.dmSans(
                color: AppColors.textMuted,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 1)),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text('$count',
              style: GoogleFonts.dmSans(
                  color: AppColors.textMuted, fontSize: 11)),
        ),
      ],
    );
  }
}

// ── Position card ─────────────────────────────────────────────────────────────

class _PositionCard extends StatelessWidget {
  final OpenPosition pos;
  final VoidCallback? onClose;

  const _PositionCard({required this.pos, this.onClose});

  @override
  Widget build(BuildContext context) {
    final gain = pos.currentGainPct;
    final isUp = (gain ?? 0) >= 0;
    final gainColor = pos.isOpen
        ? (isUp ? AppColors.green : AppColors.pink)
        : AppColors.inactive;
    final hasSellAlert = pos.sellAlertId != null;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: hasSellAlert && pos.isOpen
              ? AppColors.pink.withValues(alpha: 0.4)
              : AppColors.border,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header row
            Row(
              children: [
                Expanded(
                  child: Row(
                    children: [
                      Text(pos.ticker,
                          style: GoogleFonts.orbitron(
                              color: AppColors.textPrimary,
                              fontWeight: FontWeight.w700,
                              fontSize: 15)),
                      const SizedBox(width: 8),
                      if (!pos.isOpen)
                        _badge('CLOSED', AppColors.inactive)
                      else if (hasSellAlert)
                        _badge('SELL ALERT', AppColors.pink)
                      else
                        _badge('OPEN', AppColors.green),
                    ],
                  ),
                ),
                if (gain != null)
                  Text(
                    '${isUp ? '+' : ''}${gain.toStringAsFixed(1)}%',
                    style: GoogleFonts.orbitron(
                        color: gainColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 14),
                  ),
              ],
            ),

            const SizedBox(height: 10),

            // Stats row
            Row(
              children: [
                _stat('Entry', '£${pos.entryPrice.toStringAsFixed(2)}'),
                const SizedBox(width: 20),
                _stat('Amount', '£${pos.amount.toStringAsFixed(0)}'),
                if (gain != null) ...[
                  const SizedBox(width: 20),
                  _stat(
                    'P&L',
                    '${pos.gainGbp >= 0 ? '+' : ''}£${pos.gainGbp.toStringAsFixed(2)}',
                    valueColor: gainColor,
                  ),
                ],
              ],
            ),

            const SizedBox(height: 6),

            Text(
              'Opened ${DateFormat('dd MMM yyyy').format(pos.openedAt.toLocal())}',
              style: GoogleFonts.dmSans(
                  fontSize: 11,
                  color: AppColors.textMuted.withValues(alpha: 0.6)),
            ),

            // Sell alert banner
            if (hasSellAlert && pos.isOpen) ...[
              const SizedBox(height: 10),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.pink.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                      color: AppColors.pink.withValues(alpha: 0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.notifications_active_outlined,
                        color: AppColors.pink, size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Jimmy sent a sell alert — check your notifications.',
                        style: GoogleFonts.dmSans(
                            color: AppColors.pink,
                            fontSize: 12,
                            fontWeight: FontWeight.w500),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // Close button
            if (pos.isOpen && onClose != null) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: onClose,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.pink,
                    side: const BorderSide(
                        color: AppColors.pink, width: 1),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                  child: Text('Mark as Sold',
                      style: GoogleFonts.dmSans(
                          fontWeight: FontWeight.w600, fontSize: 13)),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _badge(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(label,
          style: GoogleFonts.dmSans(
              fontSize: 10, fontWeight: FontWeight.w700, color: color)),
    );
  }

  Widget _stat(String label, String value, {Color? valueColor}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: GoogleFonts.dmSans(
                fontSize: 10,
                color: AppColors.textMuted.withValues(alpha: 0.6),
                letterSpacing: 0.5)),
        Text(value,
            style: GoogleFonts.dmSans(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: valueColor ?? AppColors.textPrimary)),
      ],
    );
  }
}
