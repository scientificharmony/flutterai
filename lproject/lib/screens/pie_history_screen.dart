import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';
import '../models/pie_model.dart';
import 'pie_result_screen.dart';

class PieHistoryScreen extends StatefulWidget {
  const PieHistoryScreen({super.key});

  @override
  State<PieHistoryScreen> createState() => _PieHistoryScreenState();
}

class _PieHistoryScreenState extends State<PieHistoryScreen> {
  List<SavedPieSummary> _pies = [];
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
        Uri.parse('${ApiConfig.baseUrl}/pie/history'),
        headers: {'device-id': 'demo-device-uuid'},
      );
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List;
        setState(() {
          _pies = list
              .map((e) => SavedPieSummary.fromJson(e as Map<String, dynamic>))
              .toList();
        });
      } else {
        setState(() => _error = 'Failed to load history.');
      }
    } catch (_) {
      setState(() => _error = 'Connection failed.');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Saved Pies'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_pies.isEmpty) {
      return const Center(
        child: Text(
          'No saved Pies yet.\nBuild a Pie and tap Save to keep it here.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _pies.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (_, i) => _PieTile(pie: _pies[i]),
      ),
    );
  }
}

class _PieTile extends StatelessWidget {
  final SavedPieSummary pie;
  const _PieTile({required this.pie});

  Color get _riskColor => switch (pie.riskLevel) {
        'low' => Colors.green,
        'high' => Colors.red,
        _ => Colors.orange,
      };

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: _riskColor.withValues(alpha: 0.15),
          child: Icon(Icons.pie_chart, color: _riskColor),
        ),
        title: Text(pie.pieName,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(
          '${pie.slices.length} slices · £${pie.totalAmount.toStringAsFixed(2)} · ${pie.riskLevel}',
          style: const TextStyle(fontSize: 12),
        ),
        trailing: Text(
          pie.createdAt.substring(0, 10),
          style: const TextStyle(fontSize: 12, color: Colors.grey),
        ),
        onTap: () {
          // Reconstruct a PieBuildResult for display purposes
          final now = DateTime.now().toUtc().toIso8601String();
          final result = PieBuildResult(
            pieName: pie.pieName,
            goal: '',
            riskLevel: pie.riskLevel,
            totalAmount: pie.totalAmount,
            timeHorizon: '',
            slices: pie.slices,
            overallRationale: '',
            riskNote: '',
            executable: true,
            safetyFlags: [],
            warnings: [],
            dataFreshness: DataFreshness(
              status: 'unavailable',
              newestDataTimestamp: now,
              oldestAllowedTimestamp: now,
              staleTickers: const [],
            ),
            marketDataTimestamp: now,
            validUntil: now,
            investOnlyVerified: true,
            allSlicesValidated: true,
            manualExecutionOnly: true,
          );
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => PieResultScreen(pie: result)),
          );
        },
      ),
    );
  }
}
