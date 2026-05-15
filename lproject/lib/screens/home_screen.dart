import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import '../config/api_config.dart';
import '../models/alert_model.dart';
import '../services/device_service.dart';
import '../theme/app_theme.dart';
import 'alert_detail_screen.dart';
import 'cfd_lab_screen.dart';
import 'forex_lab_screen.dart';
import 'holdings_screen.dart';
import 'mission_screen.dart';
import 'pie_builder_screen.dart';
import 'pie_history_screen.dart';
import 'private_dashboard_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<TradeAlert> _alerts = [];
  bool _loading = true;
  String? _error;
  Timer? _autoRefreshTimer;

  @override
  void initState() {
    super.initState();
    _loadAlerts();
    _autoRefreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _loadAlerts());
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadAlerts() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await http.get(
        Uri.parse(ApiConfig.alerts),
        headers: {'device-id': DeviceService.instance.deviceId},
      );
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List;
        setState(() {
          _alerts = list
              .map((e) => TradeAlert.fromJson(e as Map<String, dynamic>))
              .toList();
        });
      } else {
        setState(() => _error = 'Failed to load alerts (${res.statusCode})');
      }
    } catch (_) {
      setState(() => _error = 'Connection failed. Ensure backend is running.');
    } finally {
      setState(() => _loading = false);
    }
  }

  void _openAlert(TradeAlert alert) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AlertDetailScreen(alertId: alert.id),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _buildAppBar(),
      body: _buildBody(),
      floatingActionButton: _buildFabs(),
    );
  }

  AppBar _buildAppBar() {
    return AppBar(
      titleSpacing: 12,
      title: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            margin: const EdgeInsets.only(right: 7),
            decoration: BoxDecoration(
              color: AppColors.orange,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: AppColors.orange.withValues(alpha: 0.6), blurRadius: 8)],
            ),
          ),
          Text('HEY JIMMY',
              style: GoogleFonts.orbitron(
                  color: AppColors.orange, fontWeight: FontWeight.w700, fontSize: 13)),
        ],
      ),
      actions: [
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.analytics_outlined, size: 19),
          tooltip: 'Dashboard',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const PrivateDashboardScreen()),
          ),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.currency_exchange, size: 19),
          tooltip: 'Forex Lab',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const ForexLabScreen()),
          ),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.show_chart, size: 19),
          tooltip: 'CFD Lab',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CfdLabScreen()),
          ),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.account_balance_wallet_outlined, size: 19),
          tooltip: 'My Holdings',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const HoldingsScreen()),
          ),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.pie_chart_outline, size: 19),
          tooltip: 'Saved Pies',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const PieHistoryScreen()),
          ),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.refresh, size: 19),
          onPressed: _loadAlerts,
        ),
      ],
    );
  }

  Widget _buildFabs() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        FloatingActionButton.small(
          heroTag: 'pie_fab',
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const PieBuilderScreen()),
          ),
          tooltip: 'Build a Pie',
          backgroundColor: AppColors.surface,
          foregroundColor: AppColors.cyan,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: AppColors.cyan, width: 1),
          ),
          child: const Icon(Icons.pie_chart_outline, size: 18),
        ),
        const SizedBox(height: 10),
        FloatingActionButton.extended(
          heroTag: 'scan_fab',
          onPressed: () async {
            await Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const MissionScreen()),
            );
            _loadAlerts();
          },
          icon: const Icon(Icons.search, size: 18),
          label: Text('Scan Market',
              style: GoogleFonts.dmSans(fontWeight: FontWeight.w600)),
          backgroundColor: AppColors.orange,
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          elevation: 6,
        ),
      ],
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: AppColors.orange),
            const SizedBox(height: 16),
            Text('Scanning markets…',
                style: GoogleFonts.dmSans(color: AppColors.textMuted)),
          ],
        ),
      );
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
              OutlinedButton(onPressed: _loadAlerts, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_alerts.isEmpty) {
      return RefreshIndicator(
        color: AppColors.orange,
        backgroundColor: AppColors.surface,
        onRefresh: _loadAlerts,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 110),
          children: [
            _ForexLabEntry(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ForexLabScreen()),
              ),
            ),
            const SizedBox(height: 10),
            _CfdLabEntry(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const CfdLabScreen()),
              ),
            ),
            const SizedBox(height: 48),
            Column(
              children: [
                Icon(Icons.radar,
                    size: 64,
                    color: AppColors.orange.withValues(alpha: 0.3)),
                const SizedBox(height: 20),
                Text('No signals yet.',
                    style: GoogleFonts.orbitron(
                        color: AppColors.textMuted, fontSize: 14)),
                const SizedBox(height: 8),
                Text('Tap Scan Market to run your first analysis.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 13)),
              ],
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      color: AppColors.orange,
      backgroundColor: AppColors.surface,
      onRefresh: _loadAlerts,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 100),
        itemCount: _alerts.length + 1,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (_, i) {
          if (i == 0) {
            return Column(
              children: [
                _ForexLabEntry(
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const ForexLabScreen()),
                  ),
                ),
                const SizedBox(height: 10),
                _CfdLabEntry(
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const CfdLabScreen()),
                  ),
                ),
              ],
            );
          }
          final alert = _alerts[i - 1];
          return _AlertTile(
            alert: alert,
            onTap: () => _openAlert(alert),
          );
        },
      ),
    );
  }
}

class _ForexLabEntry extends StatelessWidget {
  final VoidCallback onTap;

  const _ForexLabEntry({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.cyan.withValues(alpha: 0.25)),
        ),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: AppColors.cyan.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.currency_exchange, color: AppColors.cyan, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Forex Lab',
                      style: GoogleFonts.orbitron(
                          color: AppColors.textPrimary,
                          fontWeight: FontWeight.w700,
                          fontSize: 13)),
                  const SizedBox(height: 3),
                  Text('Practice CFD signals and risk settings',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: AppColors.textMuted, size: 20),
          ],
        ),
      ),
    );
  }
}

class _CfdLabEntry extends StatelessWidget {
  final VoidCallback onTap;

  const _CfdLabEntry({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.orange.withValues(alpha: 0.25)),
        ),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: AppColors.orange.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.show_chart, color: AppColors.orange, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('CFD Lab',
                      style: GoogleFonts.orbitron(
                          color: AppColors.textPrimary,
                          fontWeight: FontWeight.w700,
                          fontSize: 13)),
                  const SizedBox(height: 3),
                  Text('Practice index, commodity, and stock CFD setups',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.dmSans(color: AppColors.textMuted, fontSize: 12)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: AppColors.textMuted, size: 20),
          ],
        ),
      ),
    );
  }
}

// ── Alert tile ────────────────────────────────────────────────────────────────

class _AlertTile extends StatelessWidget {
  final TradeAlert alert;
  final VoidCallback onTap;

  const _AlertTile({required this.alert, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final expired = alert.isExpired;
    final actionColor = _actionColor(alert.action, expired);
    final statusIcon = _statusIcon(alert, expired);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: expired ? AppColors.border : actionColor.withValues(alpha: 0.25),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              // Left accent bar
              Container(
                width: 3,
                height: 48,
                decoration: BoxDecoration(
                  color: expired ? AppColors.inactive : actionColor,
                  borderRadius: BorderRadius.circular(2),
                  boxShadow: expired
                      ? null
                      : [BoxShadow(color: actionColor.withValues(alpha: 0.5), blurRadius: 6)],
                ),
              ),
              const SizedBox(width: 12),
              // Ticker + info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          alert.ticker,
                          style: GoogleFonts.orbitron(
                            color: expired ? AppColors.textMuted : AppColors.textPrimary,
                            fontWeight: FontWeight.w700,
                            fontSize: 14,
                          ),
                        ),
                        const SizedBox(width: 8),
                        _ActionBadge(action: alert.action, expired: expired),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      alert.alertBody,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.dmSans(
                          fontSize: 12, color: AppColors.textMuted),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${DateFormat('dd MMM HH:mm').format(alert.createdAt.toLocal())}  ·  AS ${alert.actionStrength}/100',
                      style: GoogleFonts.dmSans(
                          fontSize: 11,
                          color: AppColors.textMuted.withValues(alpha: 0.7)),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              statusIcon,
            ],
          ),
        ),
      ),
    );
  }

  Color _actionColor(String action, bool expired) {
    if (expired) return AppColors.inactive;
    switch (action) {
      case 'BUY_REVIEW':
        return AppColors.green;
      case 'REVIEW_SELL':
        return AppColors.pink;
      case 'WATCH':
        return AppColors.orange;
      default:
        return AppColors.inactive;
    }
  }

  Widget _statusIcon(TradeAlert alert, bool expired) {
    if (expired) {
      return const Icon(Icons.timer_off_outlined, color: AppColors.inactive, size: 18);
    }
    if (alert.executable) {
      return const Icon(Icons.check_circle_outline, color: AppColors.green, size: 18);
    }
    return const Icon(Icons.remove_circle_outline, color: AppColors.orange, size: 18);
  }
}

// ── Action badge ──────────────────────────────────────────────────────────────

class _ActionBadge extends StatelessWidget {
  final String action;
  final bool expired;
  const _ActionBadge({required this.action, required this.expired});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;
    switch (action) {
      case 'BUY_REVIEW':
        color = AppColors.green;
        label = 'BUY';
      case 'REVIEW_SELL':
        color = AppColors.pink;
        label = 'SELL';
      case 'WATCH':
        color = AppColors.orange;
        label = 'WATCH';
      case 'DO_NOT_ACT':
        color = AppColors.inactive;
        label = 'HOLD';
      default:
        color = AppColors.inactive;
        label = action;
    }
    if (expired) color = AppColors.inactive;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        label,
        style: GoogleFonts.dmSans(
            fontSize: 10, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}
