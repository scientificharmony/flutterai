import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import '../config/api_config.dart';
import '../models/alert_model.dart';
import '../services/device_service.dart';
import 'alert_detail_screen.dart';
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

  @override
  void initState() {
    super.initState();
    _loadAlerts();
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
      appBar: AppBar(
        title: const Text('Flutter AI'),
        actions: [
          IconButton(
            icon: const Icon(Icons.analytics_outlined),
            tooltip: 'Test Dashboard',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const PrivateDashboardScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.pie_chart_outline),
            tooltip: 'Saved Pies',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const PieHistoryScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadAlerts,
          ),
        ],
      ),
      body: _buildBody(),
      floatingActionButton: Column(
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
            child: const Icon(Icons.pie_chart),
          ),
          const SizedBox(height: 8),
          FloatingActionButton.extended(
            heroTag: 'scan_fab',
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const MissionScreen()),
              );
              _loadAlerts();
            },
            icon: const Icon(Icons.search),
            label: const Text('Manual Scan'),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline, size: 48, color: Colors.red[400]),
              const SizedBox(height: 12),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton(onPressed: _loadAlerts, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_alerts.isEmpty) {
      return const Center(
        child: Text(
          'No alerts yet.\nTap "Manual Scan" to generate your first alert.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _loadAlerts,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _alerts.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (_, i) => _AlertTile(
          alert: _alerts[i],
          onTap: () => _openAlert(_alerts[i]),
        ),
      ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  final TradeAlert alert;
  final VoidCallback onTap;

  const _AlertTile({required this.alert, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final expired = alert.isExpired;
    final color = alert.executable && !expired ? Colors.green : Colors.grey;

    return Card(
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: color.withValues(alpha: 0.15),
          child: Text(
            alert.action[0],
            style: TextStyle(
                fontWeight: FontWeight.bold, color: color, fontSize: 18),
          ),
        ),
        title: Row(
          children: [
            Text(alert.ticker,
                style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(width: 8),
            _ActionChip(action: alert.action),
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(alert.alertBody,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 2),
            Text(
              '${DateFormat('dd MMM HH:mm').format(alert.createdAt.toLocal())}  '
              '· Action Strength ${alert.actionStrength}/100  '
              '· ${alert.actionLabel}',
              style: TextStyle(fontSize: 11, color: Colors.grey[600]),
            ),
          ],
        ),
        trailing: expired
            ? const Icon(Icons.timer_off, color: Colors.grey, size: 18)
            : alert.executable
                ? const Icon(Icons.check_circle, color: Colors.green, size: 18)
                : const Icon(Icons.block, color: Colors.orange, size: 18),
      ),
    );
  }
}

class _ActionChip extends StatelessWidget {
  final String action;
  const _ActionChip({required this.action});

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color fg;
    switch (action) {
      case 'BUY_REVIEW':
        bg = Colors.green[100]!;
        fg = Colors.green[800]!;
      case 'REVIEW_SELL':
        bg = Colors.red[100]!;
        fg = Colors.red[800]!;
      case 'WATCH':
        bg = Colors.orange[100]!;
        fg = Colors.orange[800]!;
      case 'DO_NOT_ACT':
        bg = Colors.grey[300]!;
        fg = Colors.grey[800]!;
      default:
        bg = Colors.grey[200]!;
        fg = Colors.grey[700]!;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12)),
      child: Text(action,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: fg)),
    );
  }
}
